from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Draft(StrictModel):
    markdown: str = Field(min_length=1, max_length=100000)
    email_subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    email_body: str = Field(min_length=1, max_length=30000)


class BranchResult(StrictModel):
    role: str
    status: str
    facts: list[dict] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    error_code: str | None = None


class EmailIntakeDecision(StrictModel):
    disposition: Literal['business', 'ignore', 'unclear']
    company_name: str = Field(max_length=200)
    domain: str = Field(max_length=253)
    reason: Literal['business_request', 'automated', 'personal', 'unclear']
