import httpx
import pytest

from email_agentic.integrations.firecrawl import Firecrawl
from email_agentic.integrations.http import bounded_retry
from email_agentic.platform.errors import ProviderFailure
from email_agentic.integrations.tavily import Tavily
from email_agentic.runtime.budget import processing_budget


async def test_firecrawl_retries_transient_errors_then_returns_real_receipt():
    calls = []
    def respond(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={'Retry-After': '0'}, json={})
        return httpx.Response(200, json={'success': True, 'data': {'markdown': 'Source text'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (await Firecrawl(client, 'test-only').scrape('https://example.com'))['markdown'] == 'Source text'
    assert len(calls) == 3


async def test_long_retry_after_stops_page_reads_without_hammering_provider():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(429, headers={'Retry-After': '60'}, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = Firecrawl(client, 'test-only')
        for _ in range(2):
            with pytest.raises(ProviderFailure):
                await adapter.scrape('https://example.com', timeout_seconds=1)
    assert len(calls) == 1


async def test_permanent_failure_is_not_retried_and_budget_timeout_is_normalized():
    calls = []
    async def denied(remaining):
        calls.append(remaining)
        raise ProviderFailure('test', category='permissions')
    with pytest.raises(ProviderFailure, match='test'):
        await bounded_retry(denied, 1, provider='test')
    assert len(calls) == 1
    import asyncio
    async def slow(remaining):
        await asyncio.sleep(1)
    with pytest.raises(ProviderFailure) as exc:
        await bounded_retry(slow, 0.01, provider='test')
    assert exc.value.category == 'network_or_timeout'


async def test_tavily_retries_only_transient_failures_with_a_total_limit():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) < 3 else 200, headers={'Retry-After': '0'}, json={'results': []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await Tavily(client, 'test-only').search('Company example.invalid') == {'results': []}
    assert len(calls) == 3


async def test_retry_reservations_survive_operation_reentry_without_another_provider_call():
    reservations, calls = {}, []

    async def reserve(key):
        count = reservations.get(key, 0)
        if count >= 3:
            return False
        reservations[key] = count + 1
        return True

    async def failure(remaining):
        calls.append(remaining)
        raise ProviderFailure('test', transient=True, retry_after=0)

    for _ in range(2):
        with processing_budget(5, reserve):
            with pytest.raises(ProviderFailure):
                await bounded_retry(failure, 5, provider='test', operation_key='stable query')
    assert len(calls) == 3
    assert len(reservations) == 1
    assert 'stable query' not in next(iter(reservations))


async def test_shared_deadline_prevents_later_operation_from_starting():
    calls = []

    async def operation(remaining):
        calls.append(remaining)

    with processing_budget(0):
        with pytest.raises(ProviderFailure) as error:
            await bounded_retry(operation, 45, provider='test')
    assert error.value.category == 'network_or_timeout'
    assert calls == []
