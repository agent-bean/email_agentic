import argparse
import asyncio
import json

import pytest
from pydantic import ValidationError

from email_agentic.platform.errors import ProviderFailure
from email_agentic.tools.harness import ToolContext
from evals.runner.replay import digest
from evals.runner.web_replay import WebTape, collect, run


CONTEXT = ToolContext('offline-eval', 'web', frozenset({'web:read'}), 'frozen-web-eval')
IDENTITY = {'company_name': 'Example', 'domain': 'example.com'}
CONFIG = {'read_pages': 2, 'duckduckgo_enabled': True}


async def provider(name, request):
    if name == 'web.scrape':
        if request['url'].endswith('bad'):
            raise ProviderFailure('firecrawl', category='http_429', transient=True, retry_after=5)
        return {'markdown': 'Controlled page', 'metadata': {}}
    if request['provider'] == 'duckduckgo':
        raise ProviderFailure('duckduckgo', category='rate_limited')
    assert 'private-marker' not in request['query']
    return {'results': [{'url': 'https://example.com/good', 'content': 'Excerpt'},
                        {'url': 'https://example.com/bad', 'content': 'Other excerpt'}]}


async def recorded():
    tape = WebTape(CONTEXT, delegate=provider)
    result = await collect({**IDENTITY, 'context': 'private-marker'}, CONFIG, tape)
    return result, {'calls': tape.calls, 'times': tape.times}


async def test_web_agent_replays_results_failures_and_exact_clock_deadline():
    expected, document = await recorded()
    actual = await collect(IDENTITY, CONFIG, WebTape(CONTEXT, document=document))
    assert actual == expected
    assert len([row for row in actual['data'] if row['status'] == 'failed']) == 6
    assert actual['data'][0]['results'][1]['page_read']['error_code'] == 'http_429'
    assert any('failure' in entry for entries in document['calls'].values() for entry in entries)
    assert len(document['times']) == 3


async def test_web_tape_matches_requests_not_completion_order_and_checks_context_schema():
    release = asyncio.Event()

    async def out_of_order(name, request):
        if request['query'] == 'first':
            await release.wait()
        else:
            release.set()
        return {'results': [], 'query': request['query']}

    tape = WebTape(CONTEXT, delegate=out_of_order)
    first = {'query': 'first'}
    second = {'query': 'second'}
    expected = await asyncio.gather(tape.execute('web.search', first, CONTEXT),
                                    tape.execute('web.search', second, CONTEXT))
    replay = WebTape(CONTEXT, document={'calls': tape.calls, 'times': []})
    assert await replay.execute('web.search', second, CONTEXT) == expected[1]
    assert await replay.execute('web.search', first, CONTEXT) == expected[0]
    replay.assert_consumed()
    with pytest.raises(ValueError, match='request drift'):
        await replay.execute('web.search', first, CONTEXT)
    with pytest.raises(ValueError, match='ToolContext'):
        await replay.execute('web.search', first, ToolContext('', 'web', frozenset({'web:read'})))
    with pytest.raises(ValidationError):
        await replay.execute('web.scrape', {'url': 'https://example.com', 'timeout_seconds': 16}, CONTEXT)


async def test_web_replay_rejects_missing_calls_and_input_tampering_offline(tmp_path, monkeypatch):
    import httpx

    result, recorded_document = await recorded()
    source = {'input': {**IDENTITY, 'source_email': 'private-marker'}}
    document = {'version': 1, 'scope': 'web_research_agent_tool_provider', 'identity': IDENTITY,
                'config': CONFIG, 'source_input_sha256': digest(source), **recorded_document,
                'branch_sha256': digest(result)}
    document['sha256'] = digest(document)
    source_path, cassette, output = (tmp_path / p for p in ('source.json', 'cassette.json', 'output.json'))
    source_path.write_text(json.dumps(source))
    cassette.write_text(json.dumps(document))
    args = argparse.Namespace(command='replay', input=source_path, cassette=cassette, output=output)

    def network_forbidden(*args, **kwargs):
        raise AssertionError('No network in replay')

    monkeypatch.setattr(httpx, 'AsyncClient', network_forbidden)
    await run(args)
    assert json.loads(output.read_text())['branch_sha256'] == digest(result)
    output.unlink()
    source['input']['source_email'] = 'changed'
    source_path.write_text(json.dumps(source))
    with pytest.raises(ValueError, match='input drift'):
        await run(args)
    document['calls'][next(iter(document['calls']))].append({'unexpected': True})
    with pytest.raises(ValueError, match='Unconsumed'):
        await collect(IDENTITY, CONFIG, WebTape(CONTEXT, document=document))


async def test_repeated_request_replays_failure_then_success_by_occurrence():
    attempts = 0

    async def changing_provider(name, request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ProviderFailure('tavily', category='http_429', transient=True, retry_after=3)
        return {'results': []}

    tape = WebTape(CONTEXT, delegate=changing_provider)
    request = {'query': 'same public query'}
    with pytest.raises(ProviderFailure):
        await tape.execute('web.search', request, CONTEXT)
    await tape.execute('web.search', request, CONTEXT)
    replay = WebTape(CONTEXT, document={'calls': tape.calls, 'times': []})
    with pytest.raises(ProviderFailure) as failure:
        await replay.execute('web.search', request, CONTEXT)
    assert failure.value.category == 'http_429' and failure.value.retry_after == 3
    assert await replay.execute('web.search', request, CONTEXT) == {'results': []}
    replay.assert_consumed()
