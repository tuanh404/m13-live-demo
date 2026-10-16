"""CVAT job views never borrow another task's ranked images or review counts."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_review_api import payload
from test_review_api import setup_review as setup_review

from src.api.main import create_app


def test_job_queue_and_stats_preserve_original_ranks_and_history(setup_review):
    pd.DataFrame([
        ["image-01", 19, 20, 0], ["image-02", 19, 21, 1], ["image-03", 19, 20, 2],
    ], columns=["image_id", "task_id", "job_id", "frame"]).to_parquet(setup_review.mapping)
    scope = {"cvat_origin": "http://localhost:8080", "cvat_task_id": 19, "cvat_job_id": 20}
    with TestClient(create_app(setup_review)) as client:
        queue = client.get("/queue", params=scope).json()
        assert [r["rank"] for r in queue["items"]] == [1, 3]
        assert queue["total"] == 2
        assert queue["items"][1]["risk_score"] == 97  # No rescoring or rank renumbering.
        client.post("/verdict", json=payload(client, "image-01"))
        client.post("/verdict", json=payload(client, "image-02"))
        queue = client.get("/queue", params=scope).json()
        assert (queue["total"], queue["reviewed"], queue["remaining"]) == (2, 1, 1)
        stats = client.get("/stats", params=scope).json()
        assert stats["total_images"] == 2 and stats["reviewed_images"] == 1
        assert client.get("/stats").json()["reviewed_images"] == 2
        for other in ({"cvat_job_id": 99}, {"cvat_task_id": 99}, {"cvat_origin": "http://localhost:8081"}):
            result = client.get("/queue", params={**scope, **other}).json()
            assert result["items"] == [] and result["total"] == result["remaining"] == 0
    with TestClient(create_app(setup_review)) as client:
        assert client.get("/stats", params=scope).json()["reviewed_images"] == 1


@pytest.mark.parametrize("params", [
    {"cvat_task_id": 19}, {"cvat_task_id": -1, "cvat_job_id": 20, "cvat_origin": "http://localhost:8080"},
])
def test_incomplete_scope_is_not_treated_as_global(setup_review, params):
    with TestClient(create_app(setup_review)) as client:
        assert client.get("/queue", params=params).status_code == 422
        assert client.get("/stats", params=params).status_code == 422


def test_missing_mapping_does_not_fall_back_to_fixture(setup_review):
    with TestClient(create_app(setup_review)) as client:
        response = client.get("/queue", params={
            "cvat_task_id": 19, "cvat_job_id": 19, "cvat_origin": "http://localhost:8080",
        })
        assert response.status_code == 409
