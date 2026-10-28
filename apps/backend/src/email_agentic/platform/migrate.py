import argparse
import hashlib
import os
from pathlib import Path
import subprocess
from datetime import datetime, UTC

import psycopg

from email_agentic.platform.config import get_settings


def migrate():
    parser = argparse.ArgumentParser(description="Back up database, then apply checked SQL migrations")
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()
    settings = get_settings()
    directory = Path(args.backup_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = directory / f"before-migration-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.sql"
    from psycopg.conninfo import conninfo_to_dict

    parameters = conninfo_to_dict(settings.dsn)
    environment = dict(os.environ)
    for key, variable in {
        "host": "PGHOST",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
    }.items():
        if key in parameters:
            environment[variable] = parameters[key]
    with backup.open("xb") as stream:
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-acl"], env=environment, stdout=stream, stderr=subprocess.DEVNULL
        )
    backup.chmod(0o600)
    if result.returncode or backup.stat().st_size == 0:
        raise SystemExit("Backup failed; no schema changes were applied")
    location = Path(__file__).resolve().parents[3] / "migrations"
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(4782041)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, checksum text NOT NULL)"
        )
        for file in sorted(location.glob("*.sql")):
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            previous = connection.execute(
                "SELECT checksum FROM schema_migrations WHERE name=%s", (file.name,)
            ).fetchone()
            if previous:
                if previous[0] != digest:
                    raise SystemExit("An applied migration checksum changed")
                continue
            connection.execute(file.read_text(), prepare=False)
            connection.execute("INSERT INTO schema_migrations VALUES (%s,%s)", (file.name, digest))
    from langgraph.checkpoint.postgres import PostgresSaver

    with psycopg.connect(settings.dsn, autocommit=True, prepare_threshold=0) as connection:
        PostgresSaver(connection).setup()
    print("Database backup and migrations completed")


if __name__ == "__main__":
    migrate()
