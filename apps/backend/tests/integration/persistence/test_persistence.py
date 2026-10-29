import asyncio
import uuid

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from psycopg import AsyncConnection
from psycopg.rows import dict_row
import pytest

from email_agentic.bootstrap import build_container
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import Conflict
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.domains.reports.service import ReportEdit, Recipients
from email_agentic.agents.contracts import Draft
from email_agentic.runtime.jobs import Jobs, enqueue


async def test_queue_claim_is_exclusive_and_stale_claim_cannot_finish(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    async with db.transaction() as connection:
        for i in range(2):
            await enqueue(connection, owner, "test", None, f"test:{owner}:{i}")
    jobs = Jobs(db)
    a, b = await asyncio.gather(jobs.claim(["test"]), jobs.claim(["test"]))
    assert a["id"] != b["id"]
    await db.execute("UPDATE jobs SET claim_token=%s WHERE id=%s", (uuid.uuid4(), a["id"]))
    await jobs.finish(a)
    row = await db.one("SELECT status FROM jobs WHERE id=%s", (a["id"],))
    assert row["status"] == "running"
    await jobs.finish(b)


async def test_approval_version_and_outbox_are_atomic(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Test", domain="example.com"), str(uuid.uuid4())
        )
        run = await c.research.get(owner, run_id)
        await c.reports.initial(
            run, Draft(markdown="Source-backed draft", email_subject="Briefing", email_body="Summary"), {}
        )
        first = await c.reports.latest(owner, run_id)
        old = await db.one("SELECT id FROM approvals WHERE report_id=%s", (first["id"],))
        await c.reports.edit(
            owner,
            run_id,
            ReportEdit(
                version=1,
                markdown="Reviewed draft",
                email_subject="Briefing",
                email_body="Summary",
                recipients=Recipients(),
                save_kb=True,
            ),
        )
        with pytest.raises(Conflict):
            await c.approvals.decide(owner, old["id"], True)
        latest = await c.reports.latest(owner, run_id)
        approval = await db.one("SELECT id FROM approvals WHERE report_id=%s", (latest["id"],))
        await c.approvals.decide(owner, approval["id"], True)
        with pytest.raises(Conflict):
            await c.approvals.decide(owner, approval["id"], True)
        actions = await db.all("SELECT * FROM publication_actions WHERE approval_id=%s", (approval["id"],))
        assert len(actions) == 1 and actions[0]["kind"] == "kb"
        job = await db.one("SELECT * FROM jobs WHERE entity_id=%s AND kind='publish'", (actions[0]["id"],))
        assert job is not None
        package = await c.publication.package(owner, actions[0]["id"])
        assert package["correlation_id"].startswith("<")
        await c.publication.save_kb(package)
        assert await c.publication.package(owner, actions[0]["id"]) is None
        assert (
            await db.one(
                "SELECT count(*) AS total FROM knowledge WHERE report_id=%s AND status='approved'",
                (latest["id"],),
            )
        )["total"] == 1


async def test_interrupt_survives_a_new_checkpointer_connection(db):
    from typing import TypedDict

    class State(TypedDict, total=False):
        approved: bool

    def wait(state):
        return {"approved": interrupt({"kind": "approval"})}

    builder = StateGraph(State)
    builder.add_node("wait", wait)
    builder.add_edge(START, "wait")
    builder.add_edge("wait", END)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    async with await AsyncConnection.connect(
        db.pool.conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row
    ) as connection:
        graph = builder.compile(checkpointer=AsyncPostgresSaver(connection))
        first = await graph.ainvoke({}, config)
        assert "__interrupt__" in first
    async with await AsyncConnection.connect(
        db.pool.conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row
    ) as connection:
        graph = builder.compile(checkpointer=AsyncPostgresSaver(connection))
        final = await graph.ainvoke(Command(resume=True), config)
        assert final["approved"] is True


async def test_real_workflow_identity_pause_survives_restart(db):
    from email_agentic.workflows.research import make_graph

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Restart test", domain="example.com"), str(uuid.uuid4())
        )
        config = {"configurable": {"thread_id": str(run_id)}}
        async with await AsyncConnection.connect(
            db.pool.conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row
        ) as connection:
            first = await make_graph(c, AsyncPostgresSaver(connection)).ainvoke(
                {"run_id": str(run_id)}, config
            )
            assert "__interrupt__" in first
        async with await AsyncConnection.connect(
            db.pool.conninfo, autocommit=True, prepare_threshold=0, row_factory=dict_row
        ) as connection:
            state = await make_graph(c, AsyncPostgresSaver(connection)).aget_state(config)
            assert state.next == ("identity",)
            assert state.values["run_id"] == str(run_id)
        run = await c.research.get(owner, run_id)
        assert run["status"] == "awaiting_identity"
        await c.approvals.confirm_identity(owner, run_id, run["version"])
        assert (await c.research.get(owner, run_id))["identity_confirmed"] is True
        assert not await db.all(
            "SELECT * FROM publication_actions p JOIN approvals a ON a.id=p.approval_id JOIN reports r ON r.id=a.report_id WHERE r.run_id=%s",
            (run_id,),
        )


