import asyncio
import json

import httpx
import pytest

from email_agentic.agents.contracts import Draft
from email_agentic.integrations.llm import LLM
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure
from email_agentic.runtime.budget import processing_budget, provider_operation


@pytest.mark.parametrize("first", [
    '{"markdown":"Report","email_subject":"Subject","email_body":"Body"',
    '{"markdown":"Report","email_subject":"Subject"}',
])
async def test_invalid_structured_output_gets_one_format_correction_and_counts_both_calls(first):
    requests, usage = [], []

    class Usage:
        async def execute(self, statement, values):
            usage.append(values)

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["response_format"]["type"] == "json_schema"
        content = first if len(requests) == 1 else json.dumps({
            "markdown": "Report", "email_subject": "Subject", "email_body": "Body",
        })
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 2},
        })

    settings = Settings(APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL="https://example.com/v1",
                        LLM_API_KEY="test-only", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await LLM(Usage(), settings, client).structured(
            "run", Draft, "Return a draft", "PRIVATE_ORIGINAL_CONTEXT"
        )
    assert result.email_body == "Body"
    assert len(requests) == len(usage) == 2
    assert all(row[3:] == (9, 2, None) for row in usage)
    correction = json.dumps(requests[1]["messages"])
    assert "PRIVATE_ORIGINAL_CONTEXT" not in correction
    assert json.loads(requests[1]["messages"][1]["content"])["invalid_output"] == first


@pytest.mark.parametrize("slow_second", [False, True])
async def test_format_correction_stops_after_one_attempt_and_keeps_original_time_budget(slow_second):
    requests, usage = [], []

    class Usage:
        async def execute(self, statement, values):
            usage.append(values)

    async def respond(request):
        requests.append(json.loads(request.content))
        if slow_second:
            await asyncio.sleep(0.03)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "invalid JSON"}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 2},
        })

    settings = Settings(APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL="https://example.com/v1",
                        LLM_API_KEY="test-only", RESEARCH_TIMEOUT_SECONDS=0.05, _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(ProviderFailure) as error:
            await LLM(Usage(), settings, client).structured("run", Draft, "Return a draft", "Context")
    assert len(requests) == 2
    assert error.value.category == ("network_or_timeout" if slow_second else "non_json")
    assert len(usage) == (1 if slow_second else 2)


async def test_format_repair_and_worker_replay_share_attempt_cap_but_citation_correction_is_distinct():
    requests, attempts = [], {}

    class Usage:
        async def execute(self, *_):
            pass

    async def reserve(key):
        if attempts.get(key, 0) >= 3:
            return False
        attempts[key] = attempts.get(key, 0) + 1
        return True

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 2:
            return httpx.Response(503, json={})
        content = "invalid JSON" if len(requests) < 4 else json.dumps({
            "markdown": "Report", "email_subject": "Subject", "email_body": "Body",
        })
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        })

    settings = Settings(APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL="https://example.invalid/v1",
                        LLM_API_KEY="test-only", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for category in ("http_503", "retry_exhausted", "retry_exhausted"):
            with processing_budget(5, reserve):
                with pytest.raises(ProviderFailure) as error:
                    await LLM(Usage(), settings, client).structured("run", Draft, "System", "Context")
            assert error.value.category == category
        assert len(requests) == 3
        with processing_budget(5, reserve), provider_operation("citation_correction"):
            result = await LLM(Usage(), settings, client).structured("run", Draft, "System", "Context")
        assert result.email_body == "Body"
        assert sorted(attempts.values()) == [1, 3]


async def test_shared_processing_deadline_prevents_llm_request_and_reservation():
    class Unused:
        async def execute(self, *_):
            pytest.fail("No usage write without a provider response")

    async def reserve(_):
        pytest.fail("No attempt reservation after processing budget expiry")

    def respond(_):
        pytest.fail("No provider request after processing budget expiry")

    settings = Settings(APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL="https://example.invalid/v1",
                        LLM_API_KEY="test-only", _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with processing_budget(0, reserve):
            with pytest.raises(ProviderFailure) as error:
                await LLM(Unused(), settings, client).structured("run", Draft, "System", "Context")
    assert error.value.category == "network_or_timeout"
