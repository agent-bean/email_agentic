import json
import uuid

import pytest

from email_agentic.agents.contracts import Draft
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import Conflict
from email_agentic.workflows.research import canonical_url, cited_urls, make_graph


@pytest.mark.parametrize("corrects", [True, False])
@pytest.mark.parametrize("bare_url", [True, False])
async def test_research_corrects_unsupported_email_links_once_or_stops_without_report(db, corrects, bare_url):
    class ScriptedLLM:
        calls = 0

        async def structured(self, run_id, schema, system, payload):
            self.calls += 1
            data = json.loads(payload)
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
            owner, ResearchRequest(company_name="Company", domain="example.com"), str(uuid.uuid4())
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


def test_malformed_source_url_is_rejected_without_crashing_validation():
    assert canonical_url("http://[invalid") is None


@pytest.mark.parametrize("text", [
    "[Source](https://example.com/entry_(detail))",
    "See https://example.com/entry_(detail).",
    "See <https://example.com/entry_(detail)>.",
])
def test_source_validation_covers_bare_and_markdown_links_with_balanced_url_parentheses(text):
    assert cited_urls(text) == {"https://example.com/entry_(detail)"}
