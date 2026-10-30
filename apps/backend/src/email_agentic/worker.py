import asyncio
import logging
import signal
from contextlib import nullcontext, suppress
from datetime import datetime, UTC, timedelta
from zoneinfo import ZoneInfo

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from email_agentic.bootstrap import build_container
from email_agentic.platform.config import get_settings
from email_agentic.platform.database import active_claim
from prometheus_client import start_http_server
from email_agentic.platform.errors import JobLeaseLost, ProviderFailure
from email_agentic.domains.research.execution import begin_processing, reserve_provider_attempt
from email_agentic.runtime.budget import processing_budget
from email_agentic.runtime.execution import INTAKE_JOBS, begin_intake, reserve_intake_attempt
from email_agentic.platform.telemetry import DURATION, JOBS, configure, job_trace_context, tracer
from email_agentic.runtime.jobs import enqueue
from email_agentic.tools.harness import ToolContext
from email_agentic.workflows.research import make_graph

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, c, graph):
        self.c, self.graph = c, graph
        self.stopping = asyncio.Event()
        self.research_slot = asyncio.Semaphore(1)
        self.thread_locks = {}

    async def heartbeat(self, job):
        while True:
            await asyncio.sleep(15)
            try:
                current = await self.c.jobs.heartbeat(job)
            except Exception as exc:
                raise JobLeaseLost("Job heartbeat unavailable") from exc
            if not current:
                raise JobLeaseLost("Job lease lost")

    async def handle(self, job):
        c = self.c
        if job["kind"] in {"research", "resume", "approval_resume"}:
            lock = self.thread_locks.setdefault(str(job["entity_id"]), asyncio.Lock())
            async with lock, self.research_slot:
                run = await c.research.get(job["owner"], job["entity_id"])
                config = {"configurable": {"thread_id": str(run["id"])}, "recursion_limit": 30}
                state = await self.graph.aget_state(config)
                if state.values and not state.next:
                    return
                payload = (
                    Command(resume={"decision_available": True}) if state.next else {"run_id": str(run["id"])}
                )
                async with c.db.transaction() as connection:
                    remaining = await begin_processing(connection, job)

                async def reserve(key):
                    async with c.db.transaction() as connection:
                        return await reserve_provider_attempt(connection, job, key)

                with processing_budget(remaining, reserve):
                    async with asyncio.timeout(remaining):
                        await self.graph.ainvoke(payload, config)
        elif job["kind"] == "publish":
            action = await c.db.one("SELECT * FROM publication_actions WHERE id=%s", (job["entity_id"],))
            context = ToolContext(job["owner"], "publication", frozenset({"publication:execute"}))
            name = "email.send" if action["kind"] == "email" else "knowledge.publish"
            await c.tools.execute(name, {"action_id": str(action["id"])}, context)
        elif job["kind"] == "scan_email":
            context = ToolContext(job["owner"], "scheduler", frozenset({"email:read"}))
            await c.tools.execute("email.read", {"retry_failed": job["dedupe_key"].startswith("manual-sync:")}, context)
        elif job["kind"] == "email_intake":
            await c.email_automation.run(job["owner"], job["entity_id"])
        elif job["kind"] == "calendar_intake":
            await c.calendar_automation.run(job["owner"], job["entity_id"])
        elif job["kind"] == "gmail_draft":
            context = ToolContext(job["owner"], "email", frozenset({"email:draft"}))
            await c.tools.execute("email.draft", {"action_id": str(job["entity_id"])}, context)
        elif job["kind"] == "scan_calendar":
            now = datetime.now(UTC)
            context = ToolContext(job["owner"], "scheduler", frozenset({"calendar:read"}))
            events = await c.tools.execute(
                "calendar.list",
                {"start": now.isoformat(), "end": (now + timedelta(days=7)).isoformat()},
                context,
            )
            await c.calendar_automation.save(job["owner"], events)
        else:
            raise ValueError("Unknown job type")

    async def execute_claim(self, job):
        lock = self.c.db.run_lock(job["entity_id"]) if job["kind"] in {"research", "resume", "approval_resume"} else nullcontext()
        async with lock:
            try:
                token = active_claim.set(job)
                try:
                    if job["kind"] in INTAKE_JOBS:
                        async with self.c.db.transaction() as connection:
                            remaining = await begin_intake(connection, job, self.c.settings.research_timeout_seconds)

                        async def reserve(key):
                            async with self.c.db.transaction() as connection:
                                return await reserve_intake_attempt(connection, job, key)

                        with processing_budget(remaining, reserve):
                            async with asyncio.timeout(remaining):
                                await self.handle(job)
                    else:
                        await self.handle(job)
                finally:
                    active_claim.reset(token)
                if await self.c.jobs.finish(job):
                    JOBS.labels(job["kind"], "succeeded").inc()
            except JobLeaseLost:
                raise
            except Exception as exc:
                retry = (
                    isinstance(exc, ProviderFailure)
                    and exc.transient
                    and not exc.ambiguous
                    and job["attempt"] < 3
                )
                error = f"{exc.provider}:{exc.category}" if isinstance(exc, ProviderFailure) else type(exc).__name__
                if await self.c.jobs.finish(job, "failed", error, retry):
                    JOBS.labels(job["kind"], "failed").inc()
                logger.warning("Job failed: kind=%s category=%s", job["kind"], type(exc).__name__)

    async def process(self, job):
        context, links = job_trace_context(job)
        with DURATION.labels(job["kind"]).time(), tracer().start_as_current_span(
            "job." + job["kind"], context=context, links=links,
            attributes={"job.id": str(job["id"]), "job.kind": job["kind"], "job.attempt": job["attempt"]},
        ):
            # Keep run exclusion through the atomic outcome, not only graph invocation.
            task = asyncio.create_task(self.execute_claim(job))
            heartbeat = asyncio.create_task(self.heartbeat(job))
            try:
                completed, _ = await asyncio.wait({task, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in completed:
                    await heartbeat
                await task
            except JobLeaseLost:
                # Recovery owns the outcome once the lease cannot be established.
                JOBS.labels(job["kind"], "lease_lost").inc()
            except asyncio.CancelledError:
                raise
            finally:
                task.cancel()
                heartbeat.cancel()
                await asyncio.gather(task, heartbeat, return_exceptions=True)

    async def schedule(self):
        c = self.c
        now = datetime.now(ZoneInfo(c.settings.app_timezone))
        ticks = [("scan_calendar", now.strftime("%Y%m%d%H") + f"{now.minute // 15:02}")]
        if now.hour >= 8:
            ticks.append(("scan_email", now.strftime("%Y%m%d")))
        if c.settings.scheduler_enabled:
            async with c.db.transaction() as connection:
                for kind, tick in ticks:
                    inserted = await (
                        await connection.execute(
                            "INSERT INTO schedule_ticks VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING name",
                            (kind, tick),
                        )
                    ).fetchone()
                    if inserted:
                        await enqueue(
                            connection, c.settings.owner_email.casefold(), kind, None, f"{kind}:{tick}"
                        )
        async with c.db.transaction() as connection:
            expired = await (
                await connection.execute(
                    "UPDATE approvals SET status='expired' WHERE status='pending' AND expires_at<=now() RETURNING report_id,id,owner"
                )
            ).fetchall()
            for approval in expired:
                report = await (
                    await connection.execute(
                        "SELECT run_id FROM reports WHERE id=%s", (approval["report_id"],)
                    )
                ).fetchone()
                await enqueue(
                    connection,
                    approval["owner"],
                    "approval_resume",
                    report["run_id"],
                    f"expiry:{approval['id']}",
                )

    async def run(self):
        tasks = set()
        try:
            while not self.stopping.is_set():
                await self.c.jobs.recover()
                await self.schedule()
                if self.stopping.is_set():
                    break
                tasks = {task for task in tasks if not task.done()}
                if len(tasks) < 4:
                    job = await self.c.jobs.claim(
                        excluded=tuple(kind for kind, enabled in (("email_intake", self.c.settings.email_automation_enabled),
                                    ("calendar_intake", self.c.settings.calendar_automation_enabled)) if not enabled)
                    )
                    if job:
                        task = asyncio.create_task(self.process(job))
                        tasks.add(task)
                        continue
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.stopping.wait(), 1)
        finally:
            # SIGTERM stops new claims, then lets bounded in-flight jobs record receipts.
            # Unexpected loop failures still cancel tasks and leave lease recovery intact.
            if not self.stopping.is_set():
                for task in tasks:
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def main():
    settings = get_settings()
    metrics_server, metrics_thread = start_http_server(8001)
    telemetry = configure("email-worker", settings.telemetry_endpoint)
    try:
        async with build_container(settings) as c:
            async with await AsyncConnection.connect(
                settings.dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row
            ) as connection:
                graph = make_graph(c, AsyncPostgresSaver(connection))
                worker = Worker(c, graph)
                loop = asyncio.get_running_loop()
                for signum in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(signum, worker.stopping.set)
                await worker.run()
    finally:
        telemetry.shutdown()
        metrics_server.shutdown()
        metrics_server.server_close()
        metrics_thread.join(timeout=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
