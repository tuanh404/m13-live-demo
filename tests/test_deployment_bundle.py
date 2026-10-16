import json
import shutil
from pathlib import Path

import pytest

from src import config, pipeline
from src.api.deployment import backup, prepare_deployment, restore
from src.api.fixtures import prepare_scored
from src.api.review_setup import verify
from src.api.store import ReviewStore


def test_isolated_bundle_backup_restore_and_no_overwrite(tmp_path, monkeypatch):
    shutil.copytree(config.ROOT / 'extension', tmp_path / 'extension')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    source = tmp_path / 'data/source'
    record = prepare_scored(source, count=3)
    source = Path(record['folder'])
    out = tmp_path / 'data/shared'
    result = prepare_deployment(source, out, 'http://127.0.0.1:8050')
    assert not result['public_live_verified']
    assert Path(result['credentials_file']).stat().st_mode & 0o777 == 0o600
    assert not (source / 'accounts.json').exists()
    assert 'PRIVATE' in Path(result['credentials_file']).read_text()
    assert 'M13_PUBLIC_ORIGIN=http://127.0.0.1:8050' in (out / 'container.env').read_text()
    assert str(tmp_path) not in (out / 'container.env').read_text()
    with pytest.raises(ValueError, match='không ghi đè'):
        prepare_deployment(source, out, 'http://127.0.0.1:8050')
    store = ReviewStore(out / 'review.db')
    store.state('versions', {'v': {'queue_file': str(out / 'ranked_queue_fixture.csv')}})
    (out / 'cvat_map.parquet').write_bytes(b'old-host-mapping')
    store.append(dict(request_id='backup-test', image_id='fixture-qc-01', verdict='error', reviewer='unit',
                      seconds_spent=2, note='automated fixture', obj_ids=[], batch_id=None, queue_id='x',
                      model_version='fixture', rank=1, session_id='unit', review_order='priority'),
                 is_audit=False)
    archive = tmp_path / 'data/backup'
    backup(out, archive)
    assert not (archive / 'accounts.json').exists()
    assert not list(archive.rglob('*-access.txt'))
    restored = tmp_path / 'data/restored'
    restore(archive, restored, 'http://127.0.0.1:8051')
    assert verify(restored)['images'] == 3
    assert len(ReviewStore(restored / 'review.db').records()) == 1
    assert ReviewStore(restored / 'review.db').state('versions')['v']['queue_file'] == str(
        restored / 'ranked_queue_fixture.csv'
    )
    assert not (restored / 'cvat_map.parquet').exists()
    assert (restored / 'cvat_map.previous-host.parquet').exists()
    original_accounts = json.loads((out / 'accounts.json').read_text())
    assert json.loads((restored / 'accounts.json').read_text()) != original_accounts
    m = next(restored.glob('*.manifest.json'))
    data = json.loads(m.read_text())
    for kind in ('queue', 'labels', 'features', 'evidence', 'preds'):
        if data.get(kind + '_file'):
            assert pipeline.located(data[kind + '_file']).is_relative_to(restored)
    # A corrupt backup is rejected before creating the destination.
    (archive / 'review.db').write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash'):
        restore(archive, tmp_path / 'data/rejected', 'http://localhost:8052')
    assert not (tmp_path / 'data/rejected').exists()


def test_never_serve_plain_http_public(tmp_path, monkeypatch):
    shutil.copytree(config.ROOT / 'extension', tmp_path / 'extension')
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    source = tmp_path / 'data/source'
    record = prepare_scored(source, count=3)
    with pytest.raises(ValueError, match='HTTPS'):
        prepare_deployment(Path(record['folder']), tmp_path / 'data/no-http', 'http://public.example.test')
