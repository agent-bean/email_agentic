import json
import uuid

import pytest

from email_agentic.agents.contracts import Draft
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import Conflict
from email_agentic.workflows.research import make_graph


@pytest.mark.parametrize("corrects", [True, False])
@pytest.mark.parametrize("bare_url", [True, False])
async def test_research_corrects_unsupported_email_links_once_or_stops_without_report(db, corrects, bare_url):
    class ScriptedLLM:
        calls = 0

        async def structured(self, run_id, schema, system, payload):
            self.calls += 1
            data = json.loads(payload)
            # A URL in private context is not automatically evidence, even on the company's domain.
            assert data["allowed_urls"] == ["https://example.com/source"]
            assert "https://example.com/unsupported" in data["source_email"]
            if self.calls == 2:
                assert data["citation_correction"]["allowed_urls"] == ["https://example.com/source"]
                assert "unsupported" in data["citation_correction"]["previous_draft"]["email_body"]
            return Draft(
                markdown="Fact [source](https://example.com/source)", email_subject="Briefing",
                email_body="Fact [source](https://example.com/source)"
                if corrects and self.calls == 2 else (
                    "Fact https://example.com/unsupported." if bare_url
                    else "Fact [unsupported](https://example.com/unsupported)"
                ),
            )

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Company", domain="example.com",
                                   source_email="Website: https://example.com/unsupported\nCustomer request"),
            str(uuid.uuid4())
        )
        await db.execute("UPDATE research_runs SET identity_confirmed=true WHERE id=%s", (run_id,))
        for branch in ("company", "memory", "calendar", "web"):
            await c.jobs.save_branch(run_id, branch, {"status": "succeeded", "data": []})
        await db.execute(
            "INSERT INTO evidence(id,run_id,url,title,content) VALUES(%s,%s,%s,%s,%s)",
            (uuid.uuid4(), run_id, "https://example.com/source", "Protocol source", "Fact"),
        )
        c.llm = ScriptedLLM()
        graph = make_graph(c, None)
        if corrects:
            await graph.ainvoke({"run_id": str(run_id)})
            report = await c.reports.latest(owner, run_id)
            assert report["quality"]["citation_correction_attempted"] is True
            assert report["quality"]["cited_sources"] == 1
            assert report["send_email"] is False and report["save_kb"] is False
        else:
            with pytest.raises(Conflict, match="unsupported source URL"):
                await graph.ainvoke({"run_id": str(run_id)})
            assert await db.one("SELECT id FROM reports WHERE run_id=%s", (run_id,)) is None
        assert c.llm.calls == 2


@pytest.mark.parametrize("saved_evidence", [0, 1])
async def test_retry_restores_cached_web_evidence_without_repeating_searches(db, saved_evidence):
    class ReportLLM:
        async def structured(self, run_id, schema, system, payload):
            assert set(json.loads(payload)["allowed_urls"]) == {
                "https://example.com/first", "https://example.com/second",
            }
            return Draft(markdown="Fact [source](https://example.com/second)",
                         email_subject="Discussion", email_body="Thank you.")

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Company", domain="example.com"), str(uuid.uuid4()),
        )
        await db.execute("UPDATE research_runs SET identity_confirmed=true WHERE id=%s", (run_id,))
        for branch in ("company", "memory", "calendar"):
            await c.jobs.save_branch(run_id, branch, {"status": "succeeded", "data": []})
        results = [{"url": f"https://example.com/{name}", "title": name, "content": "Fact"}
                   for name in ("first", "second")]
        await c.jobs.save_branch(run_id, "web", {
            "status": "succeeded", "data": [{"research_area": "identity", "results": results}],
        })
        for item in results[:saved_evidence]:
            await db.execute("INSERT INTO evidence(id,run_id,url,title,content) VALUES(%s,%s,%s,%s,%s)",
                             (uuid.uuid4(), run_id, item["url"], item["title"], item["content"]))

        async def unexpected_provider_call(*args, **kwargs):
            pytest.fail("Successful cached branches must not repeat provider calls")

        c.tools.execute = unexpected_provider_call
        c.llm = ReportLLM()
        await make_graph(c, None).ainvoke({"run_id": str(run_id)})

        assert len(await db.all("SELECT id FROM evidence WHERE run_id=%s", (run_id,))) == 2
        assert (await c.research.get(owner, run_id))["status"] == "draft_ready"


async def test_retry_restores_readiness_without_replacing_committed_report(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Company", domain="example.com"), str(uuid.uuid4()),
        )
        await db.execute("UPDATE research_runs SET identity_confirmed=true WHERE id=%s", (run_id,))
        for branch in ("company", "memory", "calendar", "web"):
            await c.jobs.save_branch(run_id, branch, {"status": "succeeded", "data": []})
        run = await c.research.get(owner, run_id)
        report_id = await c.reports.initial(
            run, Draft(markdown="Saved report", email_subject="Discussion", email_body="Saved reply"),
            {"markdown_ready_at": "2026-10-29T00:00:00+00:00"},
        )
        before = await c.reports.latest(owner, run_id)

        result = await make_graph(c, None).ainvoke({"run_id": str(run_id)})

        assert "__interrupt__" in result
        assert (await c.research.get(owner, run_id))["status"] == "draft_ready"
        assert await c.reports.latest(owner, run_id) == before
        approvals = await db.all("SELECT status FROM approvals WHERE report_id=%s", (report_id,))
        assert approvals == [{"status": "pending"}]
        assert not await db.all("SELECT id FROM publication_actions WHERE approval_id IN "
                                "(SELECT id FROM approvals WHERE report_id=%s)", (report_id,))
