import io
import json
import os
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient
from test_deployment_auth import secured as secured
from test_web_review import web_settings as web_settings

from src.api.main import create_app
from src.api.uploads import parse_zip, sample_zip
from src.config import load


@pytest.fixture
def upload_settings(secured):
    secured.uploads_enabled = True
    secured.guest_demo = True
    accounts = json.loads(secured.accounts_file.read_text())
    accounts["users"]["guest"] = dict(accounts["users"]["demo"])
    secured.accounts_file.write_text(json.dumps(accounts))
    return secured


def client_for(app):
    client = TestClient(app, base_url="http://localhost")
    assert client.post("/auth/demo", headers={"Origin": "http://localhost"}).status_code == 200
    return client


def send(client, raw):
    return client.post(
        "/my-batches/upload",
        content=raw,
        headers={"Origin": "http://localhost", "Content-Type": "application/zip"},
    )


def test_upload_computed_scores_scope_ownership_lost_ack_and_restart(upload_settings):
    app = create_app(upload_settings)
    a, b = client_for(app), client_for(app)
    raw = a.get("/my-batches/sample.zip").content
    result = send(a, raw)
    assert result.status_code == 200, result.text
    result = result.json()
    prefix = result["review_url"].rstrip("/")
    assert send(a, raw).json()["id"] == result["id"]
    assert len(a.get("/my-batches/list").json()["items"]) == 1
    assert b.get(prefix + "/").status_code == 404
    assert not b.get("/my-batches/list").json()["items"]
    identity = a.get("/auth/session", params={"upload_batch": result["id"]}).json()["identity"]
    query = {"reviewer": identity["reviewer"], "session_id": identity["session_id"], "order": "priority"}
    queue = a.get(prefix + "/queue", params=query).json()
    assert len(queue["items"]) == 3
    by_id = {r["image_id"]: r for r in queue["items"]}
    assert by_id["clean"]["risk_score"] == 0
    assert by_id["duplicate"]["risk_score"] > 0
    assert by_id["overlap"]["risk_score"] > 0
    context = a.get(prefix + "/web/context").json()
    assert not context["has_spec"] and not context["has_predictions"]
    assert "edge_no_trunc" not in context["active_checks"]
    detail = a.get(prefix + "/web/review/duplicate", params={"queue_id": queue["queue_id"]}).json()
    assert detail["evidence"] and detail["annotations"][0]["category"] == "car"
    assert a.get(prefix + detail["image_url"]).status_code == 200
    assert a.get(prefix + "/model").status_code == 404
    payload = dict(
        request_id="upload-lost-ack",
        image_id="duplicate",
        verdict="error",
        reviewer=identity["reviewer"],
        session_id=identity["session_id"],
        queue_id=queue["queue_id"],
        seconds_spent=1,
    )
    headers = {"Origin": "http://localhost"}
    assert a.post(prefix + "/verdict", json=payload, headers=headers).json()["duplicate"] is False
    assert a.post(prefix + "/verdict", json=payload, headers=headers).json()["duplicate"] is True
    assert a.get("/health").json()["queue_id"] != queue["queue_id"]
    restarted_app = create_app(upload_settings)
    restarted = TestClient(restarted_app, base_url="http://localhost")
    restarted.cookies.update(a.cookies)
    shutil.rmtree(app.state.uploads.root)
    assert restarted.post("/auth/new-review", headers=headers).status_code == 200
    assert restarted.get(prefix + "/queue", params=query).json()["remaining"] == 2
    assert restarted.get(prefix + "/stats", params=query).json()["review_events"] == 1
    assert send(restarted, raw).json()["reused"]
    assert restarted.post(prefix + "/verdict", json=payload, headers=headers).json()["duplicate"] is True
    other = send(b, raw).json()
    assert other["id"] != result["id"] and other["queue_id"] != result["queue_id"]
    assert (
        b.get(
            other["review_url"] + "queue",
            params={
                **query,
                "reviewer": b.get("/auth/session", params={"upload_batch": other["id"]}).json()["identity"][
                    "reviewer"
                ],
                "session_id": b.get("/auth/session", params={"upload_batch": other["id"]}).json()["identity"][
                    "session_id"
                ],
            },
        ).json()["remaining"]
        == 3
    )
    assert len(app.state.store.records()) == 1


