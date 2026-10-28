import pytest
from pydantic import ValidationError

from email_agentic.domains.reports.service import ReportEdit, Recipients
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.config import Settings


def test_reject_non_domain_and_extra_fields():
    with pytest.raises(ValidationError):
        ResearchRequest(company_name="Example", domain="http://127.0.0.1/private")
    with pytest.raises(ValidationError):
        ResearchRequest(company_name="Example", domain="example.com", owner="someone-else")


def test_prevent_email_header_injection():
    with pytest.raises(ValidationError):
        Recipients(to=["person@example.com\r\nBcc:other@example.com"])
    with pytest.raises(ValidationError):
        ReportEdit(
            version=1, markdown="Body", email_subject="Hello\r\nBcc:other@example.com", email_body="Body"
        )


def test_production_fails_closed_without_access_configuration():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", _env_file=None)
    settings = Settings(APP_ENV="test", RESEARCH_TIMEOUT_SECONDS="", _env_file=None)
    assert settings.research_timeout_seconds == 180
    assert settings.report_target_seconds == 42
