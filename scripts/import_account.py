"""Copy one verified local profile to an unused account with the API stopped."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from scripts.prepare_db import ROOT, backup, connect_readonly, snapshot, verify


def import_profile(source: Path, directory: Path, user_id: str):
    source = source.resolve()
    directory = directory.resolve()
    identifier = str(UUID(user_id))
    destination = directory / (identifier + ".db")
    if destination.exists():
        raise FileExistsError("Account already has a database. Automatic merging is disabled.")
    verify(source)
    with connect_readonly(source) as db:
        if db.execute("SELECT version_num FROM alembic_version").fetchone() != ("0009_offline_sync",):
            raise RuntimeError("Prepare and verify the source database before importing")
    before = snapshot(source)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    saved = directory / ("before-import-" + stamp + ".db")
    backup(source, saved)
    staging = directory / ("import-" + stamp + ".db")
    backup(saved, staging)
    if snapshot(source) != before or snapshot(staging) != before:
        raise RuntimeError("Source changed during copy. Stop the API and retry.")
    # Windows rename refuses an existing destination. The import requires a stopped API.
    staging.rename(destination)
    verify(destination)
    return destination, saved


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "database.db")
    parser.add_argument("--accounts-dir", type=Path, required=True)
    parser.add_argument("--user-id", type=str, required=True, help="Verified Supabase Auth user UUID, before first Academy login")
    args = parser.parse_args()
    destination, saved = import_profile(args.source, args.accounts_dir, args.user_id)
    print(f"Verified profile copy: {destination}\nBackup: {saved}")
