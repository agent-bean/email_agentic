from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from email_agentic.models.research import ResearchRequest

class RunSummary(BaseModel):
    id: UUID
    company_name: str
    domain: str
    context: str
    status: str
    version: int
    created_at: datetime
    elapsed_seconds: float | None
    error_code: str | None
    config: dict

class RunRecord(RunSummary):
    raw_purged_at: datetime | None = None
    history_purged_at: datetime | None = None
    source_email: str | None = None
    source_input_id: UUID | None = None
    source_message: dict | None = None
    source_meeting_id: UUID | None = None
    source_meeting: dict | None = None

class ReportRow(BaseModel):
    id: UUID
    run_id: UUID
    version: int
    markdown: str
    email_subject: str
    email_body: str
    recipients: dict[str, list[str]]
    send_email: bool
    save_kb: bool
    quality: dict
    artifacts: list[dict]

class ApprovalRow(BaseModel):
    id: UUID
    report_id: UUID
    status: str
    expires_at: datetime

class ActionRow(BaseModel):
    id: UUID
    kind: str
    status: str
    provider_id: str | None
    error_code: str | None

class RunDetail(BaseModel):
    run: RunRecord
    reports: list[ReportRow]
    approvals: list[ApprovalRow]
    actions: list[ActionRow]
    branches: list[dict]
    evidence: list[dict]
    usage: list[dict]
    gmail_drafts: list[dict]
    gmail_drafts_available: bool

class Created(BaseModel):
    id: UUID

class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool

class IdentityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)

class IdentityConfirmation(IdentityDecision):
    company_name: str | None = None
    domain: str | None = None

    @model_validator(mode="after")
    def validate_proposal(self):
        if (self.company_name is None) != (self.domain is None):
            raise ValueError("Provide both company name and domain")
        if self.company_name is not None:
            identity = ResearchRequest(company_name=self.company_name, domain=self.domain)
            self.company_name, self.domain = identity.company_name, identity.domain
        return self

class SentReviewRow(BaseModel):
    id: UUID
    run_id: UUID
    version: int
    email_subject: str
    email_body: str
    recipients: dict[str, list[str]]
    status: str
    provider_id: str | None
    error_code: str | None
    created_at: datetime

class SentVerification(BaseModel):
    verification: str
    provider_id: str | None
