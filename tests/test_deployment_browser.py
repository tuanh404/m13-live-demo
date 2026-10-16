import os
import shutil
import socket
import threading

import pytest
import uvicorn
from test_deployment_auth import secured as secured
from test_web_review import web_settings as web_settings

from src.api.main import create_app

pytestmark = pytest.mark.skipif(not os.getenv('M13_WEB_BROWSER_TESTS'), reason='set M13_WEB_BROWSER_TESTS=1')


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
                    browser.expect(target.locator('[data-verdict=error]')).to_be_enabled()

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
