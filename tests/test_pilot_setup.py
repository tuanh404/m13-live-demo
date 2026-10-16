import json

import pytest
from fastapi.testclient import TestClient
from test_recheck import setup_recheck as setup_recheck

from src.api.fixtures import prepare_scored
from src.api.main import create_app
from src.api.pilot_setup import check_pair, prepare_pair
from src.api.review_setup import prepare
from src.api.settings import Settings


def test_pair_isolated_and_fixture_enrollment_preview_blocked(tmp_path):
    raw = tmp_path / "source"
    prepare_scored(raw, count=40)
    source = tmp_path / "pilot-source"
    prepare(
        raw / "source/ranked_queue_rule-fixture-qc-v1.csv",
        raw / "images",
        source,
        source_root=raw,
        limit=30,
        role="pilot",
    )
    pair = tmp_path / "pair"
    prepare_pair(source, pair)
    report = check_pair(pair)
    assert report["same_queue_labels_photos"] and not report["setup_ready"]
    assert not report["human_eligible"] and not report["human_pilot_complete"]
    with pytest.raises(ValueError, match="đã có"):
        prepare_pair(source, pair)
    arm = pair / "priority"
    settings = Settings(
        queue_file=arm / "ranked_queue_rule-fixture-qc-v1.csv",
        images=arm / "images",
        database=arm / "review.db",
        mapping=arm / "cvat_map.parquet",
        pilot_arm_file=arm / "pilot-arm.json",
    )
    app = create_app(settings)
    client = TestClient(app)
    status = client.get("/pilot/status").json()
    assert status["configured"] and not status["eligible"]
    assert "image_ids" not in status
    assert client.get("/queue").status_code == 403
    assert client.get("/image/fixture-qc-01/file").status_code == 403
    assert client.get("/web/review/fixture-qc-01?queue_id=x").status_code == 403
    assert (
        client.post(
            "/pilot/register",
            json={
                "reviewer": "AUTOMATED UNIT FIXTURE",
                "is_human": True,
                "unseen_batch": True,
                "follow_protocol": True,
            },
        ).status_code
        == 409
    )
    assert app.state.store.state_items("pilot:") == {}
    descriptor = json.loads((arm / "pilot-arm.json").read_text())
    assert descriptor["setup_frozen"] is False


def test_pilot_requires_configured_image_count_and_detects_annotation_drift(setup_recheck):
    from test_pilot import enroll, verdict

    from src.api.pilot import PilotPlan, register

    settings, state, _, cvat, _ = setup_recheck
    settings.data_purpose = "real"
    with pytest.raises(ValueError, match="30"):
        register(
            PilotPlan(reviewer="UNIT FIXTURE", session_id="unit", comparison_id="unit", order="file"),
            confirmed=True,
            settings=settings,
        )
    enroll(settings, cvat)
    client = TestClient(create_app(settings, cvat_client=cvat))
    state["version"] += 1
    state["shapes"][0]["points"][0] += 1
    response = client.post("/verdict", json=verdict())
    assert response.status_code == 409 and "Nhãn pilot đã đổi" in response.text


