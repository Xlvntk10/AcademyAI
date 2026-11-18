"""Supabase email OTP and opaque server sessions for the single-host pilot."""
from dataclasses import dataclass
from contextlib import contextmanager, closing
import hashlib
import math
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlparse
from uuid import UUID

import httpx
from fastapi import HTTPException
from app.database.db import make_engine

COOKIE = "academy_session"
SESSION_SECONDS = 30 * 24 * 3600
_migration_lock = threading.Lock()


@dataclass(frozen=True)
class AccountConfig:
    origin: str
    supabase_url: str
    publishable_key: str
    directory: Path | None

    @property
    def secure(self):
        return self.origin.startswith("https://")

    @classmethod
    def from_environment(cls, cloud=False):
        mode = os.environ.get("ACADEMY_AUTH_MODE", "local")
        if mode == "local":
            return None
        if mode != "supabase":
            raise RuntimeError("ACADEMY_AUTH_MODE must be local or supabase")
        origin = os.environ.get("ACADEMY_PUBLIC_ORIGIN", "").rstrip("/")
        parsed = urlparse(origin)
        if parsed.path or parsed.query or parsed.fragment or parsed.username or not parsed.netloc:
            raise RuntimeError("Set ACADEMY_PUBLIC_ORIGIN to one exact frontend origin")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}):
            raise RuntimeError("Account mode requires HTTPS, except loopback development")
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
        provider_url = urlparse(url)
        if (provider_url.scheme != "https" or not provider_url.hostname or provider_url.username
                or provider_url.password or provider_url.path or provider_url.query or provider_url.fragment
                or not key.startswith("sb_publishable_")):
            raise RuntimeError("Set SUPABASE_URL and its sb_publishable_ key")
        directory = os.environ.get("ACADEMY_ACCOUNTS_DIR", "")
        if cloud:
            return cls(origin, url, key, None)
        if not directory or not Path(directory).is_absolute():
            raise RuntimeError("Set ACADEMY_ACCOUNTS_DIR to a private absolute directory on persistent storage")
        return cls(origin, url, key, Path(directory))


