"""Persistent PostgreSQL sessions using the existing Supabase Auth boundary."""
import hashlib
import secrets
import time
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import text
from app.accounts import Accounts, SupabaseAuth, SESSION_SECONDS
from app.database.cloud import copy_profile, empty_profile


class CloudAccounts(Accounts):
    def __init__(self, config, engine, provider=None):
        self.config = config
        self.engine = engine
        self.provider = provider or SupabaseAuth(config)
        self.realm = hashlib.sha256(config.supabase_url.encode()).hexdigest()[:16]
        with engine.begin() as connection:
            role = connection.execute(text("SELECT rolsuper, rolbypassrls, rolcreaterole FROM pg_roles WHERE rolname=current_user")).one()
            elevated_membership = connection.execute(text("""SELECT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname != current_user
                AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolname IN ('pg_read_all_data','pg_write_all_data'))
                AND pg_has_role(current_user, oid, 'MEMBER'))""")).scalar_one()
            if role.rolsuper or role.rolbypassrls or role.rolcreaterole or elevated_membership:
                raise RuntimeError("Runtime PostgreSQL role must be NOSUPERUSER NOBYPASSRLS")
            unsafe = connection.execute(text("""SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='academy' AND c.relkind='r' AND (NOT c.relrowsecurity OR NOT c.relforcerowsecurity)""")).scalar_one()
            if unsafe:
                raise RuntimeError("Every academy table must enforce row security")
            connection.execute(text("INSERT INTO academy_auth.meta VALUES (1, :realm) ON CONFLICT DO NOTHING"), {"realm": self.realm})
            saved = connection.execute(text("SELECT realm FROM academy_auth.meta WHERE id=1")).scalar_one()
            if saved != self.realm:
                raise RuntimeError("This database is already bound to another Supabase project")

    def tenant_engine(self, user_id):
        # Provision only during authenticated login. Requests never create profiles.
        return self.engine

    def provision(self, user_id):
        user_id = str(UUID(user_id))
        profile = empty_profile()
        with self.engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"), {"id": user_id})
            exists = connection.execute(text("SELECT user_id FROM academy_auth.users WHERE user_id=:id"), {"id": user_id}).first()
            if exists:
                return
            connection.execute(text("INSERT INTO academy_auth.users(user_id) VALUES (:id)"), {"id": user_id})
            copy_profile(connection, user_id, profile, fresh=True)

    def rate_limit(self, action, address, email):
        now = time.time()
        limit = 5 if action == "code" else 10
        with self.engine.begin() as connection:
            # Consistent ordering of the two locks prevents cross-request deadlocks.
            buckets = sorted(action + self.digest(value) for value in ("ip:" + address, "email:" + email))
            for bucket in buckets:
                connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 1))"), {"key": bucket})
                row = connection.execute(text("SELECT * FROM academy_auth.auth_limits WHERE bucket=:key"), {"key": bucket}).mappings().first()
                count = row["count"] if row and row["started"] > now - 600 else 0
                if count >= limit:
                    raise HTTPException(429, "Слишком много попыток входа. Повтори через 10 минут.")
                connection.execute(text("""INSERT INTO academy_auth.auth_limits VALUES (:key, :started, :count)
                    ON CONFLICT(bucket) DO UPDATE SET started=excluded.started, count=excluded.count"""),
                    {"key": bucket, "started": row["started"] if count else now, "count": count + 1})
            connection.execute(text("DELETE FROM academy_auth.auth_limits WHERE started < :old"), {"old": now - 1200})

    def create_session(self, email, code):
        tokens = self.provider.verify(email, code)
        identity = self.identity(self.provider.user(tokens["access_token"]))
        self.provision(identity["id"])
        cookie = secrets.token_urlsafe(32)
        now = time.time()
        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM academy_auth.sessions WHERE session_expires < :now"), {"now": now})
            connection.execute(text("""INSERT INTO academy_auth.sessions
                VALUES (:digest, :user_id, :email, :access, :refresh, :token_expires, :session_expires)"""),
                {"digest": self.digest(cookie), "user_id": identity["id"], "email": identity["email"],
                 "access": tokens["access_token"], "refresh": tokens["refresh_token"],
                 "token_expires": now + tokens["expires_in"], "session_expires": now + SESSION_SECONDS})
        return cookie, identity

    def resolve(self, cookie):
        if not cookie or len(cookie) > 256:
            raise HTTPException(401, "Войди в аккаунт")
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM academy_auth.sessions WHERE digest=:digest FOR UPDATE"),
                                     {"digest": self.digest(cookie)}).mappings().first()
            if not row or row["session_expires"] <= time.time():
                raise HTTPException(401, "Сессия закончилась. Войди снова.")
            access = row["access_token"]
            if row["token_expires"] <= time.time() + 60:
                tokens = self.provider.refresh(row["refresh_token"])
                access = tokens["access_token"]
                identity = self.identity(self.provider.user(access))
                if identity["id"] != row["user_id"]:
                    raise HTTPException(401, "Аккаунт сессии изменился")
                connection.execute(text("""UPDATE academy_auth.sessions SET access_token=:access,
                    refresh_token=:refresh, token_expires=:expires WHERE digest=:digest"""),
                    {"access": access, "refresh": tokens["refresh_token"], "expires": time.time()+tokens["expires_in"], "digest": row["digest"]})
            else:
                identity = self.identity(self.provider.user(access))
            if identity["id"] != row["user_id"]:
                raise HTTPException(401, "Аккаунт сессии изменился")
        return identity

    def logout(self, cookie, expected_id=None):
        if not cookie:
            return
        with self.engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM academy_auth.sessions WHERE digest=:digest FOR UPDATE"),
                                     {"digest": self.digest(cookie)}).mappings().first()
            if row and expected_id is not None and row["user_id"] != expected_id:
                raise HTTPException(409, "Аккаунт изменился. Открой приложение заново.")
            connection.execute(text("DELETE FROM academy_auth.sessions WHERE digest=:digest"), {"digest": self.digest(cookie)})
        if row:
            try:
                self.provider.logout(row["access_token"])
            except HTTPException:
                pass
