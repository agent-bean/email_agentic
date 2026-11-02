"""Validated delivery packages and untrusted provider receipt boundaries."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from email_agentic.models.reports import AttachmentContent, Recipients


class EmailPackage(BaseModel):
    # Preserve domain metadata for compatible provider doubles and adapters.
    model_config = ConfigDict(extra="allow")
    email_subject: str
    email_body: str
    recipients: Recipients
    correlation_id: str
    source_message: dict[str, Any] | None = None
    attachments: list[AttachmentContent] = Field(default_factory=list)
    gmail_draft_provider_id: str | None = None

    def provider_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude_none=True)


class PublicationPackage(EmailPackage):
    id: UUID
    owner: str
    run_id: UUID
    markdown: str
    action_id: UUID
    action_kind: Literal["email", "kb"]


class DraftPackage(EmailPackage):
    reconcile_only: bool


class MessageReceipt(BaseModel):
    id: str = Field(min_length=1, strict=True)
    thread_id: str | None = Field(default=None, alias="threadId", strict=True)


class DraftMessageReceipt(BaseModel):
    thread_id: str = Field(alias="threadId", min_length=1, strict=True)


class DraftReceipt(BaseModel):
    id: str = Field(min_length=1, strict=True)
    message: DraftMessageReceipt
