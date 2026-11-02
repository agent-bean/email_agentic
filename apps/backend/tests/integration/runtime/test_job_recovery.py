import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from psycopg.types.json import Jsonb

from email_agentic.domains.research.execution import begin_processing, reserve_provider_attempt
from email_agentic.platform.errors import ProviderFailure
from email_agentic.runtime.jobs import Jobs, enqueue
from email_agentic.worker import Worker


async def research_job(db, attempt=1):
    run_id, token = uuid.uuid4(), uuid.uuid4()
    owner = f"{uuid.uuid4()}@example.invalid"
    await db.execute(
        """INSERT INTO research_runs(id,owner,company_name,domain,context,status,config)
        VALUES(%s,%s,'Recovery test','example.invalid','','running',%s)""",
        (run_id, owner, Jsonb({"timeout_seconds": 30})),
    )
    async with db.transaction() as connection:
        await enqueue(connection, owner, "research", run_id, str(run_id))
    return await db.one(
        """UPDATE jobs SET status='running',attempt=%s,claim_token=%s,
        lease_until=now()+interval '60 seconds' WHERE dedupe_key=%s RETURNING *""",
        (attempt, token, str(run_id)),
    )


async def test_stale_worker_exception_cannot_overwrite_new_owner_state(db):
    job = await research_job(db)
    await db.execute("UPDATE jobs SET claim_token=%s WHERE id=%s", (uuid.uuid4(), job["id"]))
    await db.execute("UPDATE research_runs SET status='draft_ready' WHERE id=%s", (job["entity_id"],))
    worker = Worker(SimpleNamespace(jobs=Jobs(db), db=db), None)

    async def stale_failure(_):
        raise ProviderFailure("test", category="invalid_output")

    worker.handle = stale_failure
    await worker.process(job)
    assert (await db.one("SELECT status FROM research_runs WHERE id=%s", (job["entity_id"],)))["status"] == "draft_ready"
    assert (await db.one("SELECT status FROM jobs WHERE id=%s", (job["id"],)))["status"] == "running"


async def test_completion_rolls_back_domain_failure_if_job_update_fails(db, monkeypatch):
    from email_agentic.runtime import jobs as module

    job = await research_job(db)
    original = module.fail_processing

    async def interrupted(connection, current, error):
        await original(connection, current, error)
        raise OSError("transaction interrupted")

    monkeypatch.setattr(module, "fail_processing", interrupted)
    with pytest.raises(OSError):
        await Jobs(db).finish(job, "failed", "test:error")
    assert (await db.one("SELECT status FROM research_runs WHERE id=%s", (job["entity_id"],)))["status"] == "running"
    assert (await db.one("SELECT status FROM jobs WHERE id=%s", (job["id"],)))["status"] == "running"


@pytest.mark.parametrize("kind", ["email_intake", "calendar_intake"])
async def test_terminal_lease_recovery_fails_pending_triage(db, kind):
    owner = f"{uuid.uuid4()}@example.invalid"
    input_id, entity_id, token = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await db.execute(
        "INSERT INTO inputs(id,owner,provider,source_id,kind,content) VALUES(%s,%s,'google',%s,%s,'{}')",
        (input_id, owner, str(input_id), "email" if kind == "email_intake" else "meeting"),
    )
    if kind == "email_intake":
        entity_id = input_id
        await db.execute("INSERT INTO email_triage(input_id,owner) VALUES(%s,%s)", (input_id, owner))
    else:
        await db.execute("INSERT INTO calendar_triage(id,input_id,owner,revision) VALUES(%s,%s,%s,'v1')",
                         (entity_id, input_id, owner))
    async with db.transaction() as connection:
        await enqueue(connection, owner, kind, entity_id, str(entity_id))
    await db.execute(
        """UPDATE jobs SET status='running',attempt=3,claim_token=%s,
        lease_until=now()-interval '1 second' WHERE dedupe_key=%s""", (token, str(entity_id)),
    )
    await Jobs(db).recover()
    query = "SELECT status,error_code FROM email_triage WHERE input_id=%s" if kind == "email_intake" else "SELECT status,error_code FROM calendar_triage WHERE id=%s"
    assert await db.one(query, (entity_id,)) == {"status": "failed", "error_code": "lease_expired"}


