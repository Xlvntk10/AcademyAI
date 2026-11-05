"""Two independent cookie jars against real API/storage and a fake Auth HTTP boundary."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from app.accounts import AccountConfig, Accounts, SupabaseAuth, COOKIE
from app.database.db import make_engine
from app.main import create_app
from scripts.prepare_db import snapshot, verify
from tests.test_offline import submission

USERS = {"one@example.test": "11111111-1111-4111-8111-111111111111",
         "two@example.test": "22222222-2222-4222-8222-222222222222"}
ORIGIN = "https://academy.test"


class AuthHTTP:
    def __init__(self):
        self.tokens = {}
        self.refreshes = {}
        self.offline = False
        self.refresh_count = 0

    def session(self, email):
        access, refresh = str(uuid4()), str(uuid4())
        self.tokens[access] = email
        self.refreshes[refresh] = email
        return {"access_token": access, "refresh_token": refresh, "expires_in": 3600}

    def __call__(self, request):
        assert request.headers["apikey"] == "sb_publishable_test"
        if self.offline:
            raise httpx.ConnectError("test offline")
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path.endswith("/otp"):
            assert body["email"] in USERS
            return httpx.Response(200, json={})
        if path.endswith("/verify"):
            if body["token"] != "123456":
                return httpx.Response(403, json={"msg": "invalid"})
            return httpx.Response(200, json=self.session(body["email"]))
        if path.endswith("/token"):
            email = self.refreshes.pop(body["refresh_token"], None)
            if not email:
                return httpx.Response(401, json={})
            self.refresh_count += 1
            return httpx.Response(200, json=self.session(email))
        email = self.tokens.get(request.headers.get("authorization", "").removeprefix("Bearer "))
        if not email:
            return httpx.Response(401, json={})
        if path.endswith("/user"):
            return httpx.Response(200, json={"id": USERS[email], "email": email, "email_confirmed_at": "2026-01-01T00:00:00Z"})
        if path.endswith("/logout"):
            return httpx.Response(204)
        raise AssertionError(path)


@pytest.fixture
def accounts_app(database, tmp_path):
    boundary = AuthHTTP()
    config = AccountConfig(ORIGIN, "https://project.supabase.co", "sb_publishable_test", tmp_path / "accounts")
    manager = Accounts(config, SupabaseAuth(config, httpx.MockTransport(boundary)))
    engine = make_engine("sqlite:///" + database.as_posix())
    app = create_app(engine, accounts=manager)
    with ExitStack() as stack:
        clients = [stack.enter_context(TestClient(app, base_url=ORIGIN, headers={
            "Origin": ORIGIN, "X-Academy-Request": "1"})) for _ in range(3)]
        yield app, manager, boundary, clients
    engine.dispose()


def login(client, email="one@example.test"):
    assert client.post("/api/auth/code", json={"email": email, "register": True}).status_code == 200
    response = client.post("/api/auth/verify", json={"email": email, "code": "123456"})
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert "access_token" not in response.text and "refresh_token" not in response.text
    client.headers["X-Academy-Account"] = response.json()["user"]["id"]
    return response.json()


def test_login_csrf_logout_and_durable_device_sessions(accounts_app):
    app, manager, boundary, (desktop, phone, outsider) = accounts_app
    assert outsider.get("/api/progress").status_code == 401
    assert outsider.get("/api/progress").headers["cache-control"] == "no-store"
    assert outsider.post("/api/auth/code", json={"email": "one@example.test"}, headers={"Origin":"https://evil.test"}).status_code == 403
    assert outsider.post("/api/auth/verify", json={"email":"one@example.test", "code":"000000"}).status_code == 401
    login(desktop)
    login(phone)
    cookie = desktop.cookies.get(COOKIE)
    assert cookie != phone.cookies.get(COOKIE)
    # Rebuild both application and session manager, preserving only on-disk state.
    restarted = Accounts(manager.config, manager.provider)
    with TestClient(create_app(app.state.engine, accounts=restarted), base_url=ORIGIN) as fresh:
        fresh.cookies.set(COOKIE, cookie)
        fresh.headers["X-Academy-Account"] = USERS["one@example.test"]
        assert fresh.get("/api/progress").status_code == 200
    assert desktop.post("/api/auth/logout", json={}).status_code == 200
    desktop.cookies.set(COOKIE, cookie)
    assert desktop.get("/api/progress").status_code == 401
    assert phone.get("/api/progress").status_code == 200


def test_two_devices_sync_results_plan_streak_and_isolate_other_account(accounts_app, database):
    _, manager, _, (desktop, phone, other) = accounts_app
    original = snapshot(database)
    login(desktop)
    login(phone)
    login(other, "two@example.test")
    payload = submission(desktop)
    result = desktop.post("/api/offline/attempts", json=payload)
    assert result.status_code == 200
    assert result.json()["result"]["score"] == 60
    with ThreadPoolExecutor(max_workers=2) as pool:
        retries = list(pool.map(lambda client: client.post("/api/offline/attempts", json=payload), [desktop, phone]))
    assert all(response.json() == result.json() for response in retries)
    a = desktop.get("/api/sync/snapshot").json()
    b = phone.get("/api/sync/snapshot").json()
    assert a["progress"] == b["progress"]
    assert a["dashboard"] == b["dashboard"]
    assert b["progress"]["total_xp"] == 60
    assert b["dashboard"]["current_streak"] == 1
    assert other.get("/api/progress").json()["total_xp"] == 0
    assert other.get("/api/runs/" + payload["attempt_id"]).status_code == 404
    assert other.post("/api/offline/attempts", json=payload).status_code == 409
    # Even a stale tab whose cookies switched account cannot send its old queue.
    assert other.get("/api/progress", headers={"X-Academy-Account":USERS["one@example.test"]}).status_code == 409
    assert other.post("/api/auth/logout", json={}, headers={"X-Academy-Account":USERS["one@example.test"]}).status_code == 409
    assert other.get("/api/progress").status_code == 200
    week = desktop.get("/api/planner/week").json()
    body = {"week_start": week["week_start"]}
    assert desktop.post("/api/planner/generate", json=body).status_code == 428
    generated = desktop.post("/api/planner/generate", json=body, headers={"If-Match":week["sync_revision"]})
    assert generated.status_code == 200, generated.text
    assert phone.get("/api/planner/week").json() == generated.json()
    assert other.get("/api/planner/week").json()["tasks"] == []
    task = generated.json()["tasks"][0]
    assert other.post(f'/api/planner/tasks/{task["id"]}/reschedule', json={"scheduled_date":task["scheduled_date"]}, headers={"If-Match":other.get("/api/planner/week").json()["sync_revision"]}).status_code == 404
    assert snapshot(database) == original
    for user_id in USERS.values():
        verify(manager.directory / (user_id + ".db"))


def test_planner_conflict_preserves_newer_settings(accounts_app):
    _, _, _, (desktop, phone, _) = accounts_app
    login(desktop)
    login(phone)
    prefs = desktop.get("/api/planner/settings").json()
    revision = prefs.pop("sync_revision")
    prefs.pop("timezone")
    first = desktop.post("/api/planner/settings", json={**prefs, "english_percent":70}, headers={"If-Match":revision})
    assert first.status_code == 200
    stale = phone.post("/api/planner/settings", json={**prefs, "english_percent":40}, headers={"If-Match":revision})
    assert stale.status_code == 409
    assert phone.get("/api/planner/settings").json()["english_percent"] == 70


def test_private_modules_and_ielts_are_account_scoped(accounts_app):
    _, _, _, (desktop, other, anonymous) = accounts_app
    login(desktop)
    login(other, "two@example.test")
    for path in ["/lessons", "/dashboard", "/planner/settings", "/planner/week", "/planner/roadmap", "/vocabulary", "/ielts/history", "/widgets/v1/summary", "/sync/snapshot"]:
        assert anonymous.get("/api" + path).status_code == 401
        assert other.get("/api" + path).status_code == 200
    run = desktop.post("/api/ielts/tests/reading-bikes/runs", json={"request_id":str(uuid4())}).json()
    assert other.get("/api/ielts/runs/" + run["id"]).status_code == 404
    assert other.get("/api/ielts/history").json() == []


def test_expiry_refresh_concurrency_and_provider_outage(accounts_app):
    _, manager, boundary, (desktop, _, _) = accounts_app
    login(desktop)
    cookie = desktop.cookies.get(COOKIE)
    with manager.connection() as db:
        db.execute("UPDATE sessions SET token_expires=?", (time.time()-1,))
    with ThreadPoolExecutor(max_workers=3) as pool:
        identities = list(pool.map(manager.resolve, [cookie]*3))
    assert len({user["id"] for user in identities}) == 1
    assert boundary.refresh_count == 1
    boundary.offline = True
    assert desktop.get("/api/progress").status_code == 503
    boundary.offline = False
    assert desktop.get("/api/progress").status_code == 200
    with manager.connection() as db:
        db.execute("UPDATE sessions SET session_expires=?", (time.time()-1,))
    assert desktop.get("/api/progress").status_code == 401


def test_provider_identity_validation_and_request_limits(accounts_app):
    from fastapi import HTTPException
    _, manager, _, (client, _, _) = accounts_app
    for user in [{"id":"../data", "email":"one@example.test", "email_confirmed_at":"now"},
                 {"id":USERS["one@example.test"], "email":"one@example.test"}]:
        with pytest.raises(HTTPException) as error:
            manager.identity(user)
        assert error.value.status_code == 401
    for _ in range(5):
        assert client.post("/api/auth/code", json={"email":"one@example.test"}).status_code == 200
    assert client.post("/api/auth/code", json={"email":"one@example.test"}).status_code == 429


def test_import_preserves_every_legacy_row_and_refuses_overwrite(database, tmp_path):
    import sqlite3
    from contextlib import closing
    from scripts.import_account import import_profile
    # A legacy demo attempt remains a legacy row and cannot manufacture V2 XP.
    with closing(sqlite3.connect(database)) as db:
        exercise = db.execute("SELECT id FROM exercise LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO attempt(exercise_id,answer,is_correct,earned_points,created_at) VALUES (?, 'demo', 1, 1000, '2026-11-05 10:00:00')", (exercise,))
        db.commit()
    original = snapshot(database)
    destination, saved = import_profile(database, tmp_path / "imported", USERS["one@example.test"])
    assert snapshot(destination) == original == snapshot(saved) == snapshot(database)
    with pytest.raises(FileExistsError):
        import_profile(database, destination.parent, USERS["one@example.test"])
    engine = make_engine("sqlite:///" + destination.as_posix())
    with TestClient(create_app(engine)) as client:
        assert client.get("/api/progress").json()["total_xp"] == 0
    engine.dispose()
