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
