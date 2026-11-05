"""PostgreSQL backup and restore into an empty database, using local PostgreSQL tools."""
import argparse
import os
from pathlib import Path
import subprocess
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.database.db import make_engine


def pg_environment(url):
    parsed = make_url(url)
    if parsed.get_backend_name() not in {"postgresql", "postgres"}:
        raise ValueError("PostgreSQL URL required")
    environment = {**os.environ, "PGHOST": parsed.host or "localhost", "PGPORT": str(parsed.port or 5432),
                   "PGUSER": parsed.username or "", "PGPASSWORD": parsed.password or "",
                   "PGDATABASE": parsed.database or "postgres", "PGCONNECT_TIMEOUT": "15"}
    for option in ("sslmode", "sslrootcert"):
        if option in parsed.query:
            environment["PG" + option.upper()] = parsed.query[option]
    return environment


def run_tool(name, arguments, url, bin_dir=None):
    executable = str(bin_dir / name) if bin_dir else name
    result = subprocess.run([executable, *arguments], env=pg_environment(url),
                            capture_output=True, text=True, encoding="utf8", errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        # Avoid echoing libpq diagnostics that may contain connection details.
        raise RuntimeError(f"{name} failed with exit code {result.returncode}. Check tool version, credentials, TLS and database privileges.")


def backup_cloud(url, destination, bin_dir=None):
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_tool("pg_dump", ["--format=custom", "--no-owner", "--no-privileges",
             "--schema=academy", "--schema=academy_auth", "--schema=academy_migrations",
             "--file=" + str(destination)], url, bin_dir)
    run_tool("pg_restore", ["--list", str(destination)], url, bin_dir)
    if destination.stat().st_size == 0:
        raise RuntimeError("Empty backup")


def restore_cloud(url, source, bin_dir=None):
    if not source.is_file():
        raise FileNotFoundError(source)
    engine = make_engine(url)
    try:
        with engine.connect() as connection:
            count = connection.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname IN ('academy','academy_auth','academy_migrations')")).scalar_one()
            if count:
                raise ValueError("Restore requires a destination without Academy schemas. Use a separate empty database.")
        run_tool("pg_restore", ["--single-transaction", "--exit-on-error", "--no-owner", "--no-privileges",
                 "--dbname=" + (engine.url.database or "postgres"), str(source)], url, bin_dir)
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("file", type=Path)
    parser.add_argument("--bin-dir", type=Path, help="Directory containing pg_dump and pg_restore")
    args = parser.parse_args()
    url = os.environ["MIGRATION_DATABASE_URL"]
    operation = backup_cloud if args.action == "backup" else restore_cloud
    operation(url, args.file, args.bin_dir)
    print("Backup verified" if args.action == "backup" else "Restore complete. Reapply runtime grants and verify data before switching traffic.")
