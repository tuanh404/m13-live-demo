"""Human registration is mocked on temporary unit data only, never runtime pilot enrollment."""

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from test_recheck import setup_recheck as setup_recheck

from src.api.main import create_app
from src.api.saved_labels import SavedLabels, canonical
from src.api.service import QueueService
from src.api.store import ReviewStore


@pytest.fixture
def unit_pilot_app(setup_recheck):
    settings, state, _, cvat, _ = setup_recheck
    settings.data_purpose = "real"
    settings.pilot_images = 2  # Explicit unit-only small mocked dataset.
    service = QueueService(settings, ReviewStore(settings.database))
    reader = SavedLabels(settings, service, cvat)
    baseline = []
    photos = {}
    for image_id in ["image-1", "image-2"]:
        image = settings.images / (image_id + ".png")
        Image.new("RGB", (1280, 720), "gray").save(image)
        photos[image_id] = hashlib.sha256(image.read_bytes()).hexdigest()
        payload = reader.capture(image_id)["payload"]
        baseline.append(
            {
                "image_id": image_id,
                "boxes": sorted(
                    [{k: b[k] for k in ("category", "box", "attributes")} for b in payload["boxes"]],
                    key=canonical,
                ),
            }
        )
    arm = settings.images / "unit-pair/file/pilot-arm.json"
    arm.parent.mkdir(parents=True)
    arm.write_text(
        json.dumps(
            {
                "purpose": "real",
                "setup_frozen": True,
                "n_images": 2,
                "order": "file",
                "comparison_id": "AUTOMATED-UNIT-ONLY",
                "queue_id": service.snapshot()[1],
                "mapping_sha256": hashlib.sha256(settings.mapping.read_bytes()).hexdigest(),
                "annotation_baseline_sha256": hashlib.sha256(canonical(baseline)).hexdigest(),
                "photo_sha256": photos,
                "peer_database": str(arm.parent.parent / "priority/review.db"),
            }
        )
    )
    settings.pilot_arm_file = arm
    return create_app(settings, cvat_client=cvat), state


def test_session_binding_preview_feedback_and_real_controls_on_unit_mock(unit_pilot_app):
    app, state = unit_pilot_app
    client = TestClient(app)
    assert client.get("/queue").status_code == 403
    response = client.post(
        "/pilot/register",
        json={
            "reviewer": "AUTOMATED UNIT FIXTURE",
            "request_id": "73339541-12dc-4b95-a46d-c5fde4541f39",
            "is_human": True,
            "unseen_batch": True,
            "follow_protocol": True,
        },
    )
    assert response.status_code == 200
    value = response.json()
    retry = client.post(
        "/pilot/register",
        json={
            "reviewer": "AUTOMATED UNIT FIXTURE",
            "request_id": "73339541-12dc-4b95-a46d-c5fde4541f39",
            "is_human": True,
            "unseen_batch": True,
            "follow_protocol": True,
        },
    )
    assert retry.status_code == 200 and retry.json()["session"] == value["session"]
    assert len(app.state.store.state_items("pilot:")) == 1
    client.headers["X-M13-Pilot-Session"] = value["token"]
    session = value["session"]
    assert client.get("/queue?order=priority").status_code == 403
    assert client.get("/queue?order=file").status_code == 200
    assert client.get("/pilot/status").json()["session"]["order"] == "file"
    data = {
        "reviewer": session["reviewer"],
        "session_id": session["session_id"],
        "review_order": "file",
        "verdict": "error",
        "seconds_spent": 1,
        "note": "AUTOMATED UNIT ONLY",
    }
    assert (
        client.post("/verdict", json={**data, "image_id": "image-1", "reviewer": "wrong"}).status_code == 403
    )
    feedback = {"request_id": "unit-feedback", "clarity": 4, "confusing": "UNIT ONLY"}
    assert client.post("/pilot/feedback", json=feedback).status_code == 409
    for n in [1, 2]:
        assert (
            client.post(
                "/verdict", json={**data, "image_id": f"image-{n}", "request_id": f"unit-{n}"}
            ).status_code
            == 200
        )
    assert client.post("/pilot/feedback", json=feedback).json()["status"] == "saved"
    assert client.post("/pilot/feedback", json=feedback).json()["duplicate"]
    assert client.post("/retrain").status_code == 409
