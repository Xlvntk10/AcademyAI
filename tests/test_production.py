"""Production contract: private proxy responses, Auth outages and recovery.

The local proxy checks the required transport contract; it does not certify Render.
"""
from contextlib import ExitStack
import httpx
import pytest
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.testclient import TestClient
from app.accounts import AccountConfig, SupabaseAuth
from tests.test_accounts import accounts_app, login, ORIGIN
from tests.test_offline import submission


@pytest.mark.parametrize("body", [[], {"access_token": "SECRET", "expires_in": 60},
    {"access_token": "SECRET", "refresh_token": "PRIVATE", "expires_in": -1},
    {"access_token": "SECRET", "refresh_token": "PRIVATE", "expires_in": True},
    {"access_token": "SECRET", "refresh_token": "PRIVATE", "expires_in": "3600"}])
def test_malformed_successful_auth_response_is_safe(body):
    config = AccountConfig(ORIGIN, "https://project.supabase.co", "sb_publishable_test", None)
    provider = SupabaseAuth(config, httpx.MockTransport(lambda request: httpx.Response(200, json=body)))
    for operation in (lambda: provider.verify("one@example.test", "123456"), lambda: provider.refresh("PRIVATE")):
        with pytest.raises(HTTPException) as error:
            operation()
        assert error.value.status_code == 503
        assert "SECRET" not in error.value.detail and "PRIVATE" not in error.value.detail


@pytest.mark.parametrize("status,expected", [(200, 503), (502, 503), (429, 429), (401, 401)])
def test_auth_html_or_error_does_not_escape_provider_boundary(status, expected):
    config = AccountConfig(ORIGIN, "https://project.supabase.co", "sb_publishable_test", None)
    provider = SupabaseAuth(config, httpx.MockTransport(lambda request: httpx.Response(status, text="<html>SECRET</html>")))
    with pytest.raises(HTTPException) as error:
        provider.verify("one@example.test", "123456")
    assert error.value.status_code == expected
    assert "SECRET" not in error.value.detail


@pytest.mark.parametrize("url", ["https://user:secret@project.supabase.co", "https://project.supabase.co/auth/v1", "https://project.supabase.co?key=secret"])
def test_provider_configuration_rejects_credentials_and_paths(monkeypatch, url):
    monkeypatch.setenv("ACADEMY_AUTH_MODE", "supabase")
    monkeypatch.setenv("ACADEMY_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_URL", url)
    with pytest.raises(RuntimeError):
        AccountConfig.from_environment(cloud=True)


def test_static_proxy_two_device_cookie_and_offline_replay_contract(accounts_app):
    backend, _, _, _ = accounts_app
    proxy = FastAPI()
    available = True
    @proxy.api_route("/api/{tail:path}", methods=["GET", "POST", "OPTIONS"])
    async def forward(tail: str, request: Request):
        if not available:
            return Response(status_code=503, headers={"Cache-Control": "no-store"})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=backend), base_url="https://api.test") as upstream:
            response = await upstream.request(request.method, request.url.path,
                params=request.query_params, content=await request.body(),
                headers={k:v for k,v in request.headers.items() if k not in {"host", "content-length"}})
        result = Response(response.content, status_code=response.status_code)
        result.raw_headers = [(k.encode(), v.encode()) for k,v in response.headers.multi_items()
                              if k not in {"content-encoding", "transfer-encoding"}]
        return result
    with ExitStack() as stack:
        desktop, phone, outsider = [stack.enter_context(TestClient(proxy, base_url=ORIGIN,
            headers={"Origin":ORIGIN,"X-Academy-Request":"1"})) for _ in range(3)]
        login(desktop); login(phone); login(outsider, "two@example.test")
        payload = submission(phone)
        available = False
        assert phone.post("/api/offline/attempts", json=payload).status_code == 503
        available = True
        accepted = phone.post("/api/offline/attempts", json=payload)
        assert accepted.status_code == 200
        assert phone.post("/api/offline/attempts", json=payload).json() == accepted.json()
        assert desktop.get("/api/progress").json()["total_xp"] == 60
        assert desktop.get("/api/dashboard").json()["current_streak"] == 1
        assert outsider.get("/api/runs/" + payload["attempt_id"]).status_code == 404
        week = desktop.get("/api/planner/week").json()
        update = desktop.post("/api/planner/generate", json={"week_start":week["week_start"]}, headers={"If-Match":week["sync_revision"]})
        assert update.status_code == 200
        assert phone.get("/api/planner/week").json() == update.json()
        for response in [accepted, desktop.get("/api/auth/session"), outsider.get("/api/runs/" + payload["attempt_id"])]:
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["cdn-cache-control"] == "no-store"
            assert response.headers["surrogate-control"] == "no-store"
            assert "cookie" in response.headers["vary"].lower()
        assert desktop.post("/api/auth/logout",json={}).status_code == 200
        assert desktop.get("/api/progress").status_code == 401
        assert phone.get("/api/progress").status_code == 200
