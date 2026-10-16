"""Web uses frozen, hash-checked snapshots and the existing append-only API."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.fixtures import prepare_scored
from src.api.main import create_app
from src.api.settings import Settings


@pytest.fixture
def web_settings(tmp_path):
    record = prepare_scored(tmp_path / 'synthetic', count=3)
    root = Path(record['folder'])
    return Settings(
        reports=root, queue_file=root / 'ranked_queue_rule-fixture-qc-v1.csv',
        images=root / 'images', database=root / 'review.db',
        predictions=root / 'absent.parquet', mapping=root / 'absent-map.parquet',
        cvat_url='http://127.0.0.1:1',
    )


def test_web_without_cvat_preserves_snapshot_and_verdict_after_restart(web_settings):
    with TestClient(create_app(web_settings)) as client:
        assert client.get('/').status_code == 200
        assert client.get('/assets/review.js').status_code == 200
        assert client.get('/assets/transport.js').status_code == 200
        context = client.get('/web/context').json()
        assert context['fixture'] and context['verified']
        assert context['active_checks'] == ['edge_no_trunc']
        assert not context['has_predictions'] and not context['has_spec']
        assert str(web_settings.reports) not in json.dumps(context)
        queue = client.get('/queue').json()
        row = queue['items'][0]
        detail = client.get(f"/web/review/{row['image_id']}?queue_id={context['queue_id']}").json()
        assert detail['annotations'][0] == {
            'number': 1, 'obj_id': '1', 'category': 'car', 'box': [0, 180, 350, 380],
        }
        assert detail['risk_score'] == 50 and detail['labels_verified']
        assert detail['evidence'][0]['obj_id'] == '1'
        assert detail['cvat_url'] is None and detail['label_source'] == 'queue_snapshot'
        assert client.get(detail['image_url']).headers['content-type'] == 'image/jpeg'
        payload = dict(request_id='web-safe-retry', image_id=row['image_id'], verdict='error',
                       reviewer='web-unit', session_id='demo-unit', queue_id=queue['queue_id'],
                       rank=row['rank'], model_version=row['model_version'], seconds_spent=2)
        assert client.post('/verdict', json=payload).json()['duplicate'] is False
    with TestClient(create_app(web_settings)) as restarted:
        assert restarted.post('/verdict', json=payload).json()['duplicate'] is True
        scoped = '?reviewer=web-unit&session_id=demo-unit&order=priority'
        assert restarted.get('/queue' + scoped).json()['remaining'] == 2
        stats = restarted.get('/stats' + scoped).json()
        assert stats['review_events'] == 1 and stats['latest']['verdicts']['error'] == 1
        assert restarted.get('/queue?reviewer=other').json()['remaining'] == 3


@pytest.mark.parametrize('artifact', ['labels', 'evidence', 'queue'])
def test_web_rejects_tampered_artifact_and_stale_snapshot(web_settings, artifact):
    client = TestClient(create_app(web_settings))
    context = client.get('/web/context').json()
    url = f"/web/review/fixture-qc-01?queue_id={context['queue_id']}"
    assert client.get(url).status_code == 200
    assert client.get('/web/review/fixture-qc-01?queue_id=old').status_code == 409
    assert client.get('/web/review/foreign?queue_id=' + context['queue_id']).status_code == 404
    manifest = json.loads(web_settings.queue_file.with_suffix('.manifest.json').read_text())
    path = Path(manifest[artifact + '_file'])
    path.write_bytes(path.read_bytes() + b' ')
    assert client.get(url).status_code == 503


def test_web_without_manifest_never_invents_labels_or_checks(web_settings):
    web_settings.queue_file.with_suffix('.manifest.json').unlink()
    client = TestClient(create_app(web_settings))
    context = client.get('/web/context').json()
    assert not context['verified'] and context['active_checks'] == []
    detail = client.get('/web/review/fixture-qc-01?queue_id=' + context['queue_id']).json()
    assert detail['annotations'] == [] and detail['evidence'] == []
    assert not detail['labels_verified'] and detail['warnings']
    assert client.get('/assets/../../.env').status_code == 404


@pytest.mark.parametrize('kind', ['duplicate_frame', 'nan_evidence'])
def test_web_valid_hash_does_not_allow_malformed_snapshot(web_settings, kind):
    import hashlib

    path = web_settings.queue_file.with_suffix('.manifest.json')
    manifest = json.loads(path.read_text())
    if kind == 'duplicate_frame':
        target = Path(manifest['labels_file'])
        frames = json.loads(target.read_text())
        target.write_text(json.dumps(frames + [frames[0]]))
        manifest['labels_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    else:
        target = Path(manifest['evidence_file'])
        rows = [json.loads(line) for line in target.read_text().splitlines()]
        rows[0]['boxes'][0]['box'][0] = float('nan')
        target.write_text('\n'.join(json.dumps(row) for row in rows))
        manifest['evidence_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))
    client = TestClient(create_app(web_settings))
    queue_id = client.get('/web/context').json()['queue_id']
    assert client.get('/web/review/fixture-qc-01?queue_id=' + queue_id).status_code == 503
