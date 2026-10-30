from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from email_agentic.models.research import ResearchRequest
from email_agentic.models.reports import AttachmentDescriptor, Recipients
from email_agentic.models.sources import EmailContent, MeetingContent

RunStatus = Literal["queued", "awaiting_identity", "running", "draft_ready", "failed"]
ApprovalStatus = Literal["pending", "approved", "rejected", "superseded", "expired"]
ActionStatus = Literal["pending", "running", "succeeded", "failed", "unknown", "blocked"]
DraftStatus = Literal["pending", "running", "succeeded", "failed", "unknown", "blocked", "superseded", "sent"]

class RunSummary(BaseModel):
    id: UUID
    company_name: str
    domain: str
    context: str
    status: RunStatus
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
    source_message: EmailContent | None = None
    source_meeting_id: UUID | None = None
    source_meeting: MeetingContent | None = None

class ReportRow(BaseModel):
    id: UUID
    run_id: UUID
    version: int
    markdown: str
    email_subject: str
    email_body: str
    recipients: Recipients
    send_email: bool
    save_kb: bool
    quality: dict
    artifacts: list[AttachmentDescriptor]

class ApprovalRow(BaseModel):
    id: UUID
    report_id: UUID
    status: ApprovalStatus
    expires_at: datetime

class ActionRow(BaseModel):
    id: UUID
    kind: Literal["email", "kb"]
    status: ActionStatus
    provider_id: str | None
    error_code: str | None

class BranchRow(BaseModel):
    run_id: UUID
    branch: str
    result: dict

class EvidenceRow(BaseModel):
    id: UUID
    url: str
    title: str
    published_at: datetime | None

class UsageRow(BaseModel):
    model: str
    input_tokens: int | None
    output_tokens: int | None
    cost: str | float | None

class GmailDraftRow(BaseModel):
    id: UUID
    report_id: UUID
    status: DraftStatus
    provider_id: str | None
    thread_id: str | None
    error_code: str | None
    matches_current: bool

class RunDetail(BaseModel):
    run: RunRecord
    reports: list[ReportRow]
    approvals: list[ApprovalRow]
    actions: list[ActionRow]
    branches: list[BranchRow]
    evidence: list[EvidenceRow]
    usage: list[UsageRow]
    gmail_drafts: list[GmailDraftRow]
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
    recipients: Recipients
    status: ActionStatus
    provider_id: str | None
    error_code: str | None
    created_at: datetime

class SentVerification(BaseModel):
    verification: Literal["matched", "mismatch", "not_found", "multiple_matches", "too_large", "content_expired"]
    provider_id: str | None

class KnowledgeRow(BaseModel):
    id: UUID
    owner: str
    run_id: UUID
    report_id: UUID | None
    status: Literal["draft", "approved"]
    content: str
    created_at: datetime

class CompanyRow(BaseModel):
    id: UUID
    owner: str
    legal_name: str
    domain: str
    profile: dict
    created_at: datetime

class CurrentUser(BaseModel):
    email: str
    role: str

class Queued(BaseModel):
    status: Literal["queued"]

class DecisionResult(BaseModel):
    status: Literal["approved", "rejected"]

class JobCount(BaseModel):
    kind: str
    status: Literal["pending", "running", "done", "failed"]
    total: int

class SystemStatus(BaseModel):
    mode: Literal["local", "test", "production"]
    model: str
    target_seconds: float
    scheduler_enabled: bool
    connections: dict[str, Literal["configured", "missing", "disabled", "requires_consent"]]
    jobs: list[JobCount]
