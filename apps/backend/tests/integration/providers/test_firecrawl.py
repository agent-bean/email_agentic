import json
import uuid

import pytest

from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure, ToolDenied
from email_agentic.tools.harness import ToolContext


async def test_scrape_tool_checks_role_schema_and_audits_failure_without_exposing_key(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        context = ToolContext(owner, "web", frozenset({"web:read"}))
        with pytest.raises(ToolDenied, match="scopes"):
            await c.tools.execute("web.scrape", {"url": "https://example.com"},
                                  ToolContext(owner, "calendar", frozenset({"web:read"})))
        with pytest.raises(ToolDenied, match="schema"):
            await c.tools.execute("web.scrape", {"url": "https://example.com", "timeout_seconds": 90}, context)
        with pytest.raises(ProviderFailure) as error:
            await c.tools.execute("web.scrape", {"url": "https://example.com"}, context)
        assert error.value.category == "not_configured"
        audit = await db.all("SELECT outcome FROM audit_events WHERE owner=%s ORDER BY id", (owner,))
        assert [row["outcome"] for row in audit] == ["denied:scopes", "denied:schema", "intent", "failed"]


async def test_new_run_records_page_limit_without_persisting_api_key(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo,
                        FIRECRAWL_API_KEY="test-only", FIRECRAWL_MAX_PAGES=4, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Company", domain="example.com"), str(uuid.uuid4())
        )
        run = await c.research.get(owner, run_id)
        assert run["config"]["firecrawl_max_pages"] == 4
        assert run["config"]["workflow_version"] == 8
        assert run["config"]["prompt_version"] == 12
        assert run["config"]["duckduckgo_enabled"] is True
        assert "test-only" not in json.dumps(run["config"])
