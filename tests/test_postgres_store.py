"""Opt-in real PostgreSQL integration; no mocks can satisfy these checks."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_deployment_auth import login
from test_deployment_auth import secured as secured
from test_web_review import web_settings as web_settings

from src.api.main import create_app
from src.api.store import DuplicateSubmission, ReviewStore

pytestmark = pytest.mark.skipif(not os.getenv("M13_TEST_DATABASE_URL"), reason="real PostgreSQL URL required")


@pytest.fixture
def pg_url():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    base = os.environ["M13_TEST_DATABASE_URL"]
    name = "m13_test_" + uuid4().hex
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    kwargs = conninfo_to_dict(base)
    kwargs["dbname"] = name
    yield make_conninfo(**kwargs)
    with psycopg.connect(base, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_real_postgres_concurrent_retry_conflict_append_only_and_restart(pg_url, tmp_path):
    import psycopg

    store = ReviewStore(tmp_path / "unused.db", pg_url)
    payload = dict(
        request_id="lost-ack",
        image_id="image-1",
        verdict="error",
        reviewer="unit",
        session_id="session-1",
        review_order="priority",
        seconds_spent=2,
        obj_ids=[],
        note=None,
        batch_id=None,
        queue_id="queue",
        model_version="rule-v1",
        rank=1,
    )
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(workers.map(lambda _: store.append(payload, is_audit=False), range(8)))
    assert sum(not duplicate for _, duplicate in results) == 1
    assert len({row["id"] for row, _ in results}) == 1
    with pytest.raises(DuplicateSubmission):
        store.append({**payload, "verdict": "skip"}, is_audit=False)
    store.states({"test:one": {"a": 1}, "test:two": {"b": 2}, "other": {"c": 3}})
    restarted = ReviewStore(tmp_path / "also-unused.db", pg_url)
    assert restarted.append(payload, is_audit=False)[1]
    assert len(restarted.state_items("test:")) == 2
    with pytest.raises(psycopg.Error, match="append-only"), restarted.connection() as db:
        db.execute("DELETE FROM verdicts")
    assert len(restarted.records(reviewer="unit")) == 1
    assert not (tmp_path / "unused.db").exists()


def test_real_postgres_auth_queue_verdict_persistence_without_local_files(pg_url, secured):
    secured.database_url = pg_url
    client = TestClient(create_app(secured), base_url="http://localhost")
    assert login(client).status_code == 200
    who = client.get("/auth/session").json()["identity"]
    query = {"reviewer": who["reviewer"], "session_id": who["session_id"], "order": "priority"}
    queue = client.get("/queue", params=query).json()
    payload = {
        "request_id": "pg-auth-ack",
        "image_id": queue["items"][0]["image_id"],
        "verdict": "skip",
        "reviewer": who["reviewer"],
        "session_id": who["session_id"],
        "seconds_spent": 3,
    }
    assert client.post("/verdict", headers={"Origin": "http://localhost"}, json=payload).status_code == 200
    restarted = TestClient(create_app(secured), base_url="http://localhost")
    restarted.cookies.update(client.cookies)
    assert restarted.get("/auth/session").json()["authenticated"]
    assert restarted.get("/stats", params=query).json()["review_events"] == 1
    assert restarted.post("/verdict", headers={"Origin": "http://localhost"}, json=payload).json()[
        "duplicate"
    ]
    assert not secured.database.is_file()
    assert "postgres" not in json.dumps(restarted.get("/auth/session").json()).lower()
