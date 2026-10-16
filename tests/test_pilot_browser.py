"""Browser flow on a tiny MOCK pilot, not a measured human trial."""

import os
import socket
import threading

import pytest
from test_pilot_web import unit_pilot_app as unit_pilot_app
from test_recheck import setup_recheck as setup_recheck
from test_web_review_browser import launch

pytestmark = pytest.mark.skipif(
    os.environ.get("M13_WEB_BROWSER_TESTS") != "1", reason="set M13_WEB_BROWSER_TESTS=1"
)


def test_mock_pilot_enrollment_file_order_reload_and_feedback(unit_pilot_app):
    import uvicorn
    from playwright.sync_api import expect, sync_playwright

    app, _ = unit_pilot_app
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = launch(p)
            page = browser.new_page()
            requested = []
            page.on("request", lambda r: requested.append(r.url))
            page.goto(url + "/pilot")
            expect(page.locator("#pilot-submit")).to_be_enabled()
            assert not any("/image/" in u or "/web/review/" in u for u in requested)
            page.locator("#pilot-name").fill("AUTOMATED UNIT ONLY")
            for id in ["human", "unseen", "protocol"]:
                page.locator("#" + id).check()
            page.locator("#pilot-submit").click()
            expect(page).to_have_url(url + "/pilot/review")
            expect(page.locator("[data-verdict=error]")).to_be_enabled()
            expect(page.locator(".queue-pane h1")).to_have_text("Thứ tự file")
            expect(page.locator("#cvat-tools")).to_be_hidden()
            expect(page.locator("#new-session")).to_be_hidden()
            page.keyboard.press("1")
            expect(page.locator("#progress")).to_contain_text("1/2")
            page.reload()
            expect(page.locator("[data-verdict=skip]")).to_be_enabled()
            page.keyboard.press("3")
            expect(page.locator("#pilot-feedback")).to_be_visible()
            page.locator("#feedback-clarity").select_option("4")
            page.locator("#feedback-text").fill("AUTOMATED UNIT ONLY")
            page.locator("#feedback-send").click()
            expect(page.locator("#feedback-status")).to_contain_text("Đã lưu phản hồi")
            assert len(app.state.store.state_items("pilot:")) == 1
            assert {r["review_order"] for r in app.state.store.records()} == {"file"}
            assert len(app.state.store.state_items("pilot-feedback:")) == 1
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
