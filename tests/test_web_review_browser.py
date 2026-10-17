"""Clean Chrome without extension; automatic fixture sessions are never human pilot data."""

import json
import os
import shutil
import socket
import threading

import pytest
from test_web_review import web_settings as web_settings

from src.api.main import create_app

pytestmark = pytest.mark.skipif(os.environ.get('M13_WEB_BROWSER_TESTS') != '1',
                                reason='set M13_WEB_BROWSER_TESTS=1 for clean web browser tests')


@pytest.fixture
def live_web(web_settings):
    import uvicorn

    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(5)
    app = create_app(web_settings)
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{sock.getsockname()[1]}', app
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def launch(playwright):
    return playwright.chromium.launch(headless=True, executable_path=shutil.which('google-chrome'))


def test_clean_web_all_verdicts_lost_ack_reload_retry_and_stats(live_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, app = live_web
    with browser.sync_playwright() as playwright:
        chrome = launch(playwright)
        context = chrome.new_context(viewport={'width': 1366, 'height': 768})
        page = context.new_page()
        errors, requests = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: requests.append(request.url))
        page.goto(url)
        first = page.locator('[data-verdict=error]')
        browser.expect(first).to_be_enabled()
        assert page.locator('#metadata, #signals, #session-info, #raw-reasons').count() == 0
        assert page.locator('input[type=url], input[name=batch], input[name=session_id]').count() == 0
        browser.expect(page.locator('#data-kind')).to_contain_text('FIXTURE')
        browser.expect(page.locator('#risk')).to_have_text('50')
        browser.expect(page.locator('#reasons')).to_contain_text('Box 1 · car')
        assert 'car #1' not in page.locator('#reasons').inner_text()
        page.locator('#boxes-details').click()
        browser.expect(page.locator('#label-list')).to_contain_text('Box 1 · car (0, 180, 350, 380)')
        page.locator('#note-details').click()
        page.locator('#note').fill('Phím 1 ở ghi chú không phải verdict')
        page.locator('#note').press('1')
        assert not app.state.store.records()
        page.locator('#note').blur()
        page.keyboard.press('1')
        browser.expect(page.locator('#progress')).to_contain_text('1/3')
        browser.expect(page.locator('#risk')).to_have_text('0')
        assert '0 vẫn có thể có lỗi' in page.locator('.risk-help').inner_text()
        page.reload()
        browser.expect(first).to_be_enabled()
        browser.expect(page.locator('#progress')).to_contain_text('1/3')

        def lost_ack(route):
            route.fetch()  # Commit reaches the real API; only the acknowledgment is lost.
            route.abort()

        page.route('**/verdict', lost_ack)
        page.locator('[data-verdict=false_alarm]').click()
        browser.expect(page.locator('#notice')).to_contain_text('Chưa nhận xác nhận lưu')
        assert len(app.state.store.records()) == 2
        pending = page.evaluate("JSON.parse(localStorage.getItem('m13.web.review.v1')).pending")
        page.reload()
        browser.expect(page.locator('#notice')).to_contain_text('lần trước')
        page.unroute('**/verdict', lost_ack)
        page.locator('#retry').click()
        browser.expect(page.locator('#progress')).to_contain_text('2/3')
        browser.expect(page.locator('[data-verdict=skip]')).to_be_enabled()
        assert len(app.state.store.records()) == 2
        assert len([r for r in app.state.store.records() if r['request_id'] == pending['request_id']]) == 1
        page.keyboard.press('3')
        browser.expect(page.locator('#image-title')).to_have_text('Đã hoàn thành lượt review')
        browser.expect(page.locator('#stats')).to_contain_text('1 lỗi thật · 1 bot nhầm · 1 bỏ qua')
        browser.expect(page.locator('#stats')).to_contain_text('50%')
        rows = app.state.store.records()
        assert [r['verdict'] for r in rows] == ['error', 'false_alarm', 'skip']
        assert all(r['seconds_spent'] >= 0 and r['session_id'].startswith('demo-') for r in rows)
        page.reload()
        browser.expect(page.locator('#progress')).to_contain_text('3/3')
        assert not errors
        assert all(request.startswith(url + '/') or request == url + '/' for request in requests)
        chrome.close()


