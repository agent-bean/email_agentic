import asyncio
import threading

import pytest
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.integrations.duckduckgo import DuckDuckGo
from email_agentic.platform.errors import ProviderFailure


@pytest.mark.parametrize("news", [False, True])
async def test_adapter_uses_only_duckduckgo_and_normalizes_results(monkeypatch, news):
    class SearchClient:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 10}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, query, **kwargs):
            assert threading.current_thread() is not threading.main_thread()
            assert query == "Company example.com"
            assert kwargs == {"backend": "duckduckgo", "max_results": 8,
                              "region": "wt-wt", "timelimit": "m" if news else None}
            key = "url" if news else "href"
            return [
                {key: "https://example.com/page", "title": "Company", "body": "Excerpt",
                 "date": "2026-10-29T08:00:00Z"},
                {key: "https://example.com/page"},
                {key: "javascript:alert(1)"}, {key: "http://[invalid"}, {key: None},
            ]

        news = text

    monkeypatch.setattr("email_agentic.integrations.duckduckgo.DDGS", SearchClient)
    result = await DuckDuckGo().search("Company example.com", news)
    assert result["results"] == [{
        "url": "https://example.com/page", "title": "Company", "content": "Excerpt",
        "published_date": "2026-10-29T08:00:00Z" if news else None,
    }]


@pytest.mark.parametrize("exception, category", [
    (TimeoutException, "timeout"), (RatelimitException, "rate_limited"),
    (DDGSException, "search_failed"),
])
async def test_provider_errors_have_safe_stable_categories(monkeypatch, exception, category):
    def fail(*args, **kwargs):
        raise exception("provider detail must not enter the report")

    monkeypatch.setattr("email_agentic.integrations.duckduckgo.DDGS", fail)
    with pytest.raises(ProviderFailure) as error:
        await DuckDuckGo().search("Company")
    assert error.value.category == category
    assert "provider detail" not in str(error.value)


@pytest.mark.parametrize("category", ["rate_limited", "search_failed", "timeout"])
async def test_secondary_provider_bounds_retries_and_pending_queries_obey_cooldown(monkeypatch, category):
    calls = []
    provider = DuckDuckGo()

    async def blocked(query, news):
        calls.append(query)
        raise ProviderFailure("duckduckgo", transient=True, category=category)

    monkeypatch.setattr(provider, "_request", blocked)
    for query in ["Company identity", "Company products", "Company partners"]:
        with pytest.raises(ProviderFailure):
            await provider.search(query)
    attempts = 1 if category == "rate_limited" else 3
    assert calls == ["Company identity"] * attempts
    # The cooldown is finite: a later run can use the provider again.
    provider.cooldown_until = 0
    with pytest.raises(ProviderFailure):
        await provider.search("Company news")
    assert calls == ["Company identity"] * attempts + ["Company news"] * attempts


@pytest.mark.parametrize("failed_provider", ["tavily", "duckduckgo"])
async def test_two_providers_keep_partial_results_and_share_page_budget(failed_provider):
    class Tools:
        calls = []
        reads = []

        async def execute(self, name, request, context):
            if name == "web.scrape":
                self.reads.append(request["url"])
                return {"markdown": "Full content"}
            self.calls.append(request)
            assert "private" not in request["query"]
            if request["provider"] == failed_provider:
                raise ProviderFailure(failed_provider, category="rate_limited")
            return {"results": [{"url": "https://example.com/shared"}]}

    tools = Tools()
    results = await WebResearchAgent(tools, read_pages=2, duckduckgo_enabled=True).run(
        {"company_name": "Company", "domain": "example.com",
         "context": "private request", "source_email": "private customer email"}, None
    )
    assert len(tools.calls) == 12
    assert len(results) == 12
    assert len([r for r in results if r["status"] == "failed"]) == 6
    assert tools.reads == ["https://example.com/shared"]
    assert all(r["provider"] == failed_provider for r in results if r["status"] == "failed")


async def test_cancelled_search_finishes_thread_before_releasing_provider_slot(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def work(*args):
        started.set()
        assert release.wait(2)
        return {"results": []}

    provider = DuckDuckGo()
    monkeypatch.setattr(provider, "_search", work)
    task = asyncio.create_task(provider.search("Company"))
    while not started.is_set():
        await asyncio.sleep(0.001)
    task.cancel()
    await asyncio.sleep(0)
    assert provider.slots.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not provider.slots.locked()
