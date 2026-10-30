"""Read contracts for provider snapshots, including failed and retired inputs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PageExtraction(BaseModel):
    page: int
    method: str
    status: str
    text: str = ""


class Extraction(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    text: str | None = None
    pages: int | None = None
    pages_read: int | None = None
    truncated: bool | None = None
    page_results: list[PageExtraction] | None = None


class SourceAttachment(BaseModel):
    filename: str
    size: int
    mime_type: str | None = None
    sha256: str | None = None
    extraction: Extraction


class EmailContent(BaseModel):
    # Provider metadata is preserved; a failed read or retention tombstone lacks a body.
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    thread_id: str | None = None
    mailbox: str | None = None
    status: str | None = None
    subject: str | None = None
    body: str | None = None
    source_text: str | None = None
    body_format: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    attachments: list[SourceAttachment] = Field(default_factory=list)
    received_at: str | None = None


class EventTime(BaseModel):
    model_config = ConfigDict(extra="allow")
    dateTime: str | None = None
    date: str | None = None
    timeZone: str | None = None


class Attendee(BaseModel):
    model_config = ConfigDict(extra="allow")
    email: str | None = None
    displayName: str | None = None
    responseStatus: str | None = None


class MeetingContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str | None = None
    summary: str | None = None
    description: str | None = None
    location: str | None = None
    status: str | None = None
    start: EventTime | None = None
    end: EventTime | None = None
    attendees: list[Attendee] = Field(default_factory=list)
    organizer: Attendee | None = None


class InputRecord(BaseModel):
    id: UUID
    owner: str
    provider: str
    source_id: str
    created_at: datetime
    purged_at: datetime | None = None
    calendar_available: bool | None = None
    intake_status: str | None = None
    research_run_id: UUID | None = None
    meeting_revision: str | None = None


class EmailInput(InputRecord):
    kind: Literal["email"]
    content: EmailContent


class MeetingInput(InputRecord):
    kind: Literal["meeting"]
    content: MeetingContent


SourceInput = Annotated[EmailInput | MeetingInput, Field(discriminator="kind")]
