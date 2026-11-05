"""Explicit cloud migrations. Use a migration credential, with a backup prepared."""
import os
from alembic import command
from alembic.config import Config
from scripts.prepare_db import ROOT


def migrate_cloud(url):
    if not url.startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
        raise ValueError("A PostgreSQL migration URL is required")
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations/cloud"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


if __name__ == "__main__":
    migrate_cloud(os.environ["MIGRATION_DATABASE_URL"])
    print("Cloud migrations completed")
