import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator

class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(min_length=2, max_length=200)
    domain: str = Field(min_length=3, max_length=253)
    context: str = Field("", max_length=12000)
    source_email: str | None = Field(None, min_length=1, max_length=30000)
    source_input_id: uuid.UUID | None = None
    source_meeting_id: uuid.UUID | None = None

    @field_validator("source_email")
    @classmethod
    def nonempty_source(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Source email must contain text")
        return value

    @field_validator("domain")
    @classmethod
    def domain_only(cls, value):
        import re

        value = value.strip().lower().rstrip(".")
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value):
            raise ValueError("Use a public domain name without scheme or path")
        return value