class SupabaseAuth:
    def __init__(self, config, transport=None):
        self.config = config
        self.transport = transport

    def call(self, method, path, body=None, token=None):
        headers = {"apikey": self.config.publishable_key}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            with httpx.Client(base_url=self.config.supabase_url + "/auth/v1/", timeout=10,
                              transport=self.transport, trust_env=False) as client:
                response = client.request(method, path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise HTTPException(503, "Сервис входа временно недоступен. Локальные ответы сохранены.") from exc
        if response.status_code >= 500:
            raise HTTPException(503, "Сервис входа временно недоступен")
        if response.status_code == 429:
            raise HTTPException(429, "Слишком много запросов. Подожди перед повторной попыткой.")
        if not response.is_success:
            raise HTTPException(401, "Код или сессия недействительны. Запроси новый код.")
        try:
            result = response.json() if response.content else {}
        except ValueError as exc:
            raise HTTPException(503, "Сервис входа вернул некорректный ответ. Повтори позже.") from exc
        if not isinstance(result, dict):
            raise HTTPException(503, "Сервис входа вернул некорректный ответ. Повтори позже.")
        return result

    def send_code(self, email, register):
        try:
            self.call("POST", "otp", {"email": email, "create_user": register})
        except HTTPException as exc:
            if exc.status_code != 401:
                raise
        # Do not disclose whether an address already has an account.

    def verify(self, email, code):
        return self.tokens(self.call("POST", "verify", {"email": email, "token": code, "type": "email"}))

    @staticmethod
    def tokens(value):
        expires = value.get("expires_in")
        if (not all(isinstance(value.get(key), str) and value[key] for key in ("access_token", "refresh_token"))
                or isinstance(expires, bool) or not isinstance(expires, (int, float))
                or not math.isfinite(expires) or expires <= 0):
            raise HTTPException(503, "Сервис входа вернул некорректную сессию. Повтори позже.")
        return value

    def user(self, token):
        return self.call("GET", "user", token=token)

    def refresh(self, token):
        return self.tokens(self.call("POST", "token?grant_type=refresh_token", {"refresh_token": token}))

    def logout(self, token):
        self.call("POST", "logout?scope=local", token=token)


class Accounts:
    def __init__(self, config, provider=None):
        self.config = config
        self.provider = provider or SupabaseAuth(config)
        self.directory = config.directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.registry = self.directory / "sessions.sqlite3"
        self.realm = hashlib.sha256(config.supabase_url.encode()).hexdigest()[:16]
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account_meta (realm TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL, email TEXT NOT NULL,
                    access_token TEXT NOT NULL, refresh_token TEXT NOT NULL,
                    token_expires REAL NOT NULL, session_expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_limits (
                    bucket TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
            """)
            realm = db.execute("SELECT realm FROM account_meta").fetchone()
            if realm and realm[0] != self.realm:
                raise RuntimeError("Use a different ACADEMY_ACCOUNTS_DIR for another Supabase project")
            db.execute("INSERT OR IGNORE INTO account_meta VALUES (?)", (self.realm,))

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.registry, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def identity(self, user):
        try:
            user_id = str(UUID(user["id"]))
            email = user["email"]
            if not user.get("email_confirmed_at") or not isinstance(email, str):
                raise ValueError("Unconfirmed email")
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(401, "Подтверди email через сервис входа") from exc
        return {"id": user_id, "email": email, "namespace": f"acct-{self.realm}-{user_id}"}

    def tenant_engine(self, user_id):
        from scripts.prepare_db import migrate
        path = self.directory / (str(UUID(user_id)) + ".db")
        # SQLite serializes first-account creation across processes. Alembic also
        # uses module state, so serialize migrations across threads in this process.
        with _migration_lock, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not path.exists():
                staging = self.directory / (str(UUID(user_id)) + ".creating-" + secrets.token_hex(8) + ".db")
                migrate(staging)
                staging.rename(path)
            else:
                with closing(sqlite3.connect(path)) as tenant:
                    row = tenant.execute("SELECT version_num FROM alembic_version").fetchone()
                if row != ("0009_offline_sync",):
                    raise HTTPException(503, "База аккаунта требует безопасной миграции")
        return make_engine("sqlite:///" + path.as_posix())

    @staticmethod
    def digest(cookie):
        return hashlib.sha256(cookie.encode()).hexdigest()

    def rate_limit(self, action, address, email):
        now = time.time()
        limit = 5 if action == "code" else 10
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM auth_limits WHERE started < ?", (now - 600,))
            for subject in ("ip:" + address, "email:" + email):
                bucket = action + self.digest(subject)
                row = db.execute("SELECT count FROM auth_limits WHERE bucket=?", (bucket,)).fetchone()
                if row and row[0] >= limit:
                    raise HTTPException(429, "Слишком много попыток входа. Повтори через 10 минут.")
                db.execute("INSERT INTO auth_limits VALUES (?, ?, 1) ON CONFLICT(bucket) DO UPDATE SET count=count+1", (bucket, now))

    def create_session(self, email, code):
        tokens = self.provider.verify(email, code)
        identity = self.identity(self.provider.user(tokens["access_token"]))
        engine = self.tenant_engine(identity["id"])
        engine.dispose()
        cookie = secrets.token_urlsafe(32)
        now = time.time()
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE session_expires < ?", (now,))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?)", (
                self.digest(cookie), identity["id"], identity["email"], tokens["access_token"],
                tokens["refresh_token"], now + tokens["expires_in"], now + SESSION_SECONDS))
        return cookie, identity

    def resolve(self, cookie):
        if not cookie or len(cookie) > 256:
            raise HTTPException(401, "Войди в аккаунт")
        with self.connection() as db:
            # Refresh token rotation is atomic across concurrent device requests.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM sessions WHERE digest=?", (self.digest(cookie),)).fetchone()
            if not row or row["session_expires"] <= time.time():
                raise HTTPException(401, "Сессия закончилась. Войди снова.")
            access = row["access_token"]
            if row["token_expires"] <= time.time() + 60:
                tokens = self.provider.refresh(row["refresh_token"])
                access = tokens["access_token"]
                identity = self.identity(self.provider.user(access))
                if identity["id"] != row["user_id"]:
                    raise HTTPException(401, "Аккаунт сессии изменился")
                db.execute("UPDATE sessions SET access_token=?, refresh_token=?, token_expires=? WHERE digest=?", (
                    access, tokens["refresh_token"], time.time() + tokens["expires_in"], row["digest"]))
            else:
                identity = self.identity(self.provider.user(access))
            if identity["id"] != row["user_id"]:
                raise HTTPException(401, "Аккаунт сессии изменился")
        return identity

    def logout(self, cookie, expected_id=None):
        if not cookie:
            return
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT access_token, user_id FROM sessions WHERE digest=?", (self.digest(cookie),)).fetchone()
            if row and expected_id is not None and row["user_id"] != expected_id:
                raise HTTPException(409, "Аккаунт изменился. Открой приложение заново.")
            db.execute("DELETE FROM sessions WHERE digest=?", (self.digest(cookie),))
        if row:
            try:
                self.provider.logout(row[0])
            except HTTPException:
                pass  # The local opaque session is already permanently revoked.