def test_clean_web_image_failure_retry_laptop_and_small_screen(live_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, app = live_web
    with browser.sync_playwright() as playwright:
        chrome = launch(playwright)
        page = chrome.new_page(viewport={'width': 1366, 'height': 768})
        page.route('**/image/*/file', lambda route: route.abort())
        page.goto(url)
        browser.expect(page.locator('#notice')).to_contain_text('Không tải được ảnh')
        browser.expect(page.locator('[data-verdict=error]')).to_be_disabled()
        page.unroute('**/image/*/file')
        page.locator('#retry').click()
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled()
        assert not app.state.store.records()
        for width, height in [(1366, 768), (1024, 768), (768, 800), (390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.locator('#photo').is_visible()
        page.set_viewport_size({'width': 1366, 'height': 768})
        page.locator('#notice').scroll_into_view_if_needed()
        browser.expect(page.locator('[data-verdict=skip]')).to_be_in_viewport()
        chrome.close()


def test_web_timer_focus_events_and_rejected_request_can_be_reconsidered(live_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, app = live_web
    with browser.sync_playwright() as playwright:
        chrome = launch(playwright)
        context = chrome.new_context()
        page = context.new_page()
        # Headless Chrome does not reliably blur tabs. Control the focus input, not elapsed logic.
        page.add_init_script('''window.fixtureFocus = true;
            Object.defineProperty(document, 'hasFocus', {value: () => window.fixtureFocus});''')
        page.clock.install()
        page.goto(url)
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled()
        page.clock.fast_forward(5000)
        page.evaluate("window.fixtureFocus = false; window.dispatchEvent(new Event('blur'))")
        page.clock.fast_forward(30000)
        page.evaluate("window.fixtureFocus = true; window.dispatchEvent(new Event('focus'))")
        page.clock.fast_forward(2000)
        page.locator('[data-verdict=error]').click()
        browser.expect(page.locator('#progress')).to_contain_text('1/3')
        elapsed = app.state.store.records()[0]['seconds_spent']
        assert 6.9 <= elapsed <= 8, elapsed

        def rejected(route):
            route.fulfill(status=409, content_type='application/json', body='{"detail":"Queue đã đổi"}')

        page.route('**/verdict', rejected)
        page.locator('[data-verdict=false_alarm]').click()
        browser.expect(page.locator('#notice')).to_contain_text('API từ chối')
        browser.expect(page.locator('#discard-rejected')).to_be_visible()
        page.on('dialog', lambda dialog: dialog.accept())
        page.locator('#discard-rejected').click()
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled()
        assert len(app.state.store.records()) == 1
        assert page.evaluate("JSON.parse(localStorage.getItem('m13.web.review.v1')).pending") is None
        chrome.close()


def test_web_api_retry_and_evidence_text_is_not_html(live_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, app = live_web
    with browser.sync_playwright() as playwright:
        chrome = launch(playwright)
        page = chrome.new_page()
        page.route('**/queue?*', lambda route: route.abort())
        page.goto(url)
        browser.expect(page.locator('#retry')).to_be_visible()
        browser.expect(page.locator('[data-verdict=error]')).to_be_disabled()
        page.unroute('**/queue?*')

        def unsafe_text(route):
            response = route.fetch()
            body = response.json()
            body['reasons'] = ['[R1] <img src=x onerror="window.injected=true">']
            body['evidence'][0]['note'] = '<script>window.injected=true</script>'
            body['display_reasons'] = body['reasons']
            body['display_issues'][0] = body['evidence'][0]['note']
            route.fulfill(response=response, body=json.dumps(body))

        page.route('**/web/review/*', unsafe_text)
        page.locator('#retry').click()
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled()
        browser.expect(page.locator('#reasons')).to_contain_text('<img')
        browser.expect(page.locator('#evidence-list')).to_contain_text('<script>')
        assert page.locator('#reasons img, #evidence-list script').count() == 0
        assert not page.evaluate('Boolean(window.injected)')
        assert not app.state.store.records()
        chrome.close()


def test_dense_overlay_names_optional_and_team_timing_separate(live_web):
    browser = pytest.importorskip('playwright.sync_api')
    url, _ = live_web
    with browser.sync_playwright() as p:
        chrome = launch(p)
        page = chrome.new_page(viewport={'width': 1366, 'height': 768})
        page.goto(url)
        browser.expect(page.locator('[data-verdict=error]')).to_be_enabled()
        assert not page.locator('#show-box-names').is_checked()
        page.locator('#show-box-names').check()
        assert page.locator('#show-box-names').is_checked()
        page.locator('#boxes-details').click()
        page.locator('#label-list button').first.click()
        browser.expect(page.locator('#label-list button').first).to_have_attribute('aria-pressed', 'true')
        page.goto(url + '/results')
        browser.expect(page.locator('#team-timing')).to_contain_text('10 ảnh')
        browser.expect(page.locator('#team-timing')).to_contain_text('20 phút')
        browser.expect(page.locator('#team-timing')).to_contain_text('45 phút')
        browser.expect(page.locator('#team-timing')).to_contain_text('55.6%')
        assert 'chưa đối chiếu log' in page.locator('.report-page').last.inner_text()
        chrome.close()
