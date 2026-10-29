"""Database backup prerequisite for administrative data changes."""

import os
import subprocess
from datetime import datetime, UTC
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict


def backup_database(dsn, directory, purpose):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"before-{purpose}-{datetime.now(UTC):%Y%m%dT%H%M%S%f}.sql"
    environment = dict(os.environ)
    for key, value in conninfo_to_dict(dsn).items():
        variable = {
            "host": "PGHOST",
            "port": "PGPORT",
            "dbname": "PGDATABASE",
            "user": "PGUSER",
            "password": "PGPASSWORD",
            "sslmode": "PGSSLMODE",
        }.get(key)
        if variable:
            environment[variable] = value
    with path.open("xb") as stream:
        path.chmod(0o600)
        result = subprocess.run(
            ["pg_dump", "--no-owner", "--no-acl"], env=environment, stdout=stream, stderr=subprocess.DEVNULL
        )
    if result.returncode or not path.stat().st_size:
        raise RuntimeError("Backup failed; no changes were applied")
    return path
