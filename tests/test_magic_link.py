"""Magic Link PKCE contract against the real API and a provider HTTP test double."""
import base64
from dataclasses import replace
import hashlib
import json
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from app.accounts import COOKIE, PKCE_COOKIE, SupabaseAuth
from tests.test_accounts import AuthHTTP, accounts_app, USERS, ORIGIN
from scripts.prepare_db import snapshot


class MagicAuth(AuthHTTP):
    def __init__(self):
        super().__init__()
        self.links = {}
        self.requests = []
        self.exchange_count = 0

    def __call__(self, request):
        if self.offline:
            raise httpx.ConnectError("test offline")
        body = json.loads(request.content) if request.content else {}
        if request.url.path.endswith('/otp') and 'code_challenge' in body:
            assert request.headers['apikey'] == 'sb_publishable_test'
            assert body['code_challenge_method'] == 's256'
            assert len(body['code_challenge']) == 43
            code = str(uuid4())
            self.links[code] = (body['email'], body['code_challenge'])
            self.requests.append((request, code))
            return httpx.Response(200, json={})
        if request.url.params.get('grant_type') == 'pkce':
            self.exchange_count += 1
            value = self.links.get(body['auth_code'])
            challenge = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).rstrip(b'=').decode()
            if not value or value[1] != challenge:
                return httpx.Response(400, json={'error':'invalid_grant'})
            del self.links[body['auth_code']]
            return httpx.Response(200, json=self.session(value[0]))
        return super().__call__(request)


def install(manager):
    provider = MagicAuth()
    manager.provider = SupabaseAuth(manager.config, httpx.MockTransport(provider))
    return provider


def request_link(client, provider, email='one@example.test'):
    response = client.post('/api/auth/link', json={'email': email, 'register': True, 'redirect_to': 'https://evil.test'})
    assert response.status_code == 200
    assert 'no-store' in response.headers['cache-control']
    assert 'code_verifier' not in response.text and 'access_token' not in response.text
    return provider.requests[-1][1]


@pytest.mark.parametrize('origin', [ORIGIN, 'http://127.0.0.1:5173'])
def test_magic_link_session_cookie_profile_and_source_preserved(accounts_app, database, origin):
    app, manager, _, _ = accounts_app
    before = snapshot(database)
    manager.config = replace(manager.config, origin=origin)
    provider = install(manager)
    with TestClient(app, base_url=origin, headers={'Origin':origin, 'X-Academy-Request':'1'}) as client:
        code = request_link(client, provider, 'ONE@EXAMPLE.TEST')
        request = provider.requests[-1][0]
        assert request.url.params['redirect_to'] == origin + '/auth/callback'
        assert json.loads(request.content)['email'] == 'one@example.test'
        verifier_cookie = next(c for c in client.cookies.jar if c.name == PKCE_COOKIE)
        assert verifier_cookie.path == '/api/auth'
        assert verifier_cookie.secure == origin.startswith('https')
        response = client.post('/api/auth/exchange', json={'code':code, 'user_id':USERS['two@example.test']})
        assert response.status_code == 200
        assert response.json()['user']['id'] == USERS['one@example.test']
        assert client.cookies.get(PKCE_COOKIE) is None
        assert client.cookies.get(COOKIE)
        assert 'httponly' in response.headers['set-cookie'].lower()
        assert 'samesite=strict' in response.headers['set-cookie'].lower()
        assert 'domain=' not in response.headers['set-cookie'].lower()
        assert 'access_token' not in response.text and 'refresh_token' not in response.text
        assert client.get('/api/auth/session').json() == response.json()
        client.headers['X-Academy-Account'] = response.json()['user']['id']
        assert client.get('/api/progress').status_code == 200
        assert client.post('/api/auth/exchange', json={'code':code}).status_code == 401
    assert snapshot(database) == before


def test_magic_link_rejects_foreign_browser_csrf_and_replay(accounts_app):
    _, manager, _, (client, other, _) = accounts_app
    provider = install(manager)
    code = request_link(client, provider)
    verifier = client.cookies.get(PKCE_COOKIE)
    assert other.post('/api/auth/exchange', json={'code':code}).status_code == 401
    request_link(other, provider, 'two@example.test')
    assert other.post('/api/auth/exchange', json={'code':code}).status_code == 401
    assert client.post('/api/auth/exchange', json={'code':code}, headers={'Origin':'https://evil.test'}).status_code == 403
    assert client.post('/api/auth/link', json={'email':'one@example.test'}, headers={'Origin':'https://evil.test'}).status_code == 403
    assert client.post('/api/auth/exchange', json={'code':code}).status_code == 200
    client.cookies.set(PKCE_COOKIE, verifier, path='/api/auth')
    assert client.post('/api/auth/exchange', json={'code':code}).status_code == 401


def test_magic_link_new_request_invalidates_old_and_outage_can_retry(accounts_app):
    _, manager, _, (client, _, _) = accounts_app
    provider = install(manager)
    old = request_link(client, provider)
    current = request_link(client, provider)
    assert client.post('/api/auth/exchange', json={'code':old}).status_code == 401
    provider.offline = True
    assert client.post('/api/auth/exchange', json={'code':current}).status_code == 503
    assert client.cookies.get(PKCE_COOKIE)
    provider.offline = False
    assert client.post('/api/auth/exchange', json={'code':current}).status_code == 200


def test_magic_link_expired_code_does_not_create_session(accounts_app):
    _, manager, _, (client, _, _) = accounts_app
    provider = install(manager)
    code = request_link(client, provider)
    provider.links.clear()
    assert client.post('/api/auth/exchange', json={'code':code}).status_code == 401
    assert client.get('/api/auth/session').json()['user'] is None
    assert not list(manager.directory.glob('*.db'))


def test_magic_link_email_requests_share_otp_rate_limit(accounts_app):
    _, manager, _, (client, _, _) = accounts_app
    provider = install(manager)
    for _ in range(5):
        request_link(client, provider)
    assert client.post('/api/auth/link', json={'email':'one@example.test'}).status_code == 429
    assert client.post('/api/auth/code', json={'email':'one@example.test'}).status_code == 429
