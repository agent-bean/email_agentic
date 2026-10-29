import json

import pytest
from pydantic import ValidationError

from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.domains.research.service import ResearchRequest


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
