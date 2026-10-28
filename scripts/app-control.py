"""Run the local architecture stack without echoing secrets or touching the VPS."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=["db", "build", "migrate", "up", "down", "test", "check", "status"],
    )
    args = parser.parse_args()
    environment = {
        **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v is not None},
        **os.environ,
    }
    local = ROOT / ".runtime/local-stack.env"
    if not local.exists():
        local.parent.mkdir(exist_ok=True)
        descriptor = os.open(local, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            stream.write("GRAFANA_ADMIN_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
    environment.update(
        {
            k: v
            for k, v in dotenv_values(local).items()
            if k not in environment and v is not None
        }
    )
    compose = [
        "docker",
        "compose",
        "-f",
        str(ROOT / "infra/compose.yaml"),
        "-f",
        str(ROOT / "infra/compose.local.yaml"),
    ]
    commands = {
        "db": compose + ["up", "-d", "--wait", "postgres"],
        "build": compose + ["build", "api"],
        "migrate": compose + ["run", "--rm", "migrate"],
        "up": compose
        + ["up", "-d", "--wait", "api", "worker", "prometheus", "tempo", "grafana"],
        "down": compose + ["down"],
        "check": compose + ["config", "--quiet"],
        "status": compose + ["ps"],
    }
    if args.command == "test":
        # Back up the local application before establishing the separate test database.
        subprocess.run(
            compose + ["run", "--rm", "migrate"], cwd=ROOT, env=environment, check=True
        )
        setup = """import psycopg
from psycopg.conninfo import conninfo_to_dict
from email_agentic.platform.config import get_settings
parameters=conninfo_to_dict(get_settings().dsn)
parameters['dbname']='postgres'
with psycopg.connect(**parameters,autocommit=True) as connection:
 if not connection.execute("SELECT 1 FROM pg_database WHERE datname='email_agentic_test'").fetchone():
  connection.execute('CREATE DATABASE email_agentic_test')
print('Separate local test database ready')
"""
        subprocess.run(
            compose + ["run", "--rm", "migrate", "python", "-c", setup],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        password = quote(environment.get("POSTGRES_PASSWORD", ""), safe="")
        environment["DATABASE_URL"] = (
            f"postgresql://email_agentic:{password}@postgres:5432/email_agentic_test"
        )
        subprocess.run(
            compose + ["run", "--rm", "--env", "DATABASE_URL", "migrate"],
            cwd=ROOT,
            env=environment,
            check=True,
        )
        environment.pop("DATABASE_URL")
        environment["TEST_DATABASE_URL"] = (
            f"postgresql://email_agentic:{password}@127.0.0.1:5432/email_agentic_test"
        )
        command = [
            "uv",
            "run",
            "--project",
            "apps/backend",
            "pytest",
            "apps/backend/tests",
            "-q",
        ]
    else:
        command = commands[args.command]
    result = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
