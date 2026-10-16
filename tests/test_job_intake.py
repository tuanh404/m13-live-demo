"""CVAT fixture is read-only; risk is computed by the existing real rule pipeline."""

import copy
import io
import time

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image
from test_web_review import web_settings as web_settings

from src import config
from src.api.job_intake import IntakeError, JobReader, workspace_key
from src.api.main import create_app


@pytest.fixture
def intake(web_settings, tmp_path):
    cfg = copy.deepcopy(config.load("job_intake"))
    cfg.update(root=str(tmp_path / "jobs"), allowed_task_ids=[8])
    settings = web_settings
    settings.cvat_url = "http://localhost:8080"
    settings.intake_config = tmp_path / "intake.yaml"
    settings.intake_config.write_text(yaml.safe_dump(cfg))
    annotations = {
        job: {
            "version": 1,
            "tracks": [],
            "tags": [],
            "shapes": [
                {
                    "id": job * 100,
                    "frame": 0 if job == 9 else 1,
                    "label_id": 900,
                    "type": "rectangle",
                    "rotation": 0,
                    "points": [0, 180, 350, 380],
                    "occluded": False,
                    "attributes": [{"spec_id": 901, "value": "false"}],
                },
            ],
        }
        for job in (9, 10)
    }
    problems = {
        "failure": False,
        "changed": False,
        "deleted": False,
        "step": False,
        "duplicate": False,
        "dimension": "2d",
        "width": 1280,
        "denied": False,
    }
    img = io.BytesIO()
    Image.new("RGB", (1280, 720), (30, 60, 90)).save(img, format="JPEG")
    requests = []

    def transport(request):
        requests.append(str(request.url))
        assert request.method == "GET"
        path = request.url.path
        if problems["denied"]:
            return httpx.Response(403)
        if path == "/api/tasks/8":
            data = {"dimension": problems["dimension"], "mode": "annotation"}
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
        else:
            parts = path.split("/")
            if len(parts) < 4 or parts[2] != "jobs" or not parts[3].isdigit():
                return httpx.Response(404)
            job = int(parts[3])
            if job not in annotations:
                return httpx.Response(404)
            frame = 0 if job == 9 else 1
            if path.endswith("/data/meta"):
                data = {
                    "frames": [{"name": "shared-basename.jpg", "width": problems["width"], "height": 720}],
                    "frame_filter": "step=2" if problems["step"] else "",
                    "deleted_frames": [frame] if problems["deleted"] else [],
                }
                if problems["duplicate"]:
                    data["frames"] *= 2
            elif path.endswith("/annotations"):
                data = copy.deepcopy(annotations[job])
                if problems["changed"]:
                    annotations[job]["version"] += 1
            elif path.endswith("/data"):
                if problems["failure"]:
                    raise httpx.ReadTimeout("private fixture timeout")
                return httpx.Response(200, content=img.getvalue())
            else:
                data = {
                    "id": job,
                    "task_id": 8,
                    "type": "annotation",
                    "start_frame": frame,
                    "stop_frame": frame + int(problems["duplicate"]),
                }
        return httpx.Response(200, json=data)

    with httpx.Client(transport=httpx.MockTransport(transport)) as cvat:
        yield settings, cvat, annotations, problems, cfg, requests


def check_job(client, job=9, request_id="intake-test"):
    value = {"cvat_origin": "http://localhost:8080", "task_id": 8, "job_id": job, "request_id": request_id}
    result = client.post("/intake/check", json=value)
    assert result.status_code == 202, result.text
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = client.get("/intake/requests/" + request_id)
        if result.json()["status"] in {"partial", "completed", "failed"}:
            return result.json()
        time.sleep(0.02)
    pytest.fail("Intake fixture did not finish")


