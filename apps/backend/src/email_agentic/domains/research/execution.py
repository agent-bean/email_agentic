from datetime import datetime, UTC

from psycopg.types.json import Jsonb


RESEARCH_JOBS = {"research", "resume", "approval_resume"}


async def reserve_provider_attempt(connection, job, key):
    row = await (await connection.execute(
        "SELECT config FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE",
        (job["entity_id"], job["owner"]),
    )).fetchone()
    attempts = row["config"].get("provider_attempts", {})
    count = attempts.get(key, 0)
    if count >= 3:
        return False
    attempts[key] = count + 1
    await connection.execute(
        "UPDATE research_runs SET config=jsonb_set(config,'{provider_attempts}',%s) WHERE id=%s",
        (Jsonb(attempts), job["entity_id"]),
    )
    return True


async def begin_processing(connection, job):
    run = await (await connection.execute(
        "SELECT config,elapsed_seconds FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE",
        (job["entity_id"], job["owner"]),
    )).fetchone()
    budget = run["config"].get("processing_budget", {})
    if budget.get("claim_token") and budget["claim_token"] != str(job["claim_token"]):
        previous = await (await connection.execute(
            "SELECT * FROM jobs WHERE claim_token=%s AND entity_id=%s",
            (budget["claim_token"], job["entity_id"]),
        )).fetchone()
        if previous:
            await settle_processing(connection, previous, recovered=True)
            run = await (await connection.execute(
                "SELECT config,elapsed_seconds FROM research_runs WHERE id=%s", (job["entity_id"],),
            )).fetchone()
            budget = run["config"].get("processing_budget", {})
    spent = budget.get("spent_seconds", run["elapsed_seconds"] or 0)
    remaining = max(0, run["config"]["timeout_seconds"] - spent)
    now = datetime.now(UTC)
    await connection.execute(
        "UPDATE research_runs SET config=jsonb_set(config,'{processing_budget}',%s) WHERE id=%s",
        (Jsonb({"spent_seconds": spent, "started_at": now.isoformat(),
                "claim_token": str(job["claim_token"])}), job["entity_id"]),
    )
    return remaining


async def settle_processing(connection, job, *, recovered=False):
    if job["kind"] not in RESEARCH_JOBS:
        return
    run = await (await connection.execute(
        "SELECT config FROM research_runs WHERE id=%s AND owner=%s FOR UPDATE",
        (job["entity_id"], job["owner"]),
    )).fetchone()
    if not run:
        return
    budget = run["config"].get("processing_budget", {})
    if budget.get("claim_token") != str(job["claim_token"]):
        return
    end = datetime.now(UTC)
    if recovered and job["lease_until"] is not None:
        # After a crash the last lease bounds the uncertain active interval;
        # never charge the downtime before the next worker recovers this job.
        end = min(end, job["lease_until"])
    duration = max(0, (end - datetime.fromisoformat(budget["started_at"])).total_seconds())
    spent = min(run["config"]["timeout_seconds"], budget["spent_seconds"] + duration)
    await connection.execute(
        "UPDATE research_runs SET config=jsonb_set(config,'{processing_budget}',%s) WHERE id=%s",
        (Jsonb({"spent_seconds": spent, "last_claim_token": str(job["claim_token"])}), job["entity_id"]),
    )


async def fail_processing(connection, job, error):
    if job["kind"] in RESEARCH_JOBS:
        await connection.execute(
            """UPDATE research_runs SET status='failed',error_code=%s,updated_at=now()
            WHERE id=%s AND owner=%s AND status IN ('queued','running','awaiting_identity')
            AND (config->'processing_budget'->>'claim_token' IS NULL
                 OR config->'processing_budget'->>'claim_token'=%s)
            AND (config->'processing_budget'->>'last_claim_token' IS NULL
                 OR config->'processing_budget'->>'last_claim_token'=%s)
            AND NOT EXISTS (SELECT 1 FROM jobs newer WHERE newer.entity_id=research_runs.id
                AND newer.id<>%s AND newer.kind IN ('research','resume','approval_resume')
                AND (newer.status='pending' OR (newer.status='running' AND newer.lease_until>now())))""",
            (error, job["entity_id"], job["owner"], str(job["claim_token"]), str(job["claim_token"]), job["id"]),
        )
