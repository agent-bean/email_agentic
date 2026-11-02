"""Durable execution accounting for intake jobs that do not yet have a research run."""

from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from email_agentic.platform.errors import JobLeaseLost


INTAKE_JOBS = {"email_intake", "calendar_intake"}


async def begin_intake(connection, job, timeout):
    row = await (await connection.execute(
        "SELECT execution FROM jobs WHERE id=%s AND claim_token=%s AND status='running' AND lease_until>now() FOR UPDATE",
        (job["id"], job["claim_token"]),
    )).fetchone()
    if row is None:
        raise JobLeaseLost("Job lease lost")
    execution = row["execution"]
    limit = execution.setdefault("timeout_seconds", timeout)
    budget = execution.setdefault("processing_budget", {"spent_seconds": 0})
    budget.update(started_at=datetime.now(UTC).isoformat(), claim_token=str(job["claim_token"]))
    await connection.execute("UPDATE jobs SET execution=%s WHERE id=%s", (Jsonb(execution), job["id"]))
    return max(0, limit - budget["spent_seconds"])


async def reserve_intake_attempt(connection, job, key):
    row = await (await connection.execute(
        "SELECT execution FROM jobs WHERE id=%s AND claim_token=%s AND status='running' AND lease_until>now() FOR UPDATE",
        (job["id"], job["claim_token"]),
    )).fetchone()
    if row is None:
        raise JobLeaseLost("Job lease lost")
    execution = row["execution"]
    attempts = execution.setdefault("provider_attempts", {})
    if attempts.get(key, 0) >= 3:
        return False
    attempts[key] = attempts.get(key, 0) + 1
    await connection.execute("UPDATE jobs SET execution=%s WHERE id=%s", (Jsonb(execution), job["id"]))
    return True


async def settle_intake(connection, job, *, recovered=False):
    if job["kind"] not in INTAKE_JOBS:
        return
    execution = job["execution"]
    budget = execution.get("processing_budget", {})
    if budget.get("claim_token") != str(job["claim_token"]):
        return
    end = min(datetime.now(UTC), job["lease_until"]) if recovered else datetime.now(UTC)
    spent = budget["spent_seconds"] + max(0, (end - datetime.fromisoformat(budget["started_at"])).total_seconds())
    execution["processing_budget"] = {"spent_seconds": min(execution["timeout_seconds"], spent)}
    await connection.execute("UPDATE jobs SET execution=%s WHERE id=%s", (Jsonb(execution), job["id"]))