async def test_idempotent_create_is_safe_under_concurrency(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        key = str(uuid.uuid4())
        request = ResearchRequest(company_name="Concurrency test", domain="example.com")
        ids = await asyncio.gather(*(c.research.create(owner, request, key) for _ in range(4)))
        assert len(set(ids)) == 1
        assert (await db.one("SELECT count(*) AS total FROM research_runs WHERE owner=%s", (owner,)))[
            "total"
        ] == 1


async def test_stale_worker_cannot_write_domain_state(db):
    from email_agentic.platform.database import active_claim

    owner = f"{uuid.uuid4()}@example.invalid"
    async with db.transaction() as connection:
        await enqueue(connection, owner, "fence_test", None, f"fence:{owner}")
    job = await Jobs(db).claim(["fence_test"])
    await db.execute("UPDATE jobs SET claim_token=%s WHERE id=%s", (uuid.uuid4(), job["id"]))
    token = active_claim.set(job)
    try:
        with pytest.raises(RuntimeError, match="lease lost"):
            await db.execute("INSERT INTO schedule_ticks VALUES('stale-worker-test',%s)", (owner,))
    finally:
        active_claim.reset(token)
    assert (
        await db.one("SELECT * FROM schedule_ticks WHERE name='stale-worker-test' AND tick=%s", (owner,))
        is None
    )


async def test_interrupted_publication_never_blindly_resends(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner,
            ResearchRequest(company_name="Publication recovery", domain="example.com"),
            str(uuid.uuid4()),
        )
        run = await c.research.get(owner, run_id)
        await c.reports.initial(
            run,
            Draft(markdown="Controlled report", email_subject="Review", email_body="Controlled summary"),
            {},
        )
        await c.reports.edit(
            owner,
            run_id,
            ReportEdit(
                version=1,
                markdown="Controlled report",
                email_subject="Review",
                email_body="Controlled summary",
                recipients=Recipients(to=[owner]),
                send_email=True,
                save_kb=True,
            ),
        )
        report = await c.reports.latest(owner, run_id)
        approval = await db.one("SELECT id FROM approvals WHERE report_id=%s", (report["id"],))
        await c.approvals.decide(owner, approval["id"], True)
        actions = await db.all("SELECT * FROM publication_actions WHERE approval_id=%s", (approval["id"],))
        for action in actions:
            await c.publication.package(owner, action["id"])
            await db.execute(
                "UPDATE jobs SET status='failed' WHERE kind='publish' AND entity_id=%s", (action["id"],)
            )
        await c.jobs.recover()
        states = await db.all(
            "SELECT kind,status,id FROM publication_actions WHERE approval_id=%s", (approval["id"],)
        )
        assert {a["kind"]: a["status"] for a in states} == {"email": "unknown", "kb": "failed"}
        email = next(a for a in states if a["kind"] == "email")
        assert await c.publication.package(owner, email["id"]) is None
