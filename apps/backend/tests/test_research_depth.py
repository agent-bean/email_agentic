import asyncio
import json
from datetime import UTC, datetime

import pytest

from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.platform.errors import ProviderFailure
from email_agentic.workflows.research import publication_date


async def test_search_keeps_partial_results_limits_concurrency_and_excludes_private_context():
    class SearchTools:
        active = 0
        peak = 0

        async def execute(self, name, request, context):
            assert name == "web.search"
            assert "private-contact" not in request["query"]
            self.active += 1
            self.peak = max(self.peak, self.active)
            try:
                await asyncio.sleep(0.01)
                if request["news"]:
                    raise ProviderFailure("tavily", category="rate_limit")
                return {"results": [{"url": "https://example.com/product"}]}
            finally:
                self.active -= 1

    tools = SearchTools()
    result = await WebResearchAgent(tools).run(
        {"company_name": "Company", "domain": "example.com", "context": "private-contact"}, None
    )
    assert tools.peak == 3
    assert len([item for item in result if item["results"]]) == 5
    assert result[-1] == {
        "research_area": "news", "provider": "tavily", "status": "failed",
        "error_code": "rate_limit", "results": []
    }


async def test_all_search_failures_stop_the_web_branch():
    class UnavailableTools:
        async def execute(self, *args):
            raise ProviderFailure("tavily", category="network_or_timeout")

    with pytest.raises(ProviderFailure, match="web_search"):
        await WebResearchAgent(UnavailableTools()).run(
            {"company_name": "Company", "domain": "example.com"}, None
        )


async def test_report_preserves_topic_gaps_and_omits_duplicate_provider_pages():
    class CapturingLLM:
        async def structured(self, run_id, schema, system, payload):
            return json.loads(payload)

    result = await ReportGenerationAgent(CapturingLLM()).run(
        {"id": "run", "company_name": "Company", "domain": "example.com", "context": "meeting"},
        [{"url": "https://example.com/product", "content": "query excerpt"}],
        [
            {"branch": "web", "result": {"status": "succeeded", "data": [
                {"research_area": "products", "status": "succeeded", "results": [
                    {"url": "https://example.com/product", "raw_content": "duplicate page"}
                ]},
                {"research_area": "news", "status": "failed", "error_code": "rate_limit"},
            ]}},
            {"branch": "calendar", "result": {"status": "failed"}},
        ],
    )
    assert result["research_coverage"][1]["error_code"] == "rate_limit"
    assert result["research_coverage"][0]["urls"] == ["https://example.com/product"]
    assert "duplicate page" not in json.dumps(result)
    assert result["internal_context"][0]["status"] == "failed"


@pytest.mark.parametrize("value", ["2025-03-11T17:00:00Z", "Tue, 11 Mar 2025 17:00:00 GMT"])
def test_publication_date_accepts_provider_formats(value):
    assert publication_date(value) == datetime(2025, 3, 11, 17, tzinfo=UTC)


@pytest.mark.parametrize("value", [None, "", "not a date"])
def test_unknown_publication_date_stays_unknown(value):
    assert publication_date(value) is None


async def test_secondary_provider_queue_does_not_occupy_active_search_slots():
    secondary_started = asyncio.Event()
    release_secondary = asyncio.Event()
    primary_started = asyncio.Event()
    primary_count = 0
    secondary_slots = asyncio.Semaphore(1)

    class Tools:
        async def execute(self, name, request, context):
            nonlocal primary_count
            if request["provider"] == "duckduckgo":
                async with secondary_slots:
                    secondary_started.set()
                    await release_secondary.wait()
            else:
                primary_count += 1
                if primary_count == 6:
                    primary_started.set()
                await asyncio.sleep(0)
            return {"results": []}

    task = asyncio.create_task(WebResearchAgent(Tools(), duckduckgo_enabled=True).run(
        {"company_name": "Company", "domain": "example.com"}, None
    ))
    try:
        await asyncio.wait_for(secondary_started.wait(), 1)
        await asyncio.wait_for(primary_started.wait(), 1)
    finally:
        release_secondary.set()
        await task


async def test_report_retains_persisted_evidence_tail_and_marks_provider_dates_unverified():
    class CapturingLLM:
        async def structured(self, run_id, schema, system, payload):
            return {"system": system, **json.loads(payload)}

    content = "Evidence body. " * 450 + "Specific documented outcome in the final paragraph."
    result = await ReportGenerationAgent(CapturingLLM()).run(
        {"id": "run", "company_name": "Company", "domain": "example.com", "context": "meeting"},
        [{"url": "https://example.com/article", "content": content, "published_at": "2026-10-28"}],
        [],
    )
    assert result["evidence"][0]["content"] == content
    assert result["evidence"][0]["publication_date_status"] == "unverified_provider_date"
    assert "website header" in result["system"]
    assert "purpose and documented outcomes" in result["system"]


