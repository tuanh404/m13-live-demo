"""Optional real Chromium MV3 + API test. CVAT page is explicitly a fixture."""

import asyncio
import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pandas as pd
import pytest
from fastapi.responses import HTMLResponse, JSONResponse
from test_recheck import fixture_backend
from test_recheck import setup_recheck as setup_recheck

pytestmark = pytest.mark.skipif(os.environ.get("M13_BROWSER_TESTS") != "1", reason="set M13_BROWSER_TESTS=1")


def installed_extension(tmp_path, api_url):
    extension = tmp_path / "installed-extension"
    shutil.copytree(Path("extension").resolve(), extension)
    (extension / "connection.json").write_text(json.dumps({"apiUrl": api_url}))
    return extension


def test_mv3_real_api_focus_retry_and_all_verdicts(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    browser = pytest.importorskip("playwright.sync_api")
    image_module = pytest.importorskip("PIL.Image")
    from src.api.main import create_app
    from src.api.settings import Settings
    from src.contracts import QUEUE_COLS

    images = tmp_path / "images"
    images.mkdir()
    for i in range(3):
        image_module.new("RGB", (1280, 720), (50, 100, 140)).save(images / f"fixture-{i}.png")
    queue = tmp_path / "ranked_queue_fixture.csv"
    pd.DataFrame(
        [
            [
                f"fixture-{i}", 0, i + 1, f"[R1] FIXTURE: cao {15 + i}px (tr.1)",
                "manual-unscored-browser-fixture",
            ]
            for i in range(3)
        ],
        columns=QUEUE_COLS,
    ).to_csv(queue, index=False)
    mapping = tmp_path / "map.parquet"
    pd.DataFrame(
        [[f"fixture-{i}", 1, 2, i] for i in range(3)], columns=["image_id", "task_id", "job_id", "frame"]
    ).to_parquet(mapping, index=False)
    evidence = tmp_path / "evidence_fixture.jsonl"
    evidence.write_text(
        "\n".join(
            json.dumps(
                {
                    "image_id": f"fixture-{i}",
                    "boxes": [
                        {
                            "obj_id": str(i),
                            "box": [10, 20, 200, 150],
                            "note": "Fixture box",
                            "signal": "fixture",
                        }
                    ],
                }
            )
            for i in range(3)
        )
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings = Settings(
        database=tmp_path / "review.db",
        images=images,
        mapping=mapping,
        predictions=tmp_path / "missing.parquet",
        reports=tmp_path,
        queue_file=queue,
        evidence_file=evidence,
        cvat_url=f"http://127.0.0.1:{port}",
        guideline_url=f"http://127.0.0.1:{port}/guideline-review",
    )
    app = create_app(settings)
    failures = []
    start_failures = []

    @app.middleware("http")
    async def ambiguous_response(request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path == "/verdict" and not failures:
            failures.append(True)
            return JSONResponse(
                {"detail": "Fixture: lost acknowledgement AFTER SQLite commit"}, status_code=503
            )
        if request.method == "POST" and request.url.path == "/review/start" and not start_failures:
            start_failures.append(True)
            return JSONResponse({"detail": "Fixture lost start acknowledgement"}, status_code=503)
        return response

    @app.get("/tasks/1/jobs/2")
    def cvat_fixture():
        return HTMLResponse("<h1>CVAT PAGE FIXTURE — not real annotation storage</h1>")

    @app.get("/guideline-review")
    def guideline_navigation_fixture():
        return HTMLResponse("<h1>GUIDELINE NAVIGATION FIXTURE</h1>")

    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        with browser.sync_playwright() as p:
            extension = installed_extension(tmp_path, f"http://127.0.0.1:{port}")
            context = p.chromium.launch_persistent_context(
                str(tmp_path / "chrome"),
                channel="chromium",
                headless=True,
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
            )
            worker = (
                context.service_workers[0]
                if context.service_workers
                else context.wait_for_event("serviceworker")
            )
            worker.evaluate(
                "cfg => chrome.storage.local.set({settings: cfg})",
                {
                    "apiUrl": "http://127.0.0.1:1",  # Stale URL left by an older installation.
                    "guidelineUrl": f"http://127.0.0.1:{port}/guideline-review",
                    "reviewer": "Browser fixture reviewer",
                    "batch": "",
                    "sessionId": "fixture-browser",
                    "order": "priority",
                },
            )
            panel = context.new_page()
            errors = []
            panel.on("pageerror", lambda err: errors.append(str(err)))
            panel.goto(worker.url.replace("/background.js", "/sidepanel.html"))
            panel.locator(".row").first.wait_for()
            assert panel.locator(".row").count() == 3
            effective = panel.evaluate("chrome.runtime.sendMessage({type:'SETTINGS'})")["value"]
            assert effective["apiUrl"] == f"http://127.0.0.1:{port}"
            assert effective["sessionId"] == "fixture-browser"
            assert panel.locator(".row strong").first.inner_text() == "[R1]"
            browser.expect(panel.locator(".row .rank").first).to_contain_text("Chưa chấm QC")
            browser.expect(panel.locator(".row .rank").first).not_to_contain_text("0.0 điểm")
            # Open/reuse the configured local page without changing review state.
            assert panel.locator("#api-url, #session, #batch, #order, #settings-form").count() == 0
            panel.locator("#identity-toggle").click()
            browser.expect(panel.locator("#identity input")).to_have_count(1)
            panel.locator("#identity-form button").click()
            browser.expect(panel.locator("#identity")).not_to_be_visible()
            settings_before = worker.evaluate("chrome.storage.local.get('settings')")["settings"]
            assert settings_before["guidelineUrl"] == f"http://127.0.0.1:{port}/guideline-review"
            panel.locator("#open-guideline").evaluate("el => el.closest('details').open = true")
            with context.expect_page() as guideline_page:
                panel.locator("#open-guideline").click()
            guideline = guideline_page.value
            guideline.wait_for_load_state()
            browser.expect(guideline.locator("h1")).to_have_text("GUIDELINE NAVIGATION FIXTURE")
            page_count = len(context.pages)
            panel.locator("#open-guideline").click()
            browser.expect(panel.locator("#open-guideline")).to_be_enabled()
            assert len(context.pages) == page_count
            assert worker.evaluate("chrome.storage.local.get('settings')")["settings"] == settings_before
            # A stale browser guideline setting cannot redirect the server-owned destination.
            worker.evaluate("cfg => chrome.storage.local.set({settings: cfg})",
                            {**settings_before, "guidelineUrl": "https://example.com"})
            panel.locator("#open-guideline").click()
            browser.expect(panel.locator("#open-guideline")).to_be_enabled()
            assert len(context.pages) == page_count
            worker.evaluate("cfg => chrome.storage.local.set({settings: cfg})", settings_before)
            with context.expect_page() as opened:
                panel.locator(".row").first.click()
            cvat = opened.value
            cvat.wait_for_load_state()
            panel.locator("#selected").wait_for(state="visible")
            browser.expect(panel.locator("#boxes")).to_have_attribute("width", "1280")
            assert cvat.url.endswith("/tasks/1/jobs/2?frame=0")
            cvat.bring_to_front()

            def clock():
                return panel.evaluate("chrome.runtime.sendMessage({type:'CLOCK'})")["value"]

            panel.wait_for_timeout(200)
            assert clock()["running"] is True
            # Real CVAT removes ?frame=0 from its URL. The displayed default is still frame zero.
            cvat.evaluate("history.replaceState(null, '', location.pathname)")
            cvat.wait_for_timeout(100)
            assert clock()["running"] is True
            before = clock()["seconds"]
            cvat.wait_for_timeout(150)
            assert clock()["seconds"] > before
            for frame in ("1", "invalid", ""):
                cvat.evaluate("f => history.replaceState(null, '', location.pathname + '?frame=' + f)", frame)
                cvat.wait_for_timeout(50)
                assert clock()["running"] is False
            cvat.evaluate("history.replaceState(null, '', location.pathname + '?frame=0')")
            cvat.wait_for_timeout(50)
            assert clock()["running"] is True
            extra = context.new_page()
            extra.goto("about:blank")
            extra.bring_to_front()
            first = clock()
            assert first["running"] is False
            panel.wait_for_timeout(100)
            assert clock()["seconds"] == first["seconds"]
            panel.bring_to_front()
            panel.locator('[data-verdict="error"]').click()
            panel.locator("#retry").wait_for(state="visible")
            uncertain = worker.evaluate("chrome.storage.local.get('review')")["review"]
            browser.expect(panel.locator("#identity-toggle")).to_be_disabled()
            denied = panel.evaluate("chrome.runtime.sendMessage({type:'START_REVIEW',reviewer:'Other'})")
            assert denied["ok"] is False
            assert len(app.state.store.records()) == 1
            assert panel.locator(".row").count() == 3  # UI has not claimed saved after lost acknowledgement.
            panel.locator("#retry").click()
            browser.expect(panel.locator(".row")).to_have_count(2)
            assert len(app.state.store.records()) == 1
            for key, expected in [("2", "false_alarm"), ("3", "skip")]:
                panel.locator(".row").first.click()
                panel.locator("#selected").wait_for(state="visible")
                panel.keyboard.press(key)
                panel.locator("#selected").wait_for(state="hidden")
                assert app.state.store.records()[-1]["verdict"] == expected
            browser.expect(panel.locator(".row")).to_have_count(0)
            assert len(app.state.store.records()) == 3
            panel.get_by_text("Thống kê phiên", exact=True).click()
            browser.expect(panel.locator("#stats")).to_contain_text("3 ảnh")
            # Clean install: the reviewer only supplies a name. Backend chooses the order/session.
            settings.review_order = "file"
            worker.evaluate("cfg=>chrome.storage.local.set({settings:cfg,review:null})",
                            {"apiUrl": f"http://127.0.0.1:{port}"})
            panel.reload()
            browser.expect(panel.locator("#identity")).to_be_visible()
            browser.expect(panel.locator(".row")).to_have_count(0)
            panel.locator("#reviewer").fill("New fixture reviewer")
            panel.locator("#identity-form button").click()
            browser.expect(panel.locator("#error")).to_be_visible()
            attempt = worker.evaluate("chrome.storage.local.get('startAttempt')")["startAttempt"]
            panel.reload()
            panel.locator("#reviewer").fill("New fixture reviewer")
            panel.locator("#identity-form button").click()
            browser.expect(panel.locator("#identity")).not_to_be_visible()
            browser.expect(panel.locator(".row")).to_have_count(3)
            new = worker.evaluate("chrome.storage.local.get('settings')")["settings"]
            assert new["order"] == "file"
            assert new["sessionId"] == "review-" + attempt["request_id"].replace("-", "")
            assert len(app.state.store.state_items("review-start:")) == 1
            panel.reload()
            browser.expect(panel.locator(".row")).to_have_count(3)
            assert worker.evaluate("chrome.storage.local.get('settings')")["settings"] == new
            assert len(app.state.store.records()) == 3  # Onboarding never fabricates a verdict.
            panel.locator("#new-review").evaluate("el=>el.closest('details').open=true")
            panel.once("dialog", lambda dialog: dialog.accept())
            panel.locator("#new-review").click()
            browser.expect(panel.locator("#new-review")).to_be_enabled()
            renewed = worker.evaluate("chrome.storage.local.get('settings')")["settings"]
            assert renewed["sessionId"] != new["sessionId"]
            assert len(app.state.store.records()) == 3
            assert len(app.state.store.state_items("review-start:")) == 2
            # Never move an uncertain write to a newly configured backend.
            uncertain["apiOrigin"] = "http://127.0.0.1:1"
            worker.evaluate("value=>chrome.storage.local.set({review:value})", uncertain)
            pinned = panel.evaluate("chrome.runtime.sendMessage({type:'SAVE_VERDICT',verdict:'error'})")
            assert pinned["ok"] is False and "dịch vụ cũ" in pinned["error"]
            preserved = worker.evaluate("chrome.storage.local.get('review')")["review"]
            assert preserved["pending"] == uncertain["pending"]
            assert len(app.state.store.records()) == 3
            assert not errors
            context.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


def test_mv3_saved_labels_recheck_and_lost_acknowledgement(setup_recheck, tmp_path):
    """Real Chrome/API; CVAT and score computation are deliberately fixtures."""
    uvicorn = pytest.importorskip("uvicorn")
    browser = pytest.importorskip("playwright.sync_api")
    image_module = pytest.importorskip("PIL.Image")
    from src.api.main import create_app

    settings, annotations, _, cvat_client, _ = setup_recheck
    # Nonconsecutive server IDs must stay internal; the per-image list uses
    # CVAT's persisted order, independently of string/numeric ID sorting.
    annotations["shapes"][0]["id"] = 16
    annotations["shapes"].append({**annotations["shapes"][0], "id": 2, "points": [100, 20, 130, 50]})
    image_module.new("RGB", (1280, 720), (80, 100, 120)).save(tmp_path / "image-1.png")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings.cvat_url = f"http://127.0.0.1:{port}"
    app = create_app(settings, cvat_client=cvat_client)
    lost = []
    hold, entered = threading.Event(), threading.Event()
    requests = []

    @app.get("/tasks/4/jobs/6")
    @app.get("/tasks/99/jobs/99")
    def page_fixture():
        return HTMLResponse(
            "<h1>CVAT fixture — saved boxes supplied by mock REST</h1>"
            "<button id='canvas'>Canvas fixture</button>"
            "<a id='frame-next' onclick=\"history.pushState(null,'','?frame=1')\">Frame 1</a>"
            "<script>window.keys=[];document.addEventListener('keydown',e=>keys.push(e.key));</script>"
        )

    @app.middleware("http")
    async def lose_recheck_ack(request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path.endswith("/recheck"):
            requests.append(True)
            if hold.is_set():
                entered.set()
                while hold.is_set():
                    await asyncio.sleep(0.02)
            if not lost:
                lost.append(True)
                return JSONResponse({"detail": "Fixture lost acknowledgement"}, status_code=503)
        return response

    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        with browser.sync_playwright() as p:
            extension = installed_extension(tmp_path, settings.cvat_url)
            context = p.chromium.launch_persistent_context(
                str(tmp_path / "chrome"),
                channel="chromium",
                headless=True,
                args=[f"--disable-extensions-except={extension}", f"--load-extension={extension}"],
            )
            worker = (
                context.service_workers[0]
                if context.service_workers
                else context.wait_for_event("serviceworker")
            )
            worker.evaluate(
                "cfg => chrome.storage.local.set({settings: cfg})",
                {
                    "apiUrl": settings.cvat_url,
                    "reviewer": "Automated fixture",
                    "batch": "",
                    "sessionId": "automated-recheck-fixture",
                    "order": "priority",
                },
            )
            panel = context.new_page()
            errors = []
            panel.on("pageerror", lambda err: errors.append(str(err)))
            panel.goto(worker.url.replace("/background.js", "/sidepanel.html"))
            panel.locator(".row").first.click()
            panel.locator("#selected").wait_for(state="visible")
            panel.locator("#run-qc").click()
            browser.expect(panel.locator("#error")).to_contain_text("Chưa thể kiểm tra lại")
            assert requests == []  # Read-only backend cannot manufacture a score.
            panel.locator("#annotation-details summary").first.click()
            panel.locator("#read-saved").click()
            browser.expect(panel.locator("#saved-status")).to_contain_text("Điểm chưa thay đổi")
            browser.expect(panel.locator("#recheck")).to_be_disabled()
            browser.expect(panel.locator("#saved-labels")).to_contain_text("10.0, 20.0, 30.0, 50.0")
            browser.expect(panel.locator("#saved-labels li")).to_have_text([
                "Box 1 · car · [10.0, 20.0, 30.0, 50.0]",
                "Box 2 · car · [100.0, 20.0, 130.0, 50.0]",
            ])
            # Simulates a Save in the fixture REST store, not a detector prediction.
            annotations["shapes"][0]["points"] = [70, 20, 90, 50]
            annotations["version"] += 1
            app.state.rechecks.backend = fixture_backend
            panel.locator("#read-saved").click()
            browser.expect(panel.locator("#saved-labels")).to_contain_text("70.0, 20.0, 90.0, 50.0")
            browser.expect(panel.locator("#recheck")).to_be_enabled()
            panel.locator("#recheck").click()
            browser.expect(panel.locator("#status")).to_contain_text("80.0 → 70.0 điểm")
            assert len(lost) == 1
            state = worker.evaluate("chrome.storage.local.get('review')")["review"]
            assert state["recheckPending"] is None and state["detail"]["evidence"][0]["box"][0] == 70
            assert app.state.store.records() == []  # Recheck never invents a verdict.
            panel.locator('[data-verdict="error"]').click()
            panel.locator("#selected").wait_for(state="hidden")
            assert len(app.state.store.records()) == 1
            assert app.state.store.records()[0]["model_version"].startswith("recheck-")
            assert not errors
            # Embedded overlay: actual Chrome iframe/worker, mock CVAT annotations.
            worker.evaluate(
                "cfg => chrome.storage.local.set({settings:cfg,review:null})",
                {"apiUrl": settings.cvat_url, "reviewer": "Automated overlay", "batch": "",
                 "sessionId": "fixture-overlay", "order": "priority"},
            )
            cvat = next(page for page in context.pages if "/tasks/4/jobs/6" in page.url)
            cvat.bring_to_front()
            board = cvat.locator("#m13-qc-host #board")
            browser.expect(cvat.locator("#m13-qc-host button")).to_have_count(0)
            browser.expect(board).not_to_be_visible()
            origin_errors = []
            cvat.on("console", lambda message: origin_errors.append(message.text)
                    if 'postMessage' in message.text and 'origin' in message.text else None)

            def toolbar_toggle():
                worker.evaluate("""async()=>{
                    const tabs=await chrome.tabs.query({});
                    const tab=tabs.find(t=>t.url.includes('/tasks/4/jobs/6'));
                    await toggleFromToolbar(tab);
                }""")

            toolbar_toggle()  # Invoke the exact handler registered by chrome.action.onClicked.
            embedded = cvat.frame_locator("#m13-qc-host iframe")
            embedded.locator('.row[data-image-id="image-1"]').click()
            browser.expect(embedded.locator("#selected")).to_be_visible()
            assert embedded.locator("#close-panel").count() == 0
            # Dense evidence must not push the verdict controls outside the iframe viewport.
            embedded.locator("body").evaluate("""async()=>{
                const box=selected.evidence[0];
                await showDetail({...selected,evidence:Array.from({length:30},()=>({...box}))});
                document.getElementById('evidence-details').open=true;
                document.querySelector('main').scrollTop=0;
            }""")
            assert embedded.locator("body").evaluate("el=>parseFloat(getComputedStyle(el).fontSize)") == 14
            assert embedded.locator("#review-footer").evaluate(
                "el=>{const b=el.getBoundingClientRect();return b.top>=0&&b.bottom<=innerHeight;}"
            )
            for button in embedded.locator("[data-verdict]").all():
                assert button.evaluate(
                    "el=>{const b=el.getBoundingClientRect();return b.left>=0&&b.right<=innerWidth;}"
                )
            # Clicks/keyboard outside the panel belong to CVAT and never submit verdicts.
            cvat.locator("#canvas").click()
            cvat.keyboard.press("2")
            assert cvat.evaluate("keys.includes('2')")
            assert len(app.state.store.records()) == 1
            browser.expect(board).to_be_visible()
            def clock():
                return embedded.locator("body").evaluate(
                    "async()=> (await chrome.runtime.sendMessage({type:'CLOCK'})).value"
                )
            assert clock()["running"] is True
            cvat.locator("#frame-next").click()
            browser.expect(board).to_be_visible()
            assert clock()["running"] is False
            cvat.evaluate("history.replaceState(null,'','?frame=12')")
            cvat.locator("#canvas").click()
            cvat.wait_for_timeout(100)  # Chrome's tabs URL event follows history updates.
            assert clock()["running"] is True
            embedded.locator("#annotation-details > summary").click()
            embedded.locator("#note").fill("overlay fixture")
            assert clock()["running"] is False  # Panel focus is not CVAT review time.
            annotations["shapes"][0]["points"] = [80, 20, 95, 50]
            annotations["version"] += 1
            hold.set()
            before_requests = len(requests)
            embedded.locator("#run-qc").click()
            assert entered.wait(timeout=10)
            durable = worker.evaluate("chrome.storage.local.get('review')")["review"]["recheckPending"]
            assert durable
            toolbar_toggle()
            browser.expect(board).not_to_be_visible()
            toolbar_toggle()
            browser.expect(board).to_be_visible()
            restored = worker.evaluate("chrome.storage.local.get('review')")["review"]
            assert restored["recheckPending"] == durable
            assert cvat.locator("#m13-qc-host").count() == 1
            cvat.reload()
            browser.expect(cvat.locator("#m13-qc-host #board")).to_be_visible()
            hold.clear()
            embedded = cvat.frame_locator("#m13-qc-host iframe")
            browser.expect(embedded.locator("#risk-score")).to_have_text("80.0/100")
            browser.expect(embedded.locator("#result-summary")).to_contain_text("70.0 → 80.0")
            assert len(requests) == before_requests + 1
            assert len(app.state.store.records()) == 1
            # Only the Chrome action toggles; no floating shortcut returns after reload.
            toolbar_toggle()
            browser.expect(cvat.locator("#m13-qc-host #board")).not_to_be_visible()
            cvat.locator("#canvas").click()
            cvat.reload()
            browser.expect(cvat.locator("#m13-qc-host button")).to_have_count(0)
            browser.expect(cvat.locator("#m13-qc-host #board")).not_to_be_visible()
            assert not origin_errors
            # A different open task/job must never show the prepared fixture queue.
            other = context.new_page()
            other.goto(f"{settings.cvat_url}/tasks/99/jobs/99")
            worker.evaluate("""async()=>{
                const tabs=await chrome.tabs.query({});
                await toggleFromToolbar(tabs.find(t=>t.url.includes('/tasks/99/jobs/99')));
            }""")
            other_panel = other.frame_locator("#m13-qc-host iframe")
            browser.expect(other_panel.locator("#status")).to_contain_text("chưa có hàng đợi QC")
            browser.expect(other_panel.locator("#job-context")).to_have_text("Task 99 · Job 99")
            browser.expect(other_panel.locator(".row")).to_have_count(0)
            browser.expect(other_panel.locator("#selected")).not_to_be_visible()
            attempt = other_panel.locator("body").evaluate("""async () => {
                const queue=await chrome.runtime.sendMessage({type:'API',path:'/queue'});
                return chrome.runtime.sendMessage({type:'OPEN_IMAGE',imageId:'image-1',
                    queueId:queue.value.queue_id});
            }""")
            assert attempt["ok"] is False and "không thuộc job" in attempt["error"]
            assert other.url.endswith("/tasks/99/jobs/99")
            assert len(app.state.store.records()) == 1
            context.close()
    finally:
        hold.clear()
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
