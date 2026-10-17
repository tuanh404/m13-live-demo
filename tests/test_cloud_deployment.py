import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_postgres_store import pg_url as pg_url
from test_web_review import web_settings as web_settings

from src.api.cloud import asset_name, backup_cloud, hydrate, prepare_bundle, restore_cloud, upload_bundle
from src.api.render_app import create_render_app
from src.api.saved_labels import canonical
from src.api.store import ReviewStore


def test_import_factory_does_not_boot_unconfigured_default_app():
    result = subprocess.run(
        [sys.executable, '-c', 'from src.api.main import create_app; print(callable(create_app))'],
        env={**os.environ, 'M13_PUBLIC_ORIGIN': 'https://factory.example.test'},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'True'


def test_cloud_rejects_private_paths_and_fixture_claimed_real(web_settings, tmp_path):
    for path in ("../accounts.json", "/tmp/data.json", "account.env", "pilot/review.json", ".env"):
        with pytest.raises(ValueError):
            asset_name(path)
    with pytest.raises(ValueError, match="thật"):
        prepare_bundle(web_settings.reports, tmp_path / "bundle", acquisition=tmp_path / "none.json")


@pytest.fixture
def cloud_fixture(pg_url, web_settings, tmp_path, monkeypatch):
    manifest = json.loads(web_settings.queue_file.with_suffix(".manifest.json").read_text())
    root = tmp_path / "bundle"
    root.mkdir()
    sources = [web_settings.queue_file, web_settings.queue_file.with_suffix(".manifest.json")]
    sources += [Path(manifest[k + "_file"]) for k in ("labels", "features", "evidence")]
    sources += list(web_settings.images.glob("*.jpg"))
    hashes = {}
    for source in sources:
        name = str(source.relative_to(web_settings.reports))
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        hashes[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    descriptor = {
        "schema": 1,
        "version": manifest["model_version"],
        "images": 3,
        "files": hashes,
        "data_purpose": "development",
        "purpose": "fixture_software_test",
    }
    (root / "bundle.json").write_bytes(canonical(descriptor))
    monkeypatch.setenv("M13_DATABASE_URL", pg_url)
    bundle = upload_bundle(root)
    monkeypatch.setenv("M13_DEMO_BUNDLE_ID", bundle["bundle_id"])
    monkeypatch.setenv("M13_AUTH_SECRET", "unit-cloud-secret-value-not-a-real-key-1234")
    monkeypatch.setenv("M13_PUBLIC_ORIGIN", "https://demo.example.test")
    monkeypatch.setenv("M13_RENDER_DATA", str(tmp_path / "runtime"))
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    return root, bundle


@pytest.mark.skipif(not os.getenv("M13_TEST_DATABASE_URL"), reason="real PostgreSQL required")
def test_render_guest_disk_loss_does_not_lose_session_or_verdict(
    cloud_fixture, monkeypatch, tmp_path, pg_url
):
    root, bundle = cloud_fixture
    client = TestClient(create_render_app(), base_url="https://demo.example.test")
    assert client.get("/queue").status_code == 401
    assert client.post("/auth/demo").status_code == 403
    headers = {"Origin": "https://demo.example.test"}
    assert client.post("/auth/demo", headers=headers).status_code == 200
    who = client.get("/auth/session").json()["identity"]
    params = {"reviewer": who["reviewer"], "session_id": who["session_id"], "order": "priority"}
    queue = client.get("/queue", params=params).json()
    detail = client.get(
        "/web/review/" + queue["items"][0]["image_id"], params={"queue_id": queue["queue_id"]}
    ).json()
    assert detail["cvat_url"] is None and client.get(detail["image_url"]).status_code == 200
    assert client.get("/review/workspace").json()["guideline_url"] == ""
    assert client.get("/web/context").json()["fixture"]
    for path in ("/model", "/intake", "/jobs/" + "a" * 32 + "/queue", "/web/cvat/fixture-qc-01"):
        assert client.get(path).status_code == 403
    payload = dict(
        request_id="cloud-verdict",
        image_id=queue["items"][0]["image_id"],
        verdict="false_alarm",
        reviewer=who["reviewer"],
        session_id=who["session_id"],
        seconds_spent=1,
    )
    assert client.post("/verdict", json=payload, headers=headers).json()["duplicate"] is False
    monkeypatch.setenv("M13_RENDER_DATA", str(tmp_path / "new-ephemeral-disk"))
    restarted = TestClient(create_render_app(), base_url="https://demo.example.test")
    restarted.cookies.update(client.cookies)
    assert restarted.get("/auth/session").json()["authenticated"]
    assert restarted.get("/stats", params=params).json()["review_events"] == 1
    assert restarted.post("/verdict", json=payload, headers=headers).json()["duplicate"] is True
    public = json.dumps([restarted.get("/auth/session").json(), restarted.get("/web/context").json(), detail])
    assert os.environ["M13_AUTH_SECRET"] not in public and pg_url not in public
    assert upload_bundle(root)["bundle_id"] == bundle["bundle_id"]
    import psycopg

    with pytest.raises(psycopg.Error, match="immutable"), psycopg.connect(pg_url) as db:
        db.execute("DELETE FROM demo_assets")


@pytest.mark.skipif(not os.getenv("M13_TEST_DATABASE_URL"), reason="real PostgreSQL required")
def test_cloud_backup_restore_new_database_and_reject_overwrite(cloud_fixture, tmp_path, pg_url, monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    root, bundle = cloud_fixture
    store = ReviewStore(tmp_path / "none.db", pg_url)
    store.state("auth-session:old", {"expires": 9999999999})
    store.state("retained", {"value": 42})
    backup = tmp_path / "private-backup.json"
    backup_cloud(backup)
    assert backup.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="trống"):
        restore_cloud(backup)
    name = "m13_restore_" + uuid4().hex
    with psycopg.connect(pg_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    kwargs = conninfo_to_dict(pg_url)
    kwargs["dbname"] = name
    restored_url = make_conninfo(**kwargs)
    try:
        monkeypatch.setenv("M13_DATABASE_URL", restored_url)
        assert restore_cloud(backup)["status"] == "restored"
        restored = ReviewStore(tmp_path / "none.db", restored_url)
        assert restored.state("retained") == {"value": 42}
        assert restored.state("auth-session:old") is None
        assert hydrate(bundle["bundle_id"], tmp_path / "hydrated")["images"] == 3
        with pytest.raises(psycopg.Error, match="immutable"), psycopg.connect(restored_url) as db:
            db.execute("DELETE FROM demo_assets")
        with pytest.raises(ValueError):
            restore_cloud(backup)
    finally:
        with psycopg.connect(pg_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.skipif(not os.getenv('M13_TEST_DATABASE_URL'), reason='real PostgreSQL required')
def test_new_release_preserves_previous_snapshot_stats_session_and_lost_ack(
    cloud_fixture, monkeypatch, tmp_path
):
    from src import pipeline

    root, old = cloud_fixture
    client = TestClient(create_render_app(), base_url='https://demo.example.test')
    headers = {'Origin': 'https://demo.example.test'}
    assert client.post('/auth/demo', headers=headers).status_code == 200
    identity = client.get('/auth/session').json()['identity']
    params = {'reviewer': identity['reviewer'], 'session_id': identity['session_id'], 'order': 'priority'}
    queue = client.get('/queue', params=params).json()
    payload = dict(request_id='before-release', image_id=queue['items'][0]['image_id'],
                   verdict='skip', reviewer=identity['reviewer'], session_id=identity['session_id'],
                   seconds_spent=1, queue_id=queue['queue_id'])
    assert client.post('/verdict', json=payload, headers=headers).status_code == 200
    # New assets and queue ID; no mutation of the old bundle or its review events.
    new = tmp_path / 'new-bundle'
    new.mkdir()
    hashes = {}
    version = 'fixture-new-release'
    old_version = json.loads((root / 'bundle.json').read_text())['version']
    for path in root.rglob('*'):
        if not path.is_file() or path.name == 'bundle.json':
            continue
        name = str(path.relative_to(root)).replace(old_version, version)
        raw = path.read_bytes()
        if path.suffix in {'.json', '.csv'}:
            raw = raw.replace(old_version.encode(), version.encode())
        target = new / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        hashes[name] = pipeline.sha256(target)
    manifest_path = new / f'ranked_queue_{version}.manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['queue_sha256'] = pipeline.sha256(new / f'ranked_queue_{version}.csv')
    if manifest.get('audit_plan'):
        from src.api.audit import digest

        plan = manifest['audit_plan']
        plan['policy_id'] = digest({k: v for k, v in plan.items() if k != 'policy_id'})
    manifest_path.write_bytes(canonical(manifest))
    hashes[manifest_path.name] = pipeline.sha256(manifest_path)
    descriptor = {'schema': 1, 'version': version, 'images': 3, 'files': hashes,
                  'queue_sha256': manifest['queue_sha256'], 'data_purpose': 'development'}
    # Legacy descriptors in this fixture need the hash production descriptors already carry.
    old_descriptor = json.loads((root / 'bundle.json').read_text())
    old_descriptor['queue_sha256'] = queue['queue_id']
    (root / 'bundle.json').write_bytes(canonical(old_descriptor))
    previous = upload_bundle(root)
    (new / 'bundle.json').write_bytes(canonical(descriptor))
    updated = upload_bundle(new)
    monkeypatch.setenv('M13_DEMO_BUNDLE_ID', updated['bundle_id'])
    monkeypatch.setenv('M13_PREVIOUS_DEMO_BUNDLE_IDS', json.dumps([previous['bundle_id']]))
    monkeypatch.setenv('M13_RENDER_DATA', str(tmp_path / 'release-runtime'))
    restarted = TestClient(create_render_app(), base_url='https://demo.example.test')
    restarted.cookies.update(client.cookies)
    assert restarted.get('/auth/session').json()['authenticated']
    current = restarted.get('/queue', params=params)
    assert current.status_code == 200, current.text
    assert current.json()['queue_id'] != queue['queue_id']
    history = restarted.get('/stats', params={**params, 'queue_id': queue['queue_id']}).json()
    assert history['review_events'] == 1
    assert restarted.post('/verdict', json=payload, headers=headers).json()['duplicate'] is True


@pytest.mark.skipif(not os.getenv('M13_TEST_DATABASE_URL'), reason='real PostgreSQL required')
def test_public_presentation_is_fixed_immutable_and_never_exposes_source(cloud_fixture, tmp_path):
    from src.api.submission import publish_assets

    root, _ = cloud_fixture
    client = TestClient(create_render_app(), base_url='https://demo.example.test')
    assert client.get('/queue').status_code == 401
    assert client.get('/web/submission').status_code == 404
    folder = tmp_path / 'presentation'
    folder.mkdir()
    for name, raw in [('pitch.pdf', b'%PDF-fixture'), ('thumbnail.png', b'\x89PNG-fixture'),
                      ('M13-demo.mp4', b'0000ftyp-fixture')]:
        (folder / name).write_bytes(raw)
    published = publish_assets(folder)
    assert publish_assets(folder) == published
    metadata = client.get('/web/submission').json()
    assert metadata['id'] == published['id']
    for item in published['assets'].values():
        response = client.get(item['path'])
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == item['sha256']
        assert 'immutable' in response.headers['cache-control']
    for name in ['M13-source-final.zip', '.env', 'accounts.json', 'presentation.json']:
        assert client.get('/submission/assets/' + published['id'] + '/' + name).status_code == 404
    assert client.get('/queue').status_code == 401
    assert client.post('/web/submission').status_code in {401, 403, 405}
