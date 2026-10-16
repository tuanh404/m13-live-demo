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
                    page.goto(root + f"/intake?cvat_origin=http://localhost:8080&task_id=8&job_id={job}")
                    browser.expect(page.locator("#check-job")).to_be_enabled()
                    page.locator("#check-job").click()
                    browser.expect(page.locator("#review-job")).to_be_visible(timeout=15000)
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
                assert not errors
                chrome.close()
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            app.state.job_registry.pool.shutdown(wait=True)
