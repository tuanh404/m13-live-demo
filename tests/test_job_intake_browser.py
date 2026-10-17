import os
import shutil
import socket
import threading

import pytest
import uvicorn
from test_job_intake import intake as intake
from test_web_review import web_settings as web_settings

from src.api.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv("M13_WEB_BROWSER_TESTS"), reason="browser opt-in")


def test_clean_browser_intake_progress_review_images_and_job_isolation(intake):
    browser = pytest.importorskip("playwright.sync_api")
    settings, cvat, annotations, problems, cfg, requests = intake
    app = create_app(settings, cvat_client=cvat)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        root = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        try:
            with browser.sync_playwright() as p:
                chrome = p.chromium.launch(headless=True, executable_path=shutil.which("google-chrome"))
                page = chrome.new_page(viewport={"width": 1366, "height": 768})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                for job in (9, 10):
                    if job == 9:
                        page.route("**/intake/status?*", lambda route: route.abort())
                    page.goto(root + f"/intake?cvat_origin=http://localhost:8080&task_id=8&job_id={job}")
                    if job == 9:
                        browser.expect(page.locator("#retry-intake")).to_be_visible()
                        browser.expect(page.locator("#intake-status")).to_contain_text("dịch vụ kiểm nhãn")
                        browser.expect(page.locator("#check-job")).to_be_disabled()
                        page.unroute("**/intake/status?*")
                        page.locator("#retry-intake").click()
                    browser.expect(page.locator("#check-job")).to_be_enabled()
                    assert page.locator('input[type=url], input[name=model], input[name=batch]').count() == 0
                    if job == 9:
                        def lost_ack(route):
                            assert route.fetch().status == 202
                            route.abort()

                        page.route("**/intake/check", lost_ack)
                    page.locator("#check-job").click()
                    if job == 9:
                        browser.expect(page.locator("#intake-status")).to_contain_text("dịch vụ kiểm nhãn")
                        page.unroute("**/intake/check", lost_ack)
                        page.locator("#check-job").click()
                    browser.expect(page.locator("#review-job")).to_be_visible(timeout=15000)
                    browser.expect(page.locator("#intake-scope")).to_contain_text("Kiểm một phần")
                    page.locator("#review-job").click()
                    browser.expect(page.locator("[data-verdict=skip]")).to_be_enabled()
                    browser.expect(page.locator("#progress")).to_contain_text("0/1")
                    assert (
                        "/jobs/" in page.url
                        and page.locator("#photo").evaluate("el => el.naturalWidth") == 1280
                    )
                    page.locator("[data-verdict=skip]").click()
                    browser.expect(page.locator("#progress")).to_contain_text("1/1")
                    page.reload()
                    browser.expect(page.locator("#progress")).to_contain_text("1/1")
                assert len(app.state.job_registry.store.state_items("request:")) == 2
                assert not errors
                chrome.close()
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            app.state.job_registry.pool.shutdown(wait=True)


@pytest.mark.skipif(os.getenv("M13_BROWSER_TESTS") != "1", reason="MV3 opt-in")
def test_mv3_intake_uses_same_registry_and_pins_verdict_to_job(intake, tmp_path):
    from fastapi.responses import HTMLResponse
    from test_extension_browser import installed_extension

    browser = pytest.importorskip("playwright.sync_api")
    settings, cvat, annotations, problems, cfg, requests = intake
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        root = f"http://127.0.0.1:{sock.getsockname()[1]}"
        settings.cvat_url = root
        app = create_app(settings, cvat_client=cvat)

        @app.get("/tasks/8/jobs/{job}")
        def cvat_fixture(job: int):
            return HTMLResponse(f"<h1>CVAT fixture job {job}, not a human pilot</h1>")

        server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            with browser.sync_playwright() as p:
                ext = installed_extension(tmp_path, root)
                chrome = p.chromium.launch_persistent_context(
                    str(tmp_path / "mv3-profile"),
                    channel="chromium",
                    headless=True,
                    args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}"],
                )
                worker = (
                    chrome.service_workers[0]
                    if chrome.service_workers
                    else chrome.wait_for_event("serviceworker")
                )
                worker.evaluate(
                    "chrome.storage.local.set({settings:{reviewer:'MV3 fixture',"
                    "sessionId:'auto-test',order:'priority'}})"
                )
                page = chrome.new_page()
                page.goto(root + "/tasks/8/jobs/9")
                browser.expect(page.locator("#m13-qc-host")).to_have_count(1)
                worker.evaluate("""async () => {
                    const tabs = await chrome.tabs.query({});
                    await toggleFromToolbar(tabs.find(t => t.url.includes('/tasks/8/jobs/9')));
                }""")
                panel = page.frame_locator("#m13-qc-host iframe")
                browser.expect(panel.locator("#check-job")).to_be_visible()
                panel.locator("#check-job").click()
                browser.expect(panel.locator("#count")).to_contain_text("0/1", timeout=15000)
                panel.locator("#queue .row").click()
                browser.expect(panel.locator("[data-verdict=skip]")).to_be_enabled()
                state = worker.evaluate("async()=> (await chrome.storage.local.get('review')).review")
                assert state["apiScope"].startswith("/jobs/") and state["detail"]["cvat"]["job_id"] == 9
                panel.locator("[data-verdict=skip]").click()
                browser.expect(panel.locator("#count")).to_contain_text("1/1")
                assert "/tasks/8/jobs/9" in page.url
                chrome.close()
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            app.state.job_registry.pool.shutdown(wait=True)
