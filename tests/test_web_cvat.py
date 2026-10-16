import copy

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_web_review import web_settings as web_settings

from src.api.main import create_app


@pytest.fixture
def web_cvat(web_settings):
    settings = web_settings
    settings.recheck_backend = "src.pipeline:recheck"
    settings.snapshot_dir = str(settings.reports / "snapshots")
    settings.recheck_dir = str(settings.reports / "rechecks")
    settings.cvat_url = "http://localhost:8080"
    pd.DataFrame(
        [[f"fixture-qc-{i + 1:02}", 8, 9, i] for i in range(3)],
        columns=["image_id", "task_id", "job_id", "frame"],
    ).to_parquet(settings.mapping)
    annotations = {
        "version": 1,
        "tracks": [],
        "shapes": [
            {
                "id": 101 + i,
                "frame": i,
                "label_id": 900,
                "type": "rectangle",
                "rotation": 0,
                "points": [0 if i == 0 else 150, 180, 350, 380],
                "occluded": False,
                "attributes": [{"spec_id": 901, "value": "false"}],
            }
            for i in range(3)
        ],
    }

    def transport(request):
        assert request.method == "GET"  # The integration never edits or saves on behalf of the user.
        path = request.url.path
        if path == "/api/jobs/9":
            data = {"task_id": 8, "start_frame": 0, "stop_frame": 2, "type": "annotation"}
        elif path == "/api/jobs/9/data/meta":
            data = {
                "frames": [
                    {"name": f"fixture-qc-{i + 1:02}.jpg", "width": 1280, "height": 720} for i in range(3)
                ]
            }
        elif path == "/api/labels":
            data = {
                "results": [
                    {
                        "id": 900,
                        "name": "car",
                        "attributes": [{"id": 901, "name": "truncated", "input_type": "checkbox"}],
                    }
                ],
                "next": None,
            }
        elif path == "/api/jobs/9/annotations":
            data = copy.deepcopy(annotations)
        else:
            return httpx.Response(404)
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        yield settings, annotations, client


def test_web_saved_vs_canvas_recheck_immutable_history_and_retry(web_cvat):
    settings, saved, cvat = web_cvat
    app = create_app(settings, cvat_client=cvat)
    client = TestClient(app)
    queue_id = client.get("/web/context").json()["queue_id"]
    original = settings.queue_file.read_bytes()
    image = "fixture-qc-01"
    local = TestClient(app, base_url="http://localhost:8000")
    link = local.get(f"/web/cvat/{image}?queue_id={queue_id}").json()
    assert link["url"] == "http://localhost:8080/tasks/8/jobs/9?frame=0"
    public = TestClient(app, base_url="https://demo.example.org")
    assert public.get(f"/web/cvat/{image}?queue_id={queue_id}").json()["available"] is False
    captured = client.get(f"/image/{image}/saved?queue_id={queue_id}").json()
    assert captured["boxes"][0]["box"][0] == 0
    # Unsaved client canvas has no influence on API inputs or the active score.
    unsaved = copy.deepcopy(saved)
    unsaved["shapes"][0]["points"][0] = 100
    assert client.get(f"/image/{image}/saved").json()["snapshot_id"] == captured["snapshot_id"]
    saved.update(unsaved)
    saved["version"] += 1
    value = {"request_id": "stale-read", "snapshot_id": captured["snapshot_id"], "queue_id": queue_id}
    assert client.post(f"/image/{image}/recheck", json=value).status_code == 409
    fresh = client.get(f"/image/{image}/saved").json()
    value.update(request_id="saved-recheck", snapshot_id=fresh["snapshot_id"])
    result = client.post(f"/image/{image}/recheck", json=value)
    assert result.status_code == 200, result.text
    assert result.json()["risk_before"] == 50 and result.json()["risk_after"] == 0
    assert client.post(f"/image/{image}/recheck", json=value).json() == result.json()
    assert settings.queue_file.read_bytes() == original
    before = client.get(f"/web/review/{image}?queue_id={queue_id}").json()
    after = client.get(f"/web/review/{image}?queue_id={result.json()['queue_id']}").json()
    assert before["annotations"][0]["box"][0] == 0 and before["risk_score"] == 50
    assert after["annotations"][0]["box"][0] == 100 and after["risk_score"] == 0
    frame, current_id, path = app.state.service.snapshot()
    plan = app.state.service.audit_plan(frame, current_id, path)
    assert plan['source_queue_id'] == queue_id
    assert plan['source_model_version'] == 'rule-fixture-qc-v1'
    history = client.get(f"/web/recheck-history/{image}").json()["entries"]
    assert len(history) == 1 and history[0]["result"] == result.json()


def test_web_cvat_unavailable_keeps_core_review_usable(web_settings):
    client = TestClient(create_app(web_settings), base_url="http://localhost:8000")
    queue_id = client.get("/web/context").json()["queue_id"]
    link = client.get("/web/cvat/fixture-qc-01?queue_id=" + queue_id).json()
    assert not link["available"] and "url" not in link
    assert client.get("/queue").status_code == 200
    assert client.get("/web/review/fixture-qc-01?queue_id=" + queue_id).status_code == 200


def test_manifest_backend_cannot_publish_labels_different_from_saved_cvat(web_cvat):
    import json

    from src import pipeline

    settings, saved, cvat = web_cvat
    app = create_app(settings, cvat_client=cvat)

    def incorrect(*, snapshot, queue, output_dir, model_version, seed, manifest_file):
        result = pipeline.recheck(snapshot=snapshot, queue=queue, output_dir=output_dir,
                                  model_version=model_version, seed=seed, manifest_file=manifest_file)
        labels = pipeline.located(result['labels_file'])
        frames = json.loads(labels.read_text())
        frames[0]['labels'][0]['box2d']['x1'] = 99
        pipeline.write_json(labels, frames)
        manifest = pipeline.located(result['manifest_file'])
        data = json.loads(manifest.read_text())
        data['labels_sha256'] = pipeline.sha256(labels)
        pipeline.write_json(manifest, data)
        return result

    app.state.rechecks.backend = incorrect
    client = TestClient(app)
    source = client.get('/image/fixture-qc-01/saved').json()
    result = client.post('/image/fixture-qc-01/recheck', json={
        'request_id': 'bad-snapshot', 'queue_id': source['queue_id'], 'snapshot_id': source['snapshot_id']})
    assert result.status_code == 503
    assert client.get('/web/context').json()['queue_id'] == source['queue_id']
