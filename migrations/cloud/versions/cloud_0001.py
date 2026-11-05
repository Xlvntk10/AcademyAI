"""Shared PostgreSQL tables, owner-scoped keys and enforced row policies."""
from pathlib import Path
from alembic import op

revision = "cloud_0001"
down_revision = None
branch_labels = depends_on = None


def upgrade():
    sql = (Path(__file__).parents[1] / "schema_v1.sql").read_text(encoding="utf8")
    for statement in sql.split(";"):
        if statement.strip():
            op.execute(statement)
    op.execute("""CREATE TABLE academy_auth.users (
        user_id varchar(36) PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE academy_auth.meta (
        id integer PRIMARY KEY CHECK (id=1), realm text NOT NULL)""")
    op.execute("""CREATE TABLE academy_auth.sessions (
        digest text PRIMARY KEY, user_id varchar(36) NOT NULL REFERENCES academy_auth.users(user_id),
        email text NOT NULL, access_token text NOT NULL, refresh_token text NOT NULL,
        token_expires double precision NOT NULL, session_expires double precision NOT NULL)""")
    op.execute("""CREATE TABLE academy_auth.auth_limits (
        bucket text PRIMARY KEY, started double precision NOT NULL, count integer NOT NULL)""")
    # Every tenant row belongs to a registered owner, including legacy imports.
    from sqlalchemy import inspect
    for table in inspect(op.get_bind()).get_table_names(schema="academy"):
        op.execute(f'ALTER TABLE academy."{table}" ADD CONSTRAINT owner_fk FOREIGN KEY (user_id) REFERENCES academy_auth.users(user_id)')


def downgrade():
    raise RuntimeError("Restore a verified PostgreSQL backup into a separate database instead of deleting live data")
