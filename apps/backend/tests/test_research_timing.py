import json
import uuid

import pytest

from email_agentic.agents.contracts import Draft
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.config import Settings
from email_agentic.workflows.research import make_graph


@pytest.mark.parametrize("previous", [0, 3])
async def test_processing_time_excludes_time_waiting_for_identity_and_queue(db, previous):
    class ReportLLM:
        async def structured(self, run_id, schema, system, payload):
            assert json.loads(payload)["allowed_urls"] == ["https://example.com/source"]
            return Draft(markdown="Fact [source](https://example.com/source)",
                         email_subject="Discussion", email_body="Thank you for your request.")

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Company", domain="example.com"), str(uuid.uuid4())
        )
        await db.execute("""UPDATE research_runs SET identity_confirmed=true,
            created_at=now()-interval '1 day',elapsed_seconds=%s WHERE id=%s""", (previous, run_id))
        for branch in ("company", "memory", "calendar", "web"):
            await c.jobs.save_branch(run_id, branch, {"status": "succeeded", "data": []})
        await db.execute("INSERT INTO evidence(id,run_id,url,title,content) VALUES(%s,%s,%s,%s,%s)",
                         (uuid.uuid4(), run_id, "https://example.com/source", "Source", "Fact"))
        c.llm = ReportLLM()
        await make_graph(c, None).ainvoke({"run_id": str(run_id)})
        report = await c.reports.latest(owner, run_id)
        run = await c.research.get(owner, run_id)
        assert previous <= report["quality"]["elapsed_seconds"] < previous + 10
        assert report["quality"]["time_target_met"] is True
        assert report["quality"]["timing_basis"] == "active_processing"
        assert report["quality"]["elapsed_seconds"] <= run["elapsed_seconds"] < previous + 10
        assert report["quality"]["prd_elapsed_seconds"] is None
        assert report["quality"]["prd_time_target_met"] is None


def test_prd_timing_includes_queues_and_excludes_identity_wait():
    from datetime import datetime, UTC
    from email_agentic.workflows.research import prd_timing

    run = {"identity_confirmed": True, "config": {"target_seconds": 42, "timing": {
        "version": 1,
        "received_at": "2026-10-29T08:00:00+00:00",
        "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
        "identity_confirmed_at": "2026-10-30T08:00:08+00:00",
    }}}
    # Eight seconds initial queue, ten after confirmation, thirty processing.
    quality = prd_timing(run, datetime(2026, 10, 30, 8, 0, 48, tzinfo=UTC))
    assert quality["prd_elapsed_seconds"] == 48
    assert quality["identity_wait_seconds"] == 86400
    assert quality["prd_time_target_met"] is False


@pytest.mark.parametrize("timing", [
    {}, {"version": 1},
    {"version": 1, "received_at": "2026-10-29T08:00:00+00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00"},
    {"version": 1, "received_at": "2026-10-29T08:00:00+00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
     "identity_confirmed_at": "2026-10-29T08:00:07+00:00"},
    {"version": 1, "received_at": "2026-10-29T08:00:00",
     "identity_wait_started_at": "2026-10-29T08:00:08+00:00",
     "identity_confirmed_at": "2026-10-29T08:00:09+00:00"},
])
def test_prd_timing_does_not_claim_legacy_or_incomplete_wait(timing):
    from datetime import datetime, UTC
    from email_agentic.workflows.research import prd_timing

    result = prd_timing({"identity_confirmed": True,
                         "config": {"target_seconds": 42, "timing": timing}}, datetime.now(UTC))
    assert result["prd_elapsed_seconds"] is None
    assert result["prd_time_target_met"] is None


async def test_identity_timing_is_durable_and_duplicate_wait_does_not_reset(db):
    from datetime import datetime
    from email_agentic.workflows.research import prd_timing

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(owner, ResearchRequest(company_name="Company", domain="example.com"),
                                         str(uuid.uuid4()))
        await c.research.status(run_id, "awaiting_identity")
        waiting = (await c.research.get(owner, run_id))["config"]["timing"]["identity_wait_started_at"]
        await c.research.status(run_id, "awaiting_identity")
        assert (await c.research.get(owner, run_id))["config"]["timing"]["identity_wait_started_at"] == waiting
        await c.approvals.confirm_identity(owner, run_id, 1)
        run = await c.research.get(owner, run_id)
        timing = run["config"]["timing"]
        assert datetime.fromisoformat(timing["received_at"]) <= datetime.fromisoformat(waiting)
        result = prd_timing(run, datetime.fromisoformat(timing["identity_confirmed_at"]))
        assert result["prd_elapsed_seconds"] >= 0
        assert result["prd_time_target_met"] is True


async def test_committed_report_records_prd_queue_time_separately_from_active_time(db):
    class ReportLLM:
        async def structured(self, run_id, schema, system, payload):
            return Draft(markdown="Fact [source](https://example.com/source)",
                         email_subject="Discussion", email_body="Thank you for your request.")

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(owner, ResearchRequest(company_name="Company", domain="example.com"),
                                         str(uuid.uuid4()))
        await c.research.status(run_id, "awaiting_identity")
        await c.approvals.confirm_identity(owner, run_id, 1)
        # Reproduce an elapsed day of human wait and 50 seconds of queue before processing.
        await db.execute("""UPDATE research_runs SET config=jsonb_set(config,'{timing}',
            jsonb_build_object('version',1,'received_at',clock_timestamp()-interval '1 day 50 seconds',
            'identity_wait_started_at',clock_timestamp()-interval '1 day 30 seconds',
            'identity_confirmed_at',clock_timestamp()-interval '30 seconds')) WHERE id=%s""", (run_id,))
        for branch in ("company", "memory", "calendar", "web"):
            await c.jobs.save_branch(run_id, branch, {"status": "succeeded", "data": []})
        await db.execute("INSERT INTO evidence(id,run_id,url,title,content) VALUES(%s,%s,%s,%s,%s)",
                         (uuid.uuid4(), run_id, "https://example.com/source", "Source", "Fact"))
        c.llm = ReportLLM()
        await make_graph(c, None).ainvoke({"run_id": str(run_id)})
        quality = (await c.reports.latest(owner, run_id))["quality"]
        assert quality["elapsed_seconds"] < 10
        assert 50 <= quality["prd_elapsed_seconds"] < 60
        assert quality["time_target_met"] is True
        assert quality["prd_time_target_met"] is False
        assert quality["markdown_ready_at"] is not None