@pytest.mark.parametrize(
    "change", ["traversal", "duplicate", "missing", "nan", "outside", "class", "polygon"]
)
def test_bad_zip_has_no_publication(upload_settings, change):
    app = create_app(upload_settings)
    client = client_for(app)
    with zipfile.ZipFile(io.BytesIO(sample_zip())) as z:
        files = {n: z.read(n) for n in z.namelist()}
    if change == "traversal":
        files["../evil.txt"] = b"x"
    elif change == "duplicate":
        files["images/clean.png"] = files["images/clean.jpg"]
    elif change == "missing":
        del files["labels/clean.txt"]
    else:
        files["labels/clean.txt"] = {
            "nan": b"0 nan .5 .2 .2",
            "outside": b"0 1 .5 .2 .2",
            "class": b"99 .5 .5 .2 .2",
            "polygon": b"0 .1 .2 .3 .4 .5",
        }[change]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    assert send(client, out.getvalue()).status_code == 422
    assert not client.get("/my-batches/list").json()["items"]


def test_yaml_classes_and_upload_only_body_limit(upload_settings):
    with zipfile.ZipFile(io.BytesIO(sample_zip())) as z:
        files = {n: z.read(n) for n in z.namelist() if n != "classes.txt"}
    files["data.yaml"] = b"names: {0: car, 1: truck}\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    assert len(parse_zip(out.getvalue(), load("upload"))[0]) == 3
    client = client_for(create_app(upload_settings))
    assert send(client, b"x" * (load("upload")["max_zip_bytes"] + 1)).status_code == 413
    assert (
        client.post("/verdict", content=b"x" * 40000, headers={"Origin": "http://localhost"}).status_code
        == 413
    )
    anonymous = TestClient(create_app(upload_settings), base_url="http://localhost")
    assert send(anonymous, sample_zip()).status_code == 401
    assert (
        client.post(
            "/my-batches/upload", content=sample_zip(), headers={"Origin": "https://wrong.test"}
        ).status_code
        == 403
    )


@pytest.mark.skipif(not os.getenv("M13_TEST_DATABASE_URL"), reason="requires isolated PostgreSQL")
def test_postgres_upload_restart_and_namespace_isolation(upload_settings, monkeypatch):
    from uuid import uuid4

    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    url = os.environ["M13_TEST_DATABASE_URL"]
    name = "m13_upload_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    upload_settings.database_url = make_conninfo(**{**conninfo_to_dict(url), "dbname": name})
    try:
        test_upload_computed_scores_scope_ownership_lost_ack_and_restart(upload_settings)
    finally:
        with psycopg.connect(url, autocommit=True) as db:
            db.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.mark.skipif(not os.getenv("M13_WEB_BROWSER_TESTS"), reason="requires browser opt-in")
