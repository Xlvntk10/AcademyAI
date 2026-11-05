"""Data transfer shared by initial cloud provisioning and the offline importer."""
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4
import sqlalchemy as sa
from app.database.db import make_engine

SCHEMA = "academy"


def read_profile(path):
    from scripts.prepare_db import verify
    verify(path)
    source = make_engine("sqlite:///" + Path(path).resolve().as_posix())
    try:
        metadata = sa.MetaData()
        metadata.reflect(source)
        with source.connect() as connection:
            return {table.name: [dict(row) for row in connection.execute(table.select()).mappings()]
                    for table in metadata.sorted_tables if table.name != "alembic_version"}
    finally:
        source.dispose()


@lru_cache(maxsize=1)
def empty_profile():
    from scripts.prepare_db import migrate
    from app.accounts import _migration_lock
    # Temporary SQLite only builds the existing authored catalogue. PostgreSQL
    # receives every persistent user record, including settings and identity.
    with _migration_lock, TemporaryDirectory(prefix="academy-content-") as folder:
        path = Path(folder) / "content.db"
        migrate(path)
        return read_profile(path)


def set_owner(connection, user_id):
    user_id = str(UUID(user_id))
    connection.execute(sa.text("SELECT set_config('app.user_id', :id, true)"), {"id": user_id})
    connection.execute(sa.text("SET LOCAL TIME ZONE 'UTC'"))
    connection.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:id, 0))"), {"id": user_id})
    return user_id


def copy_profile(connection, user_id, profile, fresh=False):
    user_id = set_owner(connection, user_id)
    metadata = sa.MetaData(schema=SCHEMA)
    metadata.reflect(connection, schema=SCHEMA)
    tables = [table for table in metadata.sorted_tables if table.schema == SCHEMA and table.name != "alembic_version"]
    if set(profile) != {table.name for table in tables}:
        raise ValueError("Profile schema does not match the cloud schema")
    for table in tables:
        if connection.execute(sa.select(sa.func.count()).select_from(table).where(table.c.user_id == user_id)).scalar_one():
            raise ValueError("Destination account already contains data")
    for table in tables:
        rows = [{**row, "user_id": user_id} for row in profile[table.name]]
        if fresh and table.name == "syncidentity":
            rows = [{"id": 1, "server_id": str(uuid4()), "user_id": user_id}]
        if rows:
            connection.execute(table.insert(), rows)
    # Compare typed values, not just counts, before the transaction can commit.
    for table in tables:
        if fresh and table.name == "syncidentity":
            continue
        columns = [col for col in table.c if col.name != "user_id"]
        actual = [dict(row) for row in connection.execute(sa.select(*columns).where(table.c.user_id == user_id)).mappings()]
        if sorted(actual, key=repr) != sorted(profile[table.name], key=repr):
            raise ValueError("Cloud verification failed for " + table.name)
