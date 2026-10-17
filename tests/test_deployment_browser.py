import json
import os
import shutil
import socket
import threading
from pathlib import Path

import pytest
import uvicorn
from test_deployment_auth import secured as secured
from test_web_review import web_settings as web_settings

from src.api.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv('M13_WEB_BROWSER_TESTS'), reason='set M13_WEB_BROWSER_TESTS=1')


@pytest.fixture
def guest_web(secured):
    secured.guest_demo = True
    accounts = json.loads(secured.accounts_file.read_text())
    accounts['users']['guest'] = dict(accounts['users']['demo'])
    secured.accounts_file.write_text(json.dumps(accounts))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        secured.public_origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        app = create_app(secured)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        worker.start()
        try:
            yield secured.public_origin, app
        finally:
            server.should_exit = True
            worker.join(timeout=10)


def test_guest_entry_retry_mobile_and_unavailable_features(guest_web, tmp_path):
    browser = pytest.importorskip('playwright.sync_api')
    url, app = guest_web
    with browser.sync_playwright() as p:
        chrome = p.chromium.launch(headless=True, executable_path=shutil.which('google-chrome'))
        page = chrome.new_page(viewport={'width': 1366, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/auth/session', lambda route: route.abort())
        page.goto(url)
        browser.expect(page.locator('#entry-retry')).to_be_visible()
        browser.expect(page.locator('#login-form')).to_be_hidden()
        page.unroute('**/auth/session')
        page.locator('#entry-retry').click()
        browser.expect(page.locator('#guest-demo')).to_be_visible()
        browser.expect(page.locator('#entry-retry')).to_be_hidden()
        browser.expect(page.locator('.entry-bottom .entry-resources')).to_be_hidden()
        for width in (1366, 1024, 768, 390):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.set_viewport_size({'width': 1366, 'height': 900})
        # Regression: the entry card must use its whole column, not the205px queue column.
        assert page.locator('.entry-card').bounding_box()['width'] > 350
        evidence = Path(os.environ.get('M13_UI_EVIDENCE_DIR', tmp_path))
        evidence.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(evidence / 'login-desktop.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(evidence / 'login-mobile.png'), full_page=True)
        page.locator('#account-toggle').click()
        browser.expect(page.locator('#username')).to_be_focused()
        page.locator('#account-toggle').click()
        browser.expect(page.locator('#login-form')).to_be_hidden()
        page.route('**/auth/demo', lambda route: route.fulfill(status=503, json={'detail': 'temporary'}))
        page.locator('#guest-demo').click()
        browser.expect(page.locator('#login-status')).to_contain_text('Chưa mở được lượt demo')
        browser.expect(page.locator('#guest-demo')).to_be_enabled()
        browser.expect(page.locator('#login-form')).to_be_hidden()
        page.unroute('**/auth/demo')
        page.locator('#guest-demo').click()
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled(timeout=15000)
        for selector in ('#cvat-tools', '#pilot-link', '#results-link', '#submission-link'):
            browser.expect(page.locator(selector)).to_be_hidden()
        assert not app.state.store.records()
        assert not errors
        chrome.close()


def test_published_resources_are_discoverable_without_exposing_admin_tools(guest_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, _ = guest_web
    with browser.sync_playwright() as p:
        chrome = p.chromium.launch(headless=True, executable_path=shutil.which('google-chrome'))
        page = chrome.new_page()
        # Metadata transport fixture: published files themselves are verified by Postgres/public checks.
        page.route('**/web/submission', lambda route: route.fulfill(
            json={'assets': {'pitch.pdf': '/fixture.pdf'}}))
        page.goto(url)
        browser.expect(page.locator('.entry-bottom .entry-resources')).to_be_visible()
        page.locator('#guest-demo').click()
        browser.expect(page.locator('#submission-link')).to_be_visible(timeout=15000)
        browser.expect(page.locator('#pilot-link')).to_be_hidden()
        browser.expect(page.locator('#cvat-tools')).to_be_hidden()
        page.goto(url + '/results')
        browser.expect(page.locator('#report-pilot-link')).to_be_hidden()
        chrome.close()


def test_clean_browser_login_session_isolation_reload_and_logout(secured):
    browser = pytest.importorskip('playwright.sync_api')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        secured.public_origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
        app = create_app(secured)
        server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
        worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        worker.start()
        try:
            with browser.sync_playwright() as p:
                chrome = p.chromium.launch(headless=True, executable_path=shutil.which('google-chrome'))
                a, b = chrome.new_context(), chrome.new_context()
                page = a.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def enter(target):
                    target.goto(secured.public_origin)
                    browser.expect(target.locator('#login-form')).to_be_visible()
                    target.locator('#username').fill('demo')
                    target.locator('#password').fill('unit-demo-password')
                    target.locator('#sign-in').click()
                    # Password hashing and the initial image share a busy runner.
                    browser.expect(target.locator('[data-verdict=error]')).to_be_enabled(timeout=15000)

                enter(page)
                browser.expect(page.locator('#cvat-tools')).to_be_hidden()
                page.locator('[data-verdict=error]').click()
                browser.expect(page.locator('#progress')).to_contain_text('1/3')
                page.reload()
                browser.expect(page.locator('#progress')).to_contain_text('1/3')
                second = b.new_page()
                enter(second)
                browser.expect(second.locator('#progress')).to_contain_text('0/3')
                page.locator('details.advanced > summary').click()
                page.locator('#new-session').click()
                browser.expect(page.locator('#progress')).to_contain_text('0/3')
                page.locator('details.advanced > summary').click()
                page.locator('#logout').click()
                browser.expect(page.locator('#login-form')).to_be_visible()
                assert a.request.get(secured.public_origin + '/queue').status == 401
                assert len(app.state.store.records()) == 1
                assert not errors
                chrome.close()
        finally:
            server.should_exit = True
            worker.join(timeout=10)