def test_two_jobs_same_task_and_basename_isolated_history_recheck_restart(intake):
    settings, cvat, annotations, problems, cfg, requests = intake
    app = create_app(settings, cvat_client=cvat)
    with TestClient(app) as client:
        left, right = check_job(client), check_job(client, 10, "second-job")
        assert left["status"] == right["status"] == "partial", (left, right)
        a, b = left["result"]["api_prefix"], right["result"]["api_prefix"]
        assert a != b
        qa, qb = client.get(a + "/queue").json(), client.get(b + "/queue").json()
        assert qa["items"][0]["image_id"] == qb["items"][0]["image_id"] == "shared-basename"
        assert qa["items"][0]["cvat"]["job_id"] == 9 and qb["items"][0]["cvat"]["job_id"] == 10
        assert qa["items"][0]["cvat"]["frame"] == 0 and qb["items"][0]["cvat"]["frame"] == 1
        assert client.get(a + "/image/shared-basename/file").headers["content-type"] == "image/jpeg"
        context = client.get(a + "/web/context").json()
        assert not context["has_predictions"] and not context["has_spec"]
        assert context["method"] == "rule" and "edge_no_trunc" in context["active_checks"]
        payload = {
            "request_id": "verdict-lost-ack",
            "image_id": "shared-basename",
            "verdict": "false_alarm",
            "reviewer": "unit",
            "session_id": "a",
            "seconds_spent": 2,
            "queue_id": qa["queue_id"],
        }
        assert client.post(a + "/verdict", json=payload).json()["duplicate"] is False
        assert client.get(b + "/stats").json()["review_events"] == 0
        captured = client.get(a + "/image/shared-basename/saved").json()
        annotations[9]["version"] = 2
        annotations[9]["shapes"][0]["points"][0] = 150
        assert (
            client.post(
                a + "/image/shared-basename/recheck",
                json={
                    "request_id": "stale",
                    "snapshot_id": captured["snapshot_id"],
                    "queue_id": qa["queue_id"],
                },
            ).status_code
            == 409
        )
        captured = client.get(a + "/image/shared-basename/saved").json()
        rechecked = client.post(
            a + "/image/shared-basename/recheck",
            json={
                "request_id": "new-saved",
                "snapshot_id": captured["snapshot_id"],
                "queue_id": qa["queue_id"],
            },
        )
        assert rechecked.status_code == 200, rechecked.text
        assert rechecked.json()["risk_before"] > rechecked.json()["risk_after"]
        assert client.get(b + "/queue").json()["queue_id"] == qb["queue_id"]
        updated = check_job(client, request_id="after-save")
        assert updated["status"] == "partial", updated
        assert client.post(a + "/verdict", json=payload).json()["duplicate"] is True
        history = client.get(a + "/web/review/shared-basename", params={"queue_id": qa["queue_id"]})
        assert history.status_code == 200
        assert history.json()["annotations"][0]["box"][0] == 0
        app.state.job_registry.pool.shutdown(wait=True)
    restarted = TestClient(create_app(settings, cvat_client=cvat))
    assert restarted.post(a + "/verdict", json=payload).json()["duplicate"] is True
    assert restarted.get(a + "/stats", params={"queue_id": qa["queue_id"]}).json()["review_events"] == 1
    query = {"cvat_origin": "http://localhost:8080", "task_id": 8, "job_id": 9}
    status = restarted.get("/intake/status", params=query).json()
    assert status["ready"] and not status["needs_check"]
    before = len(requests)
    assert restarted.post("/intake/check", json={**query, "request_id": "after-save"}).status_code == 202
    assert len(requests) == before


def test_missing_permissions_wrong_origin_task_reused_request_and_failure_retry(intake):
    settings, cvat, annotations, problems, cfg, requests = intake
    app = create_app(settings, cvat_client=cvat)
    client = TestClient(app)
    base = {"cvat_origin": settings.cvat_url, "task_id": 8, "job_id": 9}
    assert (
        client.get("/intake/status", params={**base, "cvat_origin": "http://evil.invalid"}).status_code == 403
    )
    assert client.get("/intake/status", params={**base, "task_id": 99}).status_code == 403
    problems["failure"] = True
    failed = check_job(client)
    assert failed["status"] == "failed"
    assert client.get("/intake/status", params=base).json()["ready"] is False
    assert (
        client.post("/intake/check", json={**base, "job_id": 10, "request_id": "intake-test"}).status_code
        == 409
    )
    problems["failure"] = False
    assert check_job(client)["status"] == "partial"
    problems["changed"] = True
    assert check_job(client, request_id="changed-during-read")["status"] == "failed"
    assert client.get("/intake/status", params=base).json()["ready"]
    problems["changed"] = False
    problems["denied"] = True
    assert client.get("/intake/status", params=base).status_code == 409
    app.state.job_registry.pool.shutdown(wait=True)


@pytest.mark.parametrize(
    "problem,value",
    [("dimension", "3d"), ("width", 800), ("step", True), ("deleted", True), ("duplicate", True)],
)
def test_unsupported_metadata_is_rejected_without_mapping_guess(intake, problem, value):
    settings, cvat, annotations, problems, cfg, requests = intake
    problems[problem] = value
    with pytest.raises((IntakeError, ValueError)):
        JobReader(settings.cvat_url, cvat, cfg).describe(8, 9)


def test_server_namespaces_and_durable_request_resume(intake):
    settings, cvat, annotations, problems, cfg, requests = intake
    assert workspace_key("http://localhost:8080", 8, 9) != workspace_key("https://other.example", 8, 9)
    app = create_app(settings, cvat_client=cvat)
    registry = app.state.job_registry
    registry.schedule = lambda request_id: None  # Simulate process exit before the queued worker starts.
    value = {"cvat_origin": settings.cvat_url, "task_id": 8, "job_id": 9, "request_id": "restart-job"}
    assert TestClient(app).post("/intake/check", json=value).json()["status"] == "queued"
    restarted = TestClient(create_app(settings, cvat_client=cvat))
    assert check_job(restarted, request_id="restart-job")["status"] == "partial"
    registry.pool.shutdown(wait=True)