async def test_terminal_lease_recovery_fails_run_and_settles_only_active_lease_interval(db):
    job = await research_job(db, attempt=3)
    now = datetime.now(UTC)
    await db.execute("UPDATE jobs SET lease_until=%s WHERE id=%s", (now - timedelta(seconds=10), job["id"]))
    budget = {"spent_seconds": 2, "started_at": (now - timedelta(seconds=20)).isoformat(),
              "claim_token": str(job["claim_token"])}
    await db.execute("UPDATE research_runs SET config=config || %s WHERE id=%s",
                     (Jsonb({"processing_budget": budget}), job["entity_id"]))
    await Jobs(db).recover()
    run = await db.one("SELECT status,error_code,config FROM research_runs WHERE id=%s", (job["entity_id"],))
    assert (run["status"], run["error_code"]) == ("failed", "lease_expired")
    assert run["config"]["processing_budget"]["spent_seconds"] == pytest.approx(12)
    assert (await db.one("SELECT status FROM jobs WHERE id=%s", (job["id"],)))["status"] == "failed"


@pytest.mark.parametrize("resume_completed", [False, True])
async def test_old_exhausted_job_does_not_fail_newer_resume_or_discard_its_budget(db, resume_completed):
    old = await research_job(db, attempt=3)
    now = datetime.now(UTC)
    await db.execute("UPDATE jobs SET lease_until=%s WHERE id=%s", (now - timedelta(seconds=10), old["id"]))
    budget = {"spent_seconds": 1, "started_at": (now - timedelta(seconds=15)).isoformat(),
              "claim_token": str(old["claim_token"])}
    await db.execute("UPDATE research_runs SET config=config || %s,status='awaiting_identity' WHERE id=%s",
                     (Jsonb({"processing_budget": budget}), old["entity_id"]))
    async with db.transaction() as connection:
        await enqueue(connection, old["owner"], "resume", old["entity_id"], f"resume:{old['id']}")
    current = await db.one(
        """UPDATE jobs SET status='running',attempt=1,claim_token=%s,lease_until=now()+interval '60 seconds'
        WHERE dedupe_key=%s RETURNING *""", (uuid.uuid4(), f"resume:{old['id']}"),
    )
    async with db.transaction() as connection:
        assert await begin_processing(connection, current) == pytest.approx(24)
    if resume_completed:
        assert await Jobs(db).finish(current)
    await Jobs(db).recover()
    run = await db.one("SELECT status,config FROM research_runs WHERE id=%s", (old["entity_id"],))
    assert run["status"] == "awaiting_identity"
    assert run["config"]["processing_budget"]["spent_seconds"] >= 6
    token_key = "last_claim_token" if resume_completed else "claim_token"
    assert run["config"]["processing_budget"][token_key] == str(current["claim_token"])


async def test_retry_and_human_wait_do_not_reset_processing_budget_or_provider_attempts(db):
    job = await research_job(db)
    async with db.transaction() as connection:
        assert await begin_processing(connection, job) == 30
        assert await reserve_provider_attempt(connection, job, "operation")
        assert await reserve_provider_attempt(connection, job, "operation")
    budget = {"spent_seconds": 0, "started_at": (datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
              "claim_token": str(job["claim_token"])}
    await db.execute("UPDATE research_runs SET config=config || %s WHERE id=%s",
                     (Jsonb({"processing_budget": budget}), job["entity_id"]))
    assert await Jobs(db).finish(job, "failed", "test:timeout", retry=True)
    job = await db.one(
        """UPDATE jobs SET status='running',attempt=attempt+1,claim_token=%s,
        lease_until=now()+interval '60 seconds' WHERE id=%s RETURNING *""", (uuid.uuid4(), job["id"]),
    )
    # Completed segments have no start timestamp, so a delayed resume cannot charge human wait.
    async with db.transaction() as connection:
        remaining = await begin_processing(connection, job)
        assert 24 < remaining < 26
        assert await reserve_provider_attempt(connection, job, "operation")
        assert not await reserve_provider_attempt(connection, job, "operation")


async def test_run_lock_serializes_sessions_and_releases_after_cancellation(db):
    run_id = uuid.uuid4()
    acquired, blocked_started, acquired_second = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def owner():
        async with db.run_lock(run_id):
            acquired.set()
            await asyncio.Event().wait()

    async def contender():
        blocked_started.set()
        async with db.run_lock(run_id):
            acquired_second.set()

    first = asyncio.create_task(owner())
    second = None
    try:
        await asyncio.wait_for(acquired.wait(), 2)
        second = asyncio.create_task(contender())
        await blocked_started.wait()
        async with db.run_lock(uuid.uuid4()):
            assert not acquired_second.is_set()
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await asyncio.wait_for(second, 2)
        assert acquired_second.is_set()
    finally:
        first.cancel()
        if second is not None:
            second.cancel()
        await asyncio.gather(*(task for task in (first, second) if task is not None), return_exceptions=True)
