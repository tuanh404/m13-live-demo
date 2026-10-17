import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_job_intake import check_job
from test_job_intake import intake as intake
from test_web_review import web_settings as web_settings

from src import config, contracts, pipeline
from src.api.job_intake import IntakeError
from src.api.job_predictions import cache_identity
from src.api.main import create_app
from src.api.saved_labels import canonical


def install_cache(settings, cfg, cvat, *, image_hash=None, empty=False):
    folder = settings.intake_config.parent
    preds = folder / 'detector.parquet'
    rows = [] if empty else [['shared-basename', 700, 300, 950, 500, 'car', .99]]
    pd.DataFrame(rows, columns=contracts.PRED_COLS).to_parquet(preds, index=False)
    raw = cvat.get('http://localhost:8080/api/jobs/9/data?type=frame&number=0&quality=original').content
    d = config.load('pipeline')['detector']
    manifest = {
        'schema': 1, 'model': d['model'], 'revision': d['revision'], 'confidence_floor': d['conf'],
        'predictions_file': preds.name, 'predictions_sha256': pipeline.sha256(preds),
        'class_map_sha256': hashlib.sha256(canonical(config.load('class_map')['coco_to_bdd'])).hexdigest(),
        'images': {'shared-basename': image_hash or hashlib.sha256(raw).hexdigest()},
        'empty_image_ids': ['shared-basename'] if empty else [],
        'source': 'synthetic independent detector fixture; not model inference',
    }
    target = folder / 'detector.json'
    target.write_text(json.dumps(manifest))
    cfg['predictions_manifest'] = str(target)
    import yaml

    settings.intake_config.write_text(yaml.safe_dump(cfg))
    return target, manifest


@pytest.mark.parametrize('empty', [False, True])
def test_verified_independent_cache_and_recheck_use_same_predictions(intake, empty):
    settings, cvat, _, _, cfg, _ = intake
    install_cache(settings, cfg, cvat, empty=empty)
    app = create_app(settings, cvat_client=cvat)
    client = TestClient(app)
    operation = check_job(client)
    assert operation['status'] == 'partial' and 'predictions cache' in operation['message']
    prefix = operation['result']['api_prefix']
    context = client.get(prefix + '/web/context').json()
    assert context['has_predictions'] and 'model_missing_label' in context['active_checks']
    active = next(iter(app.state.job_registry.store.state_items('job:').values()))
    manifest = json.loads(Path(active['queue_file']).with_suffix('.manifest.json').read_text())
    assert manifest['provenance']['detector_cache']['revision'] == (
        config.load('pipeline')['detector']['revision']
    )
    assert manifest['provenance']['missing'] == ['approved_guideline']
    # Saved-label recheck carries the verified image-independent predictions forward.
    snapshot = {'image_id': 'shared-basename', 'width': 1280, 'height': 720,
                'boxes': [], 'annotation_version': 2}
    result = pipeline.recheck(snapshot=snapshot, queue=pd.read_csv(active['queue_file']).fillna(''),
                              output_dir=Path(active['output']) / 'test-recheck',
                              model_version='cache-recheck', seed=42,
                              manifest_file=Path(active['queue_file']).with_suffix('.manifest.json'))
    assert result['preds_sha256'] == manifest['preds_sha256']
    assert 'model_missing_label' in result['used_signals']
    again = check_job(client, request_id='cache-again')
    assert again['result']['cache_hit']
    app.state.job_registry.pool.shutdown(wait=True)


def test_same_basename_different_image_bytes_stays_partial_geometry(intake):
    settings, cvat, _, _, cfg, _ = intake
    install_cache(settings, cfg, cvat, image_hash='0' * 64)
    app = create_app(settings, cvat_client=cvat)
    client = TestClient(app)
    operation = check_job(client)
    assert 'Chưa có predictions khớp ảnh' in operation['message']
    assert not client.get(operation['result']['api_prefix'] + '/web/context').json()['has_predictions']
    app.state.job_registry.pool.shutdown(wait=True)


def test_tampered_model_hash_and_mutation_during_request_rejected(intake):
    settings, cvat, _, _, cfg, _ = intake
    path, value = install_cache(settings, cfg, cvat)
    options = config.load('pipeline')
    initial = cache_identity(cfg, options)
    value['revision'] = '0' * 40
    path.write_text(json.dumps(value))
    with pytest.raises(IntakeError):
        cache_identity(cfg, options)
    value['revision'] = initial['revision']
    path.write_text(json.dumps(value))
    (path.parent / value['predictions_file']).write_bytes(b'broken-cache')
    with pytest.raises(IntakeError):
        cache_identity(cfg, options)
