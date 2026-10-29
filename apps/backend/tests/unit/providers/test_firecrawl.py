import asyncio
import json

import httpx
import pytest

from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.integrations.firecrawl import Firecrawl
from email_agentic.platform.errors import ProviderFailure


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


async def test_duplicate_page_content_is_reused_even_when_page_reading_is_disabled():
    responses = [{"results": [
        {"url": "https://example.com/product", "content": "Matched identity excerpt"},
        {"url": "https://example.com/product#details", "raw_content": "Concrete deployment outcome"},
    ]}]
    await WebResearchAgent(None, read_pages=0).read_sources(responses, None)
    first, second = responses[0]["results"]
    assert first["raw_content"] == second["raw_content"] == "Concrete deployment outcome"
    assert first["content"] == "Matched identity excerpt"


async def test_failed_page_read_preserves_best_available_duplicate_excerpt():
    class UnavailablePages:
        async def execute(self, *args):
            raise ProviderFailure("firecrawl", category="http_403")

    responses = [{"results": [
        {"url": "https://example.com/product", "raw_content": "Short"},
        {"url": "https://example.com/product#details", "raw_content": "Specific documented deployment outcome"},
    ]}]
    await WebResearchAgent(UnavailablePages(), read_pages=1).read_sources(responses, None)
    for item in responses[0]["results"]:
        assert item["raw_content"] == "Specific documented deployment outcome"
        assert item["page_read"] == {"status": "failed", "error_code": "http_403"}


async def test_page_read_retains_article_publication_metadata_without_promoting_header_or_update_dates():
    class Pages:
        async def execute(self, *args):
            return {
                "markdown": "Website header: 29 October 2026\nArticle published: 4 July 2026\nDetails",
                "metadata": {
                    "article:published_time": "2026-07-04T09:00:00Z",
                    "datePublished": "2026-07-04",
                    "modifiedTime": "2026-10-29",
                    "date": "2026-10-29",
                    "title": "Article",
                },
            }

    responses = [{"results": [{"url": "https://example.com/article", "published_date": "2026-10-29"}]}]
    await WebResearchAgent(Pages(), read_pages=1).read_sources(responses, None)
    item = responses[0]["results"][0]
    assert item["page_read"]["publication_metadata"] == {
        "article:published_time": "2026-07-04T09:00:00Z", "datePublished": "2026-07-04",
    }
    # Search date remains separate so conflicting dates can be reviewed rather than silently overwritten.
    assert item["published_date"] == "2026-10-29"
    assert "4 July 2026" in item["raw_content"]


async def test_unscoped_scrape_does_not_replace_identified_search_article_with_boilerplate():
    class Pages:
        async def execute(self, *args):
            return {"markdown": "CURRENT WEBSITE CLOCK\n\n" + "Navigation. " * 1000}

    body = "# Regional partnership\n\nMarch 11, 2025\n\nDocumented outcome."
    responses = [{"results": [{
        "url": "https://example.com/article", "title": "Regional partnership",
        "raw_content": "WEBSITE CLOCK\n\n" + body,
    }]}]
    await WebResearchAgent(Pages(), read_pages=1).read_sources(responses, None)
    item = responses[0]["results"][0]
    assert item["raw_content"] == body
    assert item["article_context"]["status"] == "title_heading_matched"
    assert item["page_read"]["content_selection"] == "search_article_body"
    assert "CURRENT WEBSITE CLOCK" in item["unscoped_page_content"]