def test_browser_upload_retry_all_verdicts_resume_and_private_list(upload_settings, tmp_path):
    import socket
    import threading

    import uvicorn
    from playwright.sync_api import expect, sync_playwright

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    upload_settings.public_origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
    app = create_app(upload_settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    worker.start()
    try:
        with sync_playwright() as p:
            chrome = p.chromium.launch(headless=True, executable_path=shutil.which("google-chrome"))
            context = chrome.new_context(viewport={"width": 1366, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(upload_settings.public_origin)
            expect(page.locator("#my-images")).to_be_visible()
            page.locator("#my-images").click()
            expect(page.locator("#batch-list li")).to_have_count(0)
            with page.expect_download() as download:
                page.get_by_role("link", name="Tải gói mẫu3ảnh để thử ngay").click()
            archive = tmp_path / "sample.zip"
            download.value.save_as(archive)
            page.locator("#archive").set_input_files(archive)

            def lost_ack(route):
                route.fetch()
                route.abort()

            page.route("**/my-batches/upload", lost_ack)
            page.locator("#upload-check").click()
            expect(page.locator("#upload-status")).to_contain_text("không tạo bộ trùng", timeout=15000)
            page.unroute("**/my-batches/upload")
            page.locator("#upload-check").click()
            expect(page.locator("#uploaded-review")).to_be_visible(timeout=15000)
            expect(page.locator("#upload-status")).to_contain_text("Đã mở lại bộ có sẵn")
            expect(page.locator("#batch-list li")).to_have_count(1)
            for width in (1366, 390):
                page.set_viewport_size({"width": width, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.set_viewport_size({"width": 1366, "height": 900})
            page.locator("#uploaded-review").click()
            review_url = page.url
            expect(page.locator("[data-verdict=error]")).to_be_enabled()
            expect(page.locator("#upload-review-scope")).to_be_visible()
            expect(page.locator("#data-kind")).to_have_text("Ảnh của bạn · Kiểm một phần")
            expect(page.locator("#cvat-tools")).to_be_hidden()
            for verdict in ("error", "false_alarm", "skip"):
                page.locator(f"[data-verdict={verdict}]").click()
            expect(page.locator("#progress")).to_contain_text("3/3")
            expect(page.locator("#stats")).to_contain_text("1 lỗi thật · 1 bot nhầm · 1 bỏ qua")
            page.reload()
            expect(page.locator("#progress")).to_contain_text("3/3")
            page.locator("a[data-upload-nav]").click()
            expect(page.locator("#batch-list li")).to_have_count(1)
            page.locator("#batch-list a").click()
            expect(page.locator("#progress")).to_contain_text("3/3")
            second = chrome.new_context().new_page()
            second.goto(upload_settings.public_origin + "/login")
            second.locator("#my-images").click()
            expect(second.locator("#list-status")).to_contain_text("Chưa có bộ ảnh")
            assert second.request.get(review_url).status == 404
            assert len(app.state.store.records()) == 3
            assert not errors
            chrome.close()
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        sock.close()


def test_quota_and_corrupt_snapshot_fail_closed(upload_settings):
    app = create_app(upload_settings)
    client = client_for(app)
    raw = sample_zip()
    item = send(client, raw).json()
    app.state.uploads.cfg["max_batches_per_session"] = 1
    alternate = io.BytesIO(raw)
    with zipfile.ZipFile(alternate, "a") as z:
        z.comment = b"another archive"
    assert send(client, alternate.getvalue()).status_code == 409
    assert send(client, raw).json()["reused"]
    with app.state.store.connection() as db:
        db.execute("UPDATE state SET value=? WHERE key=?", ("{}", "upload-assets:" + item["id"]))
    assert client.get(item["review_url"]).status_code == 503
    assert len(client.get("/my-batches/list").json()["items"]) == 1


def test_rejects_inflated_zip_and_wrong_dimensions():
    from fastapi import HTTPException
    from PIL import Image

    cfg = load("upload")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("images/a.jpg", b"x" * (cfg["max_unpacked_bytes"] + 1))
    with pytest.raises(HTTPException) as error:
        parse_zip(out.getvalue(), cfg)
    assert error.value.status_code == 422
    im = io.BytesIO()
    Image.new("RGB", (640, 480)).save(im, format="JPEG")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("images/a.jpg", im.getvalue())
        z.writestr("labels/a.txt", "")
        z.writestr("classes.txt", "car")
    with pytest.raises(HTTPException) as error:
        parse_zip(out.getvalue(), cfg)
    assert "1280" in error.value.detail


def test_upload_busy_is_retryable_without_writing(upload_settings):
    app = create_app(upload_settings)
    client = client_for(app)
    app.state.uploads.upload_gate.acquire()
    try:
        assert send(client, sample_zip()).status_code == 429
        assert not client.get("/my-batches/list").json()["items"]
    finally:
        app.state.uploads.upload_gate.release()
    assert send(client, sample_zip()).status_code == 200


def test_invalid_yaml_is_a_readable_validation_error(upload_settings):
    with zipfile.ZipFile(io.BytesIO(sample_zip())) as z:
        files = {n: z.read(n) for n in z.namelist() if n != "classes.txt"}
    files["data.yaml"] = b"names: [car, truck\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    client = client_for(create_app(upload_settings))
    response = send(client, out.getvalue())
    assert response.status_code == 422
    assert "Không đọc được" in response.json()["detail"]
    assert not client.get("/my-batches/list").json()["items"]
