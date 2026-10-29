import asyncio
import logging
import signal
from contextlib import suppress
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
from email_agentic.platform.errors import ProviderFailure
from email_agentic.platform.telemetry import DURATION, JOBS, configure, tracer
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

    async def heartbeat(self, job, task):
        while True:
            await asyncio.sleep(15)
            if not await self.c.jobs.heartbeat(job):
                task.cancel()
                return

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
                async with asyncio.timeout(run["config"]["timeout_seconds"]):
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

    async def process(self, job):
        token = active_claim.set(job)
        task = asyncio.create_task(self.handle(job))
        active_claim.reset(token)
        heartbeat = asyncio.create_task(self.heartbeat(job, task))
        with DURATION.labels(job["kind"]).time(), tracer().start_as_current_span("job." + job["kind"]):
            try:
                await task
                await self.c.jobs.finish(job)
                JOBS.labels(job["kind"], "succeeded").inc()
            except asyncio.CancelledError:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise
            except Exception as exc:
                retry = (
                    isinstance(exc, ProviderFailure)
                    and exc.transient
                    and not exc.ambiguous
                    and job["attempt"] < 3
                )
                error = (
                    f"{exc.provider}:{exc.category}"
                    if isinstance(exc, ProviderFailure)
                    else type(exc).__name__
                )
                await self.c.jobs.finish(job, "failed", error, retry)
                if job["kind"] == "email_intake":
                    await self.c.db.execute(
                        "UPDATE email_triage SET status=%s,error_code=%s,updated_at=now() WHERE input_id=%s AND owner=%s",
                        ("queued" if retry else "failed", error, job["entity_id"], job["owner"]),
                    )
                if job["kind"] == "calendar_intake":
                    await self.c.db.execute("UPDATE calendar_triage SET status=%s,error_code=%s,updated_at=now() WHERE id=%s AND owner=%s",
                                       ("queued" if retry else "failed", error, job["entity_id"], job["owner"]))
                if job["kind"] in {"research", "resume"} and not retry:
                    await self.c.research.status(job["entity_id"], "failed", error)
                JOBS.labels(job["kind"], "failed").inc()
                logger.warning("Job failed: kind=%s category=%s", job["kind"], type(exc).__name__)
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

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
