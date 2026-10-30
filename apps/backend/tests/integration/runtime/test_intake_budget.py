import json
import uuid

import httpx
import pytest

from email_agentic.integrations.llm import LLM
from email_agentic.models.agents import Draft
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure
from email_agentic.runtime.budget import processing_budget
from email_agentic.runtime.execution import begin_intake, reserve_intake_attempt
from email_agentic.runtime.jobs import Jobs, enqueue


async def test_intake_llm_repair_and_restart_share_durable_attempt_and_time_budget(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    input_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO inputs(id,owner,provider,source_id,kind,content) VALUES(%s,%s,'google',%s,'email','{}')",
        (input_id, owner, str(input_id)),
    )
    async with db.transaction() as connection:
        await enqueue(connection, owner, "email_intake", input_id, str(input_id))
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        if len(calls) == 2:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": "invalid JSON"}}],
        })

    settings = Settings(APP_ENV="test", LLM_MODEL="protocol-test", LLM_BASE_URL="https://example.invalid/v1",
                        LLM_API_KEY="test-only", _env_file=None)
    remaining_budgets = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for index, category in enumerate(("http_503", "retry_exhausted"), 1):
            job = await db.one(
                """UPDATE jobs SET status='running',attempt=%s,claim_token=%s,
                lease_until=now()+interval '60 seconds' WHERE dedupe_key=%s RETURNING *""",
                (index, uuid.uuid4(), str(input_id)),
            )
            async with db.transaction() as connection:
                remaining = await begin_intake(connection, job, 30)
            remaining_budgets.append(remaining)

            async def reserve(key):
                async with db.transaction() as connection:
                    return await reserve_intake_attempt(connection, job, key)

            with processing_budget(remaining, reserve):
                with pytest.raises(ProviderFailure) as error:
                    await LLM(db, settings, client).structured(None, Draft, "System", "Context", input_id=input_id)
            assert error.value.category == category
            assert await Jobs(db).finish(job, "failed", f"llm:{category}", retry=index == 1)
    assert len(calls) == 3
    assert remaining_budgets[1] < remaining_budgets[0]
    saved = await db.one("SELECT execution,status FROM jobs WHERE dedupe_key=%s", (str(input_id),))
    assert list(saved["execution"]["provider_attempts"].values()) == [3]
    assert "started_at" not in saved["execution"]["processing_budget"]
    assert saved["status"] == "failed"
