import asyncio
import json
import uuid

import httpx
import pytest

from email_agentic.agents.contracts import Draft
from email_agentic.domains.research.service import ResearchRequest, ResearchService
from email_agentic.integrations.llm import LLM
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure


@pytest.mark.parametrize("budget, succeeds", [(0.5, True), (0.03, False)])
async def test_llm_request_respects_its_budget_instead_of_shared_client_timeout(db, budget, succeeds):
    requests = []
    handlers = set()

    async def serve(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            length = next(
                int(line.split(b":", 1)[1])
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            requests.append(json.loads(await reader.readexactly(length)))
            await asyncio.sleep(0.08)
            body = json.dumps(
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                        "markdown": "Protocol test", "email_subject": "Subject", "email_body": "Body"
                    })}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
            )
            await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    settings = Settings(
        APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL=f"http://127.0.0.1:{port}",
        LLM_API_KEY="test-only", RESEARCH_TIMEOUT_SECONDS=budget, _env_file=None,
    )
    owner = f"{uuid.uuid4()}@example.invalid"
    run_id = await ResearchService(db, settings).create(
        owner, ResearchRequest(company_name="Protocol test", domain="example.invalid"), str(uuid.uuid4())
    )
    try:
        async with server, httpx.AsyncClient(timeout=0.01) as client:
            llm = LLM(db, settings, client)
            if succeeds:
                result = await llm.structured(run_id, Draft, "Protocol test", "Protocol test")
                assert result.email_subject == "Subject"
                usage = await db.one("SELECT * FROM model_usage WHERE run_id=%s", (run_id,))
                assert usage["input_tokens"] == 10 and usage["output_tokens"] == 5
            else:
                with pytest.raises(ProviderFailure) as error:
                    await llm.structured(run_id, Draft, "Protocol test", "Protocol test")
                assert error.value.category == "network_or_timeout"
                assert await db.one("SELECT id FROM model_usage WHERE run_id=%s", (run_id,)) is None
            assert requests[0]["response_format"]["json_schema"]["strict"] is True
    finally:
        server.close()
        await server.wait_closed()
        for task in list(handlers):
            task.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
