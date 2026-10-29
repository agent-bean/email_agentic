import asyncio
from types import SimpleNamespace

from email_agentic.worker import Worker


async def test_shutdown_stops_claiming_and_drains_inflight_work_before_exit():
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    class Jobs:
        claims = 0

        async def recover(self):
            pass

        async def claim(self, **kwargs):
            self.claims += 1
            return {'id': 'inflight'} if self.claims == 1 else None

    jobs = Jobs()
    settings = SimpleNamespace(
        email_automation_enabled=False, calendar_automation_enabled=False,
    )
    worker = Worker(SimpleNamespace(jobs=jobs, settings=settings), None)

    async def schedule():
        pass

    async def process(job):
        started.set()
        await release.wait()
        finished.set()

    worker.schedule = schedule
    worker.process = process
    task = asyncio.create_task(worker.run())
    await asyncio.wait_for(started.wait(), 1)
    worker.stopping.set()
    await asyncio.sleep(0)
    assert not task.done()
    assert not finished.is_set()
    claims = jobs.claims
    release.set()
    await asyncio.wait_for(task, 1)
    assert finished.is_set()
    assert jobs.claims == claims


async def test_shutdown_during_recovery_does_not_claim_new_work():
    class Jobs:
        claims = 0

        async def recover(self):
            worker.stopping.set()

        async def claim(self, **kwargs):
            self.claims += 1
            return None

    jobs = Jobs()
    settings = SimpleNamespace(
        email_automation_enabled=False, calendar_automation_enabled=False,
    )
    worker = Worker(SimpleNamespace(jobs=jobs, settings=settings), None)

    async def schedule():
        pass

    worker.schedule = schedule
    await asyncio.wait_for(worker.run(), 1)

    assert jobs.claims == 0
