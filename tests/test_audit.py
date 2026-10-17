import json
import math
import random
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_review_api import payload
from test_review_api import setup_review as setup_review

from src import contracts
from src.api import audit
from src.api.fixtures import prepare_scored
from src.api.main import Verdict, create_app
from src.api.operations import export_audit
from src.api.review_setup import prepare
from src.api.settings import Settings


def frame(n):
    return pd.DataFrame([[f'id-{i:05}', n-i, i+1, 'reason', 'rule-v1'] for i in range(n)],
                        columns=contracts.QUEUE_COLS)


@pytest.mark.parametrize('n', [0, 1, 2, 7, 40, 2000, 10000])
def test_plan_exact_population_sample_interleave_and_unchanged_rank(n):
    source = frame(n)
    before = source.copy(deep=True)
    plan = audit.make_plan(source, 'source-sha')
    assert plan == audit.validate_plan(plan) == audit.make_plan(source, 'source-sha')
    top = math.ceil(.2*n)
    assert plan['n_top'] == top and plan['n_audit'] == math.ceil(.05*(n-top))
    tail = source.image_id.tolist()[top:]
    assert plan['audit_ids'] == random.Random(42).sample(tail, plan['n_audit'])
    assert set(plan['audit_ids']) <= set(tail)
    assert len(plan['order']) == len(set(plan['order'])) == n
    assert set(plan['order']) == set(source.image_id)
    if plan['n_audit']:
        k = max(1, top//plan['n_audit'])
        assert plan['order'][k] == plan['audit_ids'][0]
    if n == 10000:
        assert plan['n_top'] == 2000 and plan['n_audit'] == 400
    pd.testing.assert_frame_equal(source, before)


@pytest.mark.parametrize('options', [{'audit_rate': -1}, {'audit_rate': float('nan')},
    {'audit_rate': 1.1}, {'audit_top_frac': 0}, {'audit_top_frac': 1.1}, {'audit_seed': True}])
def test_invalid_policy_config_rejected(options):
    with pytest.raises(ValueError):
        Settings(**options)


@pytest.mark.parametrize('top,rate', [(1, 1), (.2, 0), (.1, 1)])
def test_no_audit_and_more_audits_than_top_have_no_duplicates(top, rate):
    plan = audit.make_plan(frame(10), 'source', top_frac=top, rate=rate)
    assert len(plan['order']) == len(set(plan['order'])) == 10
    assert len(plan['audit_ids']) == math.ceil(rate*(10-math.ceil(top*10)))


def event(plan, image, verdict, **updates):
    return {'image_id': image, 'verdict': verdict, 'is_audit': True, 'review_order': 'priority',
            'audit_policy_id': plan['policy_id'], 'audit_source_queue_id': plan['source_queue_id'], **updates}


def test_wilson_unique_latest_skip_legacy_and_file_order_excluded():
    plan = audit.make_plan(frame(2000), 'source-sha')
    ids = plan['audit_ids']
    rows = [event(plan, i, 'error' if n < 15 else 'false_alarm') for n, i in enumerate(ids[:30])]
    report = audit.summary(plan, rows)
    assert report['valid'] == 30 and report['error_rate'] == .5
    assert report['wilson95'] == pytest.approx([.3315412564, .6684587436])
    assert report['tail_errors_estimate'] == 800
    assert report['planned_review_images'] == 480 and report['planned_review_fraction'] == .24
    rows += [event(plan, ids[0], 'skip'), event(plan, ids[31], 'error', review_order='file'),
             event(plan, ids[32], 'error', audit_policy_id='legacy-every10'),
             event(plan, ids[33], 'error', audit_source_queue_id='foreign')]
    report = audit.summary(plan, rows)
    assert report['valid'] == 29 and report['verdicts']['skip'] == 1
    assert report['status'] == 'insufficient' and report['tail_errors_estimate'] is None
    empty = audit.summary(plan, [])
    assert empty['valid'] == 0 and empty['error_rate'] is None and empty['wilson95'] is None


def test_subset_freezes_original_40_before_cut_to_10_and_retries_without_overwrite(tmp_path):
    result = prepare_scored(tmp_path/'source', count=40)
    source = Path(result['folder'])
    queue = source/'ranked_queue_rule-fixture-qc-v1.csv'
    output = tmp_path/'subset'
    record = prepare(queue, source/'images', output, source_root=tmp_path/'source', limit=10)
    manifest = json.loads((output/queue.name).with_suffix('.manifest.json').read_text())
    plan = manifest['audit_plan']
    assert plan['N'] == 40 and plan['n_top'] == 8 and plan['n_audit'] == 2
    original = pd.read_csv(queue)
    assert plan['source_ranks'] == {r.image_id: r.rank for r in original.itertuples()}
    subset = pd.read_csv(output/queue.name)
    assert set(subset.image_id) == set(plan['order'][:10])
    assert not contracts.check_queue(subset)
    settings = Settings(queue_file=output/queue.name, database=output/'review.db',
                        images=output/'images', mapping=output/'missing', predictions=output/'absent')
    client = TestClient(create_app(settings))
    visible = client.get('/queue').json()['items']
    assert [r['image_id'] for r in visible] == plan['order'][:10]
    assert all('is_audit' not in r and 'audit_policy_id' not in r for r in visible)
    assert prepare(queue, source/'images', output, source_root=tmp_path/'source', limit=10) == record


def test_audit_verdict_retry_policy_separation_and_export(setup_review, tmp_path, monkeypatch):
    client = TestClient(create_app(setup_review))
    items = client.get('/queue').json()['items']
    sampled = items[5]
    value = payload(client, sampled['image_id'], request_id='audit-request')
    assert client.post('/verdict', json=value).status_code == 200
    assert client.post('/verdict', json=value).json()['duplicate'] is True
    store = client.app.state.store
    rows = store.records()
    assert len(rows) == 1 and rows[0]['is_audit']
    assert rows[0]['audit_policy_version'] == audit.POLICY_VERSION
    assert rows[0]['source_rank'] == sampled['rank']
    file_value = {**value, 'request_id': 'file-order', 'review_order': 'file'}
    assert client.post('/verdict', json=file_value).status_code == 200
    assert store.records()[-1]['is_audit'] is False
    # Old-policy retry/history remains readable but cannot contribute to the new policy estimate.
    old = {**value, 'request_id': 'old-policy', 'image_id': items[0]['image_id']}
    for key in ('queue_id', 'model_version', 'rank'):
        old[key] = rows[0][key]
    store.append(Verdict(**old).model_dump(), is_audit=True)
    monkeypatch.setattr(Settings, 'configured', lambda: setup_review)
    output = tmp_path/'audit.json'
    report = export_audit(output)
    assert report['events'] == 1 and report['valid'] == 1 and report['status'] == 'insufficient'
    csv = pd.read_csv(output.with_suffix('.csv'))
    assert len(csv) == 1 and csv.audit_policy_version.iloc[0] == audit.POLICY_VERSION
    with pytest.raises(ValueError, match='đã có'):
        export_audit(output)


def test_old_sqlite_migrates_without_changing_history_or_retry_hash(setup_review):
    import sqlite3

    from src.api.store import ReviewStore

    client = TestClient(create_app(setup_review))
    value = payload(client, 'image-01', request_id='old-ack')
    assert client.post('/verdict', json=value).status_code == 200
    with sqlite3.connect(setup_review.database) as db:
        before = db.execute('SELECT payload_hash FROM verdicts').fetchone()[0]
        for name in ['audit_policy_id', 'audit_policy_version', 'audit_source_queue_id', 'source_rank']:
            db.execute(f'ALTER TABLE verdicts DROP COLUMN {name}')
    migrated = ReviewStore(setup_review.database)
    assert migrated.records()[0]['audit_policy_version'] == 'legacy-every10'
    with migrated.connection() as db:
        assert db.execute('SELECT payload_hash FROM verdicts').fetchone()[0] == before
    assert client.post('/verdict', json=value).json()['duplicate'] is True


def test_legacy_subset_is_unavailable_instead_of_sampling_its_tail(tmp_path):
    source = Path(prepare_scored(tmp_path/'source', count=40)['folder'])
    output = tmp_path/'subset'
    queue = source/'ranked_queue_rule-fixture-qc-v1.csv'
    prepare(queue, source/'images', output, source_root=tmp_path/'source', limit=10)
    path = (output/queue.name).with_suffix('.manifest.json')
    manifest = json.loads(path.read_text())
    del manifest['audit_plan']
    path.write_text(json.dumps(manifest))
    app = create_app(Settings(queue_file=output/queue.name, database=output/'review.db'))
    client = TestClient(app)
    visible = client.get('/queue').json()
    assert len(visible['items']) == 10
    service = app.state.service
    plan = service.audit_plan(*service.snapshot())
    assert plan['status'] == 'unavailable' and plan['audit_ids'] == []
    assert audit.summary(plan, [])['wilson95'] is None


def test_explicit_demo_selection_keeps_full_population_plan_and_rejects_mixed_versions(tmp_path):
    source = Path(prepare_scored(tmp_path / "source", count=40)["folder"])
    queue = source / "ranked_queue_rule-fixture-qc-v1.csv"
    original = pd.read_csv(queue)
    selected = set(original.image_id.iloc[[0, 3, 15, 30]])
    args = dict(source_root=source, limit=4, include_image_ids=selected)
    record = prepare(queue, source / "images", tmp_path / "release", **args)
    manifest = json.loads((tmp_path / "release" / queue.name).with_suffix(".manifest.json").read_text())
    plan = manifest["audit_plan"]
    assert plan["N"] == 40 and plan["source_queue_id"] == record["identity"]["source_queue_sha256"]
    assert plan["source_model_version"] == record["version"]
    cropped = pd.read_csv(tmp_path / "release" / queue.name)
    assert set(cropped.image_id) == selected
    pd.testing.assert_frame_equal(
        cropped.drop(columns="rank").reset_index(drop=True),
        original[original.image_id.isin(selected)].drop(columns="rank").reset_index(drop=True),
    )
    assert prepare(queue, source / "images", tmp_path / "release", **args) == record
    assert prepare(source / queue.name, source / "images", tmp_path / "full", source_root=source, limit=40)
    source_manifest = json.loads(queue.with_suffix(".manifest.json").read_text())
    bad = original.copy()
    bad["model_version"] = "different-scorer"
    source_manifest["audit_plan"] = audit.make_plan(bad, "different-source")
    queue.with_suffix(".manifest.json").write_text(json.dumps(source_manifest))
    with pytest.raises(ValueError, match="khác phiên bản"):
        prepare(queue, source / "images", tmp_path / "bad-release", **args)
    assert not (tmp_path / "bad-release").exists()
