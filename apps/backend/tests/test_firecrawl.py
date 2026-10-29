import asyncio
import json
import uuid

import httpx
import pytest

from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.integrations.firecrawl import Firecrawl
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure, ToolDenied
from email_agentic.tools.harness import ToolContext


async def test_scrape_protocol_requests_main_content_and_returns_markdown():
    def respond(request):
        assert str(request.url) == "https://api.firecrawl.dev/v2/scrape"
        assert request.headers["authorization"] == "Bearer test-only"
        body = json.loads(request.content)
        assert body["url"] == "https://example.com/product"
        assert body["formats"] == ["markdown"] and body["onlyMainContent"] is True
        assert body["timeout"] < 15000
        assert body["skipTlsVerification"] is False
        assert body["parsers"] == []
        return httpx.Response(200, json={
            "success": True, "data": {"markdown": "# Product\nDetailed content", "metadata": {"statusCode": 200}}
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await Firecrawl(client, "test-only").scrape("https://example.com/product")
    assert result["markdown"].endswith("Detailed content")


@pytest.mark.parametrize("status, body, category", [
    (429, {}, "http_429"),
    (200, {"success": False}, "invalid_receipt"),
    (200, {"success": True, "data": {}}, "missing_content"),
    (200, {"success": True, "data": {"markdown": " "}}, "empty_content"),
    (200, {"success": True, "data": {"markdown": "blocked", "metadata": {"statusCode": 403}}}, "page_error"),
    (200, {"success": True, "data": {"markdown": "page", "metadata": {"statusCode": None}}}, "invalid_receipt"),
])
async def test_scrape_failure_receipts_are_not_accepted_as_source_content(status, body, category):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))) as client:
        with pytest.raises(ProviderFailure) as error:
            await Firecrawl(client, "test-only").scrape("https://example.com/page")
    assert error.value.category == category


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1", "http://127.1/", "http://[::1]/",
    "http://localhost/", "http://localhost./", "http://host.local./",
    "https://user:pass@example.com/", "http://[invalid",
])
async def test_private_or_invalid_targets_are_rejected_before_provider_request(url):
    def unexpected(request):
        raise AssertionError("Invalid target reached provider")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ProviderFailure) as error:
            await Firecrawl(client, "test-only").scrape(url)
    assert error.value.category == "invalid_url"


async def test_page_reading_is_topic_balanced_deduplicated_bounded_and_retains_fallback():
    class PageTools:
        urls = []
        active = 0
        peak = 0

        async def execute(self, name, request, context):
            assert name == "web.scrape"
            assert set(request) == {"url", "timeout_seconds"}
            self.urls.append(request["url"])
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.01)
                if "bad" in request["url"]:
                    raise ProviderFailure("firecrawl", category="http_403")
                return {"markdown": "Full product details"}
            finally:
                self.active -= 1

    tools = PageTools()
    results = [
        {"results": [
            {"url": "https://example.com/identity", "content": "excerpt"},
            {"url": "https://example.com/extra"},
        ]},
        {"results": [{"url": "https://example.com/bad", "raw_content": "Tavily fallback"}]},
        {"results": [
            {"url": "https://example.com/product"},
            {"url": "https://example.com/identity#section"},
        ]},
    ]
    await WebResearchAgent(tools, read_pages=3).read_sources(results, None)
    assert tools.peak == 2
    assert len(tools.urls) == 3 and "https://example.com/extra" not in tools.urls
    assert results[0]["results"][0]["raw_content"] == "Full product details"
    assert results[0]["results"][0]["content"] == "excerpt"
    assert results[0]["results"][1]["page_read"]["status"] == "not_selected"
    assert results[1]["results"][0]["raw_content"] == "Tavily fallback"
    assert results[1]["results"][0]["page_read"]["error_code"] == "http_403"
    assert results[2]["results"][1]["page_read"]["status"] == "succeeded"


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
        assert run["config"]["workflow_version"] == 5
        assert run["config"]["prompt_version"] == 10
        assert run["config"]["duckduckgo_enabled"] is True
        assert "test-only" not in json.dumps(run["config"])


async def test_page_reads_prioritize_missing_content_and_preserve_existing_search_excerpts():
    class Pages:
        urls = []

        async def execute(self, name, request, context):
            self.urls.append(request["url"])
            return {"markdown": "Additional page content"}

    tools = Pages()
    long_content = "Useful source details " * 400
    responses = [{"results": [
        {"url": "https://example.com/rich", "content": "First short duplicate"},
        {"url": "https://example.com/missing", "content": "Search excerpt"},
        {"url": "https://example.com/rich#section", "raw_content": long_content},
    ]}]
    await WebResearchAgent(tools, read_pages=1).read_sources(responses, None)
    assert tools.urls == ["https://example.com/missing"]
    rich, missing, duplicate = responses[0]["results"]
    assert rich["raw_content"] == long_content
    assert rich["page_read"] == duplicate["page_read"] == {
        "status": "not_selected", "reason": "search_content_available",
    }
    assert missing["raw_content"] == "Additional page content"
    assert missing["content"] == "Search excerpt"
