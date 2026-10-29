"""Eval-only real web-agent record/replay; no DB, golden or network fallback."""
import argparse
import asyncio
import copy
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.bootstrap import Scrape, Search
from email_agentic.platform.errors import ProviderFailure, ToolDenied
from email_agentic.tools.harness import ToolContext

from evals.runner.replay import digest, write_private


class WebTape:
    def __init__(self, context, delegate=None, document=None):
        self.context, self.delegate = context, delegate
        self.document = document
        self.calls = {}
        self.counts = {}
        self.times = []
        self.time_position = 0

    def time(self):
        if self.delegate:
            value = asyncio.get_running_loop().time()
            self.times.append(value)
            return value
        if self.time_position >= len(self.document['times']):
            raise ValueError('Frozen web clock exhausted')
        value = self.document['times'][self.time_position]
        self.time_position += 1
        return value

    async def execute(self, name, arguments, context):
        if context != self.context or not context.owner or context.role != 'web' or context.scopes != frozenset({'web:read'}):
            raise ValueError('Frozen web ToolContext mismatch')
        schema = {'web.search': Search, 'web.scrape': Scrape}.get(name)
        if schema is None:
            raise ValueError('Unexpected frozen web tool')
        request = schema.model_validate(arguments).model_dump(mode='json')
        key = digest({'tool': name, 'request': request, 'context': {**asdict(context), 'scopes': sorted(context.scopes)}})
        occurrence = self.counts.get(key, 0)
        self.counts[key] = occurrence + 1
        if self.delegate:
            call = {'tool': name, 'request': request}
            # Allocate occurrence before awaiting: completion order must not bind requests.
            self.calls.setdefault(key, []).append(call)
            try:
                result = await self.delegate(name, request)
            except ProviderFailure as exc:
                call['failure'] = {k: getattr(exc, k) for k in ('provider', 'transient', 'ambiguous', 'category', 'retry_after')}
                raise
            except ToolDenied as exc:
                call['denied'] = exc.gate
                raise
            call['result'] = copy.deepcopy(result)
            return result
        entries = self.document['calls'].get(key, [])
        if occurrence >= len(entries):
            raise ValueError('Frozen web request drift; refusing network fallback')
        call = entries[occurrence]
        if call['tool'] != name or call['request'] != request:
            raise ValueError('Frozen web request changed')
        if 'failure' in call:
            raise ProviderFailure(**call['failure'])
        if 'denied' in call:
            raise ToolDenied(call['denied'])
        return copy.deepcopy(call['result'])

    def assert_consumed(self):
        if self.delegate:
            return
        if self.counts != {key: len(entries) for key, entries in self.document['calls'].items()}:
            raise ValueError('Unconsumed frozen web calls')
        if self.time_position != len(self.document['times']):
            raise ValueError('Unconsumed frozen web clock')


async def collect(identity, config, tape):
    # Preserve observed deadline decisions and exact timeout arguments. Do not change
    # the event loop clock used by provider timeouts, retries or asyncio scheduling.
    proxy = SimpleNamespace(Semaphore=asyncio.Semaphore, gather=asyncio.gather,
                            get_running_loop=lambda: SimpleNamespace(time=tape.time))
    with patch('email_agentic.agents.web_research.asyncio', proxy):
        try:
            value = {'status': 'succeeded', 'data': await WebResearchAgent(
                tape, read_pages=config['read_pages'], duckduckgo_enabled=config['duckduckgo_enabled']
            ).run(identity, tape.context)}
        except ProviderFailure as exc:
            value = {'status': 'failed', 'provider': exc.provider, 'error_code': exc.category}
    tape.assert_consumed()
    return value


async def run(args):
    if args.output.exists() or (args.command == 'record' and args.cassette.exists()):
        raise ValueError('Refusing to overwrite frozen web evidence')
    source = json.loads(args.input.read_text())
    identity = {key: source['input'][key] for key in ('company_name', 'domain')}
    context = ToolContext('offline-eval', 'web', frozenset({'web:read'}), 'frozen-web-eval')
    if args.command == 'record':
        import httpx
        from email_agentic.integrations.duckduckgo import DuckDuckGo
        from email_agentic.integrations.firecrawl import Firecrawl
        from email_agentic.integrations.tavily import Tavily
        from email_agentic.platform.config import get_settings

        settings = get_settings()
        if not 0 <= args.read_pages <= 12:
            raise ValueError('Frozen web recording permits at most12 page reads')
        config = {'read_pages': args.read_pages if settings.firecrawl_api_key.get_secret_value() else 0,
                  'duckduckgo_enabled': settings.duckduckgo_enabled}
        async with httpx.AsyncClient(timeout=45) as client:
            tavily = Tavily(client, settings.tavily_api_key.get_secret_value())
            firecrawl = Firecrawl(client, settings.firecrawl_api_key.get_secret_value())
            ddg = DuckDuckGo(settings.duckduckgo_enabled)

            async def provider(name, request):
                if name == 'web.search':
                    integration = ddg if request['provider'] == 'duckduckgo' else tavily
                    return await integration.search(request['query'], request['news'])
                return await firecrawl.scrape(request['url'], request['timeout_seconds'])

            tape = WebTape(context, delegate=provider)
            result = await collect(identity, config, tape)
        document = {'version': 1, 'scope': 'web_research_agent_tool_provider',
                    'source_input_sha256': digest(source), 'identity': identity, 'config': config,
                    'calls': tape.calls, 'times': tape.times, 'branch_sha256': digest(result)}
        document['sha256'] = digest(document)
        write_private(args.cassette, document)
    else:
        document = json.loads(args.cassette.read_text())
        if document.get('version') != 1 or document.get('sha256') != digest({k:v for k,v in document.items() if k != 'sha256'}):
            raise ValueError('Frozen web cassette checksum changed')
        if document['source_input_sha256'] != digest(source) or document['identity'] != identity:
            raise ValueError('Frozen web source input drift')
        tape = WebTape(context, document=document)
        result = await collect(identity, document['config'], tape)
        if digest(result) != document['branch_sha256']:
            raise ValueError('Frozen web branch drift')
    write_private(args.output, {'scope': document['scope'], 'mode': args.command,
                               'cassette_sha256': document['sha256'], 'source_input_sha256': digest(source),
                               'branch_sha256': digest(result), 'branch': result,
                               'full_workflow_replay': 'not_evaluated', 'factual_accuracy': 'not_evaluated',
                               'product_acceptance': 'not_evaluated'})
    print('Web provider collection completed; mode=' + args.command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['record', 'replay'])
    parser.add_argument('--input', type=Path, required=True, help='Effective private case input')
    parser.add_argument('--cassette', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--read-pages', type=int, default=2, help='Record-only page-read cap, at most12')
    asyncio.run(run(parser.parse_args()))


if __name__ == '__main__':
    main()
