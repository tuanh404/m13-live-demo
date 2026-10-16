import os

import pytest
from test_web_cvat import web_cvat as web_cvat
from test_web_review import web_settings as web_settings
from test_web_review_browser import launch
from test_web_review_browser import live_web as live_web

pytestmark = pytest.mark.skipif(
    os.environ.get("M13_WEB_BROWSER_TESTS") != "1", reason="set M13_WEB_BROWSER_TESTS=1"
)


def test_web_cvat_saved_recheck_lost_ack_and_history(web_cvat, live_web):
    browser = pytest.importorskip("playwright.sync_api")
    settings, annotations, cvat = web_cvat
    url, app = live_web
    app.state.rechecks.saved.client = cvat
    with browser.sync_playwright() as playwright:
        chrome = launch(playwright)
        page = chrome.new_page()
        page.goto(url)
        browser.expect(page.locator("[data-verdict=error]")).to_be_enabled()
        page.locator("#cvat-tools > summary").click()
        page.locator("#connect-cvat").click()
        browser.expect(page.locator("#open-cvat")).to_have_attribute(
            "href", "http://localhost:8080/tasks/8/jobs/9?frame=0"
        )
        # This is a CVAT transport fixture, never navigate to the real job at this URL.
        page.locator("#read-saved").click()
        browser.expect(page.locator("#saved-boxes")).to_contain_text("(0, 180, 350, 380)")
        browser.expect(page.locator("#risk")).to_have_text("50")
        annotations["shapes"][0]["points"][0] = 100
        annotations["version"] += 1
        page.locator("#read-saved").click()
        browser.expect(page.locator("#saved-boxes")).to_contain_text("(100, 180, 350, 380)")

        def lost_ack(route):
            route.fetch()
            route.abort()

        page.route("**/image/*/recheck", lost_ack)
        page.locator("#recheck").click()
        browser.expect(page.locator("#recheck-status")).to_contain_text("50 → 0")
        browser.expect(page.locator("#risk")).to_have_text("0")
        browser.expect(page.locator("#image-title")).to_have_text("fixture-qc-01")
        assert len(app.state.store.state_items("recheck:")) == 1
        page.reload()
        browser.expect(page.locator("[data-verdict=error]")).to_be_enabled()
        browser.expect(page.locator("#image-title")).to_have_text("fixture-qc-01")
        page.locator("#cvat-tools > summary").click()
        page.locator("#show-history").click()
        page.get_by_role("button", name="Xem trước", exact=True).click()
        browser.expect(page.locator("#recheck-history pre")).to_contain_text("50/100")
        page.get_by_role("button", name="Xem sau", exact=True).click()
        browser.expect(page.locator("#recheck-history pre")).to_contain_text("0/100")
        browser.expect(page.locator("#recheck-history pre")).to_contain_text("(100, 180, 350, 380)")
        chrome.close()
