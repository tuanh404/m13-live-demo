import json

import pytest
from fastapi.testclient import TestClient
from test_web_review import web_settings as web_settings

from src.api.auth import password_hash
from src.api.main import create_app


@pytest.fixture
def secured(web_settings, tmp_path):
    accounts = tmp_path / 'accounts.json'
    accounts.write_text(json.dumps({'users': {
        'demo': {'role': 'demo', 'password_hash': password_hash('unit-demo-password')},
        'admin': {'role': 'admin', 'password_hash': password_hash('unit-admin-password')},
    }}))
    web_settings.accounts_file = accounts
    web_settings.public_origin = 'http://localhost'
    web_settings.auth_cookie_secure = False
    return web_settings


def login(client, username='demo'):
    return client.post('/auth/login', headers={'Origin': 'http://localhost'},
                       json={'username': username, 'password': f'unit-{username}-password'})


def test_login_guard_ownership_admin_csrf_and_restart(secured):
    app = create_app(secured)
    a = TestClient(app, base_url='http://localhost')
    b = TestClient(app, base_url='http://localhost')
    assert a.get('/queue').status_code == 401
    assert a.get('/', headers={'Accept': 'text/html'}, follow_redirects=False).headers['location'] == '/login'
    assert a.get('/health').status_code == 200
    assert a.get('/assets/login.js').status_code == 200
    assert a.post('/auth/login', json={
        'username': 'demo', 'password': 'unit-demo-password'
    }).status_code == 403
    assert login(a).status_code == login(b).status_code == 200
    first = a.get('/auth/session').json()['identity']
    other = b.get('/auth/session').json()['identity']
    assert first['session_id'] != other['session_id']
    q = {'reviewer': first['reviewer'], 'session_id': first['session_id'], 'order': 'priority'}
    assert a.get('/queue', params=q).status_code == 200
    assert b.get('/queue', params=q).status_code == 403
    assert a.get('/stats').status_code == 403
    assert a.post('/retrain', headers={'Origin': 'http://localhost'}).status_code == 403
    assert a.post('/model/rollback', json={}, headers={'Origin': 'http://localhost'}).status_code == 403
    assert a.get('/image/fixture-qc-01/saved').status_code == 403
    row = a.get('/queue', params=q).json()['items'][0]
    payload = {'request_id': 'auth-retry', 'image_id': row['image_id'], 'verdict': 'error',
               'reviewer': first['reviewer'], 'session_id': first['session_id'], 'seconds_spent': 2}
    assert a.post('/verdict', json=payload, headers={'Origin': 'https://foreign.test'}).status_code == 403
    headers = {'Origin': 'http://localhost'}
    assert a.post('/verdict', json={**payload, 'reviewer': 'spoof'}, headers=headers).status_code == 403
    assert a.post('/verdict', json=payload, headers=headers).json()['duplicate'] is False
    restarted = TestClient(create_app(secured), base_url='http://localhost')
    restarted.cookies.update(a.cookies)
    assert restarted.post('/verdict', json=payload, headers=headers).json()['duplicate'] is True
    assert restarted.get('/queue', params=q).json()['remaining'] == 2
    admin = TestClient(app, base_url='http://localhost')
    assert login(admin, 'admin').status_code == 200
    assert admin.get('/model').status_code == 200
    assert admin.post('/retrain', headers=headers).status_code == 503  # No invented ML backend.
    assert a.post('/auth/new-review', headers=headers).status_code == 200
    assert a.get('/auth/session').json()['identity']['session_id'] != first['session_id']
    assert a.post('/auth/logout', headers=headers).status_code == 200
    assert a.get('/queue', params=q).status_code == 401


def test_shared_config_and_cookie_validation(secured):
    secured.public_origin = 'https://review.example.test'
    with pytest.raises(ValueError, match='HTTPS'):
        create_app(secured)
    secured.auth_cookie_secure = True
    app = create_app(secured)
    client = TestClient(app, base_url=secured.public_origin)
    assert client.get('/health', headers={'Host': 'evil.test'}).status_code == 400
    response = client.post('/auth/login', json={'username': 'demo', 'password': 'unit-demo-password'},
                           headers={'Origin': secured.public_origin})
    assert response.status_code == 200
    assert 'Secure' in response.headers['set-cookie'] and 'HttpOnly' in response.headers['set-cookie']
    assert client.post('/verdict', content=b'x'*40000,
                       headers={'Origin': secured.public_origin}).status_code == 413
