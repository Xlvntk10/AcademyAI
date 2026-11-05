"""Copy a stopped SQLite profile into a new PostgreSQL owner transactionally."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import UUID
import sqlalchemy as sa
from app.database.db import make_engine
from app.database.cloud import read_profile, copy_profile, set_owner
from scripts.prepare_db import backup, snapshot


def import_cloud(source, user_id, url, backup_dir):
    user_id = str(UUID(user_id))
    if not url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        raise ValueError("PostgreSQL destination required")
    backup_dir.mkdir(parents=True, exist_ok=True)
    saved = backup_dir / ("cloud-import-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".db")
    backup(source, saved)
    before = snapshot(saved)
    profile = read_profile(saved)
    engine = make_engine(url)
    try:
        with engine.begin() as connection:
            set_owner(connection, user_id)
            if connection.execute(sa.text("SELECT 1 FROM academy_auth.users WHERE user_id=:id"), {"id": user_id}).first():
                raise ValueError("Account already exists. Merge requires a separate reviewed procedure.")
            connection.execute(sa.text("INSERT INTO academy_auth.users(user_id) VALUES (:id)"), {"id": user_id})
            copy_profile(connection, user_id, profile)
            # Import runs during maintenance. Lock tables while advancing sequences
            # so inserts cannot race with explicitly imported legacy integer IDs.
            for name in sorted(profile):
                sequence = connection.execute(sa.text("SELECT to_regclass(:name)"), {"name": f"academy.{name}_id_seq"}).scalar_one()
                if sequence:
                    connection.exec_driver_sql(f'LOCK TABLE academy."{name}" IN ACCESS EXCLUSIVE MODE')
                    connection.exec_driver_sql(f"SELECT setval('academy.{name}_id_seq', GREATEST((SELECT last_value FROM academy.{name}_id_seq), COALESCE((SELECT max(id) FROM academy.\"{name}\"), 1)), true)")
            if snapshot(source) != before:
                raise ValueError("SQLite changed while importing. Stop its API and retry.")
    finally:
        engine.dispose()
    return saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--backup-dir", type=Path, default=Path("backups"))
    args = parser.parse_args()
    saved = import_cloud(args.source, args.user_id, os.environ["MIGRATION_DATABASE_URL"], args.backup_dir)
    print(f"Imported and verified. SQLite backup: {saved}")
