"""Reviewer onboarding keeps operator policy on the backend and retries durable."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_web_review import web_settings as web_settings

from src.api.main import create_app
from src.api.presentation import display_reason
from src.api.settings import Settings


def test_start_is_idempotent_after_restart_and_keeps_operator_scope(web_settings):
    web_settings.review_order = "file"
    web_settings.review_batch = "prepared-batch"
    value = {"request_id": str(uuid4()), "reviewer": " Tú Anh "}
    with TestClient(create_app(web_settings)) as client:
        assert client.get("/review/workspace").json()["order"] == "file"
        result = client.post("/review/start", json=value)
        assert result.status_code == 200
        session = result.json()
        assert session["reviewer"] == "Tú Anh"
        assert session["batch"] == "prepared-batch" and session["order"] == "file"
        assert session["session_id"].startswith("review-")
        assert client.app.state.store.records() == []
        assert client.post("/review/start", json={**value, "reviewer": "Khác"}).status_code == 409
        for field in ("batch", "session_id", "order", "apiUrl", "guideline_url"):
            assert client.post("/review/start", json={**value, field: "override"}).status_code == 422
    # Changed defaults apply to new sessions only; a lost response/restart cannot change the scope.
    web_settings.review_order = "priority"
    with TestClient(create_app(web_settings)) as client:
        assert client.post("/review/start", json=value).json() == session
        new = client.post("/review/start", json={**value, "request_id": str(uuid4())}).json()
        assert new["session_id"] != session["session_id"] and new["order"] == "priority"
        assert str(web_settings.database) not in str(client.get("/review/workspace").json())


def test_start_cannot_bypass_pilot_registration(web_settings, tmp_path):
    web_settings.pilot_arm_file = tmp_path / "pilot.json"
    with TestClient(create_app(web_settings)) as client:
        assert not client.get("/review/workspace").json()["local_start_allowed"]
        assert client.post("/review/start", json={
            "reviewer": "Không tự đăng ký pilot", "request_id": str(uuid4()),
        }).status_code == 409
        assert client.app.state.store.state_items("review-start:") == {}


def test_operator_configuration_is_validated_and_reviewer_cannot_send_paths(web_settings):
    for address in ("https://outside.test", "http://name:password@localhost:8010", "file:///etc/passwd"):
        with pytest.raises(ValueError, match="guideline_url"):
            Settings(guideline_url=address)
    with pytest.raises(ValueError, match="review_order"):
        Settings(review_order="anything")
    with TestClient(create_app(web_settings)) as client:
        for value in ({"reviewer": " "}, {"reviewer": "X", "request_id": "not-a-uuid"}):
            assert client.post("/review/start", json=value).status_code == 422


def test_plain_explanations_preserve_numbers_and_source_reason(web_settings):
    source = "Box car #3 lệch so với model: IoU 0.56 < 0.70 (conf 0.76) (+5 chỗ khác)"
    assert display_reason(source) == "Box car #3 lệch so với máy: độ khớp 56% dưới 70% (+5 vị trí khác)"
    rule = "[R1] Box car cao 9px, ngưỡng 30px (tr.2)"
    assert display_reason(rule) == rule
    assert display_reason("Sai class: nhãn car → model truck (0.92)") == "Sai class: nhãn car → máy truck"
    with TestClient(create_app(web_settings)) as client:
        row = client.get("/queue").json()["items"][0]
        assert row["top_reasons"] == " | ".join(row["reasons"])
        assert row["display_reasons"] == [display_reason(r) for r in row["reasons"]]
        assert len(row["display_issues"]) == len(row["evidence"])

