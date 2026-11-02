import asyncio
import uuid
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from email_agentic.platform.database import active_claim
from email_agentic.platform.errors import JobLeaseLost, ProviderFailure
from email_agentic.worker import Worker


def claimed_job():
    return {"id": uuid.uuid4(), "entity_id": uuid.uuid4(), "owner": "owner@example.invalid",
            "kind": "research", "attempt": 1, "claim_token": uuid.uuid4()}


@pytest.mark.parametrize("failure", [JobLeaseLost("Job lease lost"), ProviderFailure("test", transient=True)])
async def test_stale_exception_path_has_no_unfenced_domain_writes(failure):
    completions = []

    async def finish(*args):
        completions.append(args)
        assert active_claim.get() is None
        return False

    # The database exposes only locking: all state changes must belong to finish.
    worker = Worker(SimpleNamespace(jobs=SimpleNamespace(finish=finish), db=SimpleNamespace(run_lock=lambda _: nullcontext())), None)
    job = claimed_job()

    async def handle(value):
        assert active_claim.get() == value
        raise failure

    worker.handle = handle
    await worker.process(job)
    assert len(completions) == (0 if isinstance(failure, JobLeaseLost) else 1)


async def test_failed_heartbeat_cancels_and_drains_inflight_handle():
    started, stopped = asyncio.Event(), asyncio.Event()
    worker = Worker(SimpleNamespace(db=SimpleNamespace(run_lock=lambda _: nullcontext())), None)

    async def handle(job):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def heartbeat(job):
        await started.wait()
        raise JobLeaseLost("Job heartbeat unavailable")

    worker.handle, worker.heartbeat = handle, heartbeat
    await asyncio.wait_for(worker.process(claimed_job()), 1)
    assert stopped.is_set()


async def test_heartbeat_database_failure_is_lease_loss(monkeypatch):
    async def no_delay(_):
        pass

    async def heartbeat(job):
        raise OSError("database unavailable")

    monkeypatch.setattr("email_agentic.worker.asyncio.sleep", no_delay)
    worker = Worker(SimpleNamespace(jobs=SimpleNamespace(heartbeat=heartbeat)), None)
    with pytest.raises(JobLeaseLost, match="heartbeat unavailable"):
        await worker.heartbeat(claimed_job())
