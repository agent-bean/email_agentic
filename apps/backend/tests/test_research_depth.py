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
    assert len([item for item in result if item["results"]]) == 4
    assert result[-1] == {
        "research_area": "news", "status": "failed", "error_code": "rate_limit", "results": []
    }


async def test_all_search_failures_stop_the_web_branch():
    class UnavailableTools:
        async def execute(self, *args):
            raise ProviderFailure("tavily", category="network_or_timeout")

    with pytest.raises(ProviderFailure, match="tavily"):
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
