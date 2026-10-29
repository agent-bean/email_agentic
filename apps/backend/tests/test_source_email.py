import json
import uuid

import httpx
import pytest
from pydantic import ValidationError

from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.main import create_app
from email_agentic.platform.config import Settings


async def test_source_email_round_trips_exactly_and_stays_separate_from_context(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(APP_ENV="local", DATABASE_URL=db.pool.conninfo,
                        GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None)
    source = "  Subject: [TC-02] Source\r\n\r\nDỮ LIỆU MẪU\n<script>text only</script>\n\n"
    context = "Prepare internal research. Do not include this in the reply."
    async with build_container(settings) as c:
        app = create_app(settings)
        app.state.container = c
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
            response = await client.post(
                "/api/v1/runs", headers={"Origin": "http://127.0.0.1:8000",
                                        "Idempotency-Key": str(uuid.uuid4())},
                json={"company_name": "Source boundary", "domain": "example.com",
                      "context": context, "source_email": source},
            )
            assert response.status_code == 202
            run_id = response.json()["id"]
            detail = (await client.get(f"/api/v1/runs/{run_id}")).json()
            assert detail["run"]["source_email"] == source
            assert detail["run"]["context"] == context
            overview = (await client.get("/api/v1/runs")).json()
            assert all("source_email" not in item for item in overview)
            assert detail["reports"] == [] and detail["actions"] == []
            other = await c.research.create(
                f"{uuid.uuid4()}@example.invalid",
                ResearchRequest(company_name="Private source", domain="example.com", source_email=source),
                str(uuid.uuid4()),
            )
            assert (await client.get(f"/api/v1/runs/{other}")).status_code == 404
        old = await c.research.create(owner, ResearchRequest(
            company_name="Context only", domain="example.com", context=source), str(uuid.uuid4()))
        assert (await c.research.get(owner, old))["source_email"] is None


async def test_model_receives_original_email_and_research_request_as_separate_values():
    class Capture:
        async def structured(self, run_id, schema, system, payload):
            data = json.loads(payload)
            assert data["source_email"] == "  Subject: Source\r\n\nCustomer words\n"
            assert data["context"] == "Internal research request"
            return None

    await ReportGenerationAgent(Capture()).run(
        {"id": "run", "company_name": "Company", "domain": "example.com",
         "context": "Internal research request",
         "source_email": "  Subject: Source\r\n\nCustomer words\n"}, [], [])


@pytest.mark.parametrize("source", ["", " \r\n", "x" * 30001])
def test_invalid_source_email_is_rejected_instead_of_silently_modified(source):
    with pytest.raises(ValidationError):
        ResearchRequest(company_name="Company", domain="example.com", source_email=source)