async def test_all_search_areas_use_confirmed_entity_without_restricting_counterpart_sources():
    class Searches:
        requests = []

        async def execute(self, name, request, context):
            assert name == "web.search"
            self.requests.append(request)
            return {"results": []}

    tools = Searches()
    result = await WebResearchAgent(tools, duckduckgo_enabled=True).run(
        {"company_name": "Example Regional Subsidiary", "domain": "example.com"}, None
    )
    assert {row["research_area"] for row in result} == {
        "identity", "products", "deployments", "partners", "adoption", "news",
    }
    assert len(tools.requests) == 12
    for request in tools.requests:
        assert "Example Regional Subsidiary" in request["query"]
        assert "example.com" in request["query"]
        assert "site:" not in request["query"]
    assert sum(request["news"] for request in tools.requests) == 2


def test_article_boundary_excludes_clock_before_exact_heading_and_preserves_body():
    from email_agentic.agents.web_research import article_body

    prefix = "Tuesday, October 27 2026\n\n# [Publisher](/)\n\n[Sections](/sections)\n\n"
    body = "# [Regional **technology** partnership](/article)\n\nJuly 02, 2026 - 14:58\n\nSpecific outcome.\n"
    extracted, context = article_body(prefix + body, "Regional technology partnership")
    assert extracted == body
    assert context == {
        "status": "title_heading_matched", "heading": "Regional technology partnership",
        "opening": body, "excluded_prefix": prefix,
    }


def test_article_boundary_unknown_keeps_all_content_without_guessing_dates():
    from email_agentic.agents.web_research import article_body

    content = "October 27, 2026\n\n# Different article\n\nSpecific outcome."
    assert article_body(content, "Requested article") == (content, {"status": "unknown"})
    assert article_body(content, "") == (content, {"status": "unknown"})


def test_article_boundary_scan_is_bounded_without_truncating_source():
    from email_agentic.agents.web_research import article_body

    body = "# Regional partnership\n\n" + "Documented outcome.\n" * 10000
    extracted, context = article_body("Website navigation\n\n" + body, "Regional partnership")
    assert extracted == body
    assert context["excluded_prefix"] + extracted == "Website navigation\n\n" + body
    late = "Navigation.\n" * 6000 + body
    assert article_body(late, "Regional partnership") == (late, {"status": "unknown"})


async def test_article_parsing_can_be_cancelled_without_blocking_event_loop(monkeypatch):
    import threading
    from email_agentic.agents import web_research

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def blocked_parser(content, title):
        started.set()
        try:
            assert release.wait(2)
            return content, {"status": "unknown"}
        finally:
            finished.set()

    monkeypatch.setattr(web_research, "article_body", blocked_parser)
    task = asyncio.create_task(WebResearchAgent(None).read_sources(
        [{"results": [{"url": "https://example.com/article", "raw_content": "Article"}]}], None
    ))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 0.5)
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)


async def test_duplicate_source_content_is_parsed_once_per_collection(monkeypatch):
    from email_agentic.agents import web_research

    original = web_research.article_body
    calls = []

    def counted(content, title):
        calls.append((content, title))
        return original(content, title)

    monkeypatch.setattr(web_research, "article_body", counted)
    responses = [{"results": [{
        "url": "https://example.com/article", "title": "Article", "raw_content": "# Article\n\nOutcome"
    } for _ in range(12)]}]
    await WebResearchAgent(None).read_sources(responses, None)
    assert len(calls) == 1
    assert all(item["article_context"]["status"] == "title_heading_matched"
               for item in responses[0]["results"])


async def test_matched_article_wins_over_longer_duplicate_boilerplate_and_prefix_stays_out_of_report():
    class CapturingLLM:
        async def structured(self, run_id, schema, system, payload):
            return json.loads(payload)

    body = "# Regional partnership\n\nJuly 02, 2026\n\n" + "Documented outcome. " * 400
    prefix = "October 27, 2026 WEBSITE CLOCK\n\n# Publisher\n\n"
    responses = [{"results": [
        {"url": "https://example.com/article", "title": "Regional partnership", "raw_content": prefix + body},
        {"url": "https://example.com/article#section", "title": "Different listing title",
         "raw_content": "Unmatched boilerplate. " * 800},
    ]}]
    await WebResearchAgent(None, read_pages=0).read_sources(responses, None)
    first, second = responses[0]["results"]
    assert first["raw_content"] == second["raw_content"] == body
    assert first["article_context"]["excluded_prefix"] == prefix
    result = await ReportGenerationAgent(CapturingLLM()).run(
        {"id": "run", "company_name": "Company", "domain": "example.com", "context": "meeting"},
        [{"url": first["url"], "content": "Search excerpt\n\n" + first["raw_content"][:8000]}],
        [{"branch": "web", "result": {"status": "succeeded", "data": responses}}],
    )
    assert "WEBSITE CLOCK" not in json.dumps(result)
    assert result["research_coverage"][0]["article_contexts"][0]["status"] == "title_heading_matched"
    assert "July 02, 2026" in result["evidence"][0]["content"]


def test_article_title_heading_takes_priority_over_same_named_navigation_subheading():
    from email_agentic.agents.web_research import article_body

    prefix = "## [Regional partnership](/section)\n\nWEBSITE CLOCK\n\n"
    body = "# Regional partnership\n\nMarch 11, 2025\n\nDocumented outcome."
    assert article_body(prefix + body, "Regional partnership")[0] == body
    ambiguous = "## Regional partnership\n\nOne\n\n## Regional partnership\n\nTwo"
    assert article_body(ambiguous, "Regional partnership") == (ambiguous, {"status": "unknown"})
