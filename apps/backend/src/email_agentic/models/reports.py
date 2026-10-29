from email.utils import parseaddr
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Recipients(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to: list[str] = Field(default_factory=list, max_length=20)
    cc: list[str] = Field(default_factory=list, max_length=20)
    bcc: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("to", "cc", "bcc")
    @classmethod
    def emails(cls, items):
        for item in items:
            if any(x in item for x in "\r\n") or parseaddr(item)[1] != item or "@" not in item:
                raise ValueError("Use plain email addresses")
        return items

class ReportEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    markdown: str = Field(min_length=1, max_length=100000)
    email_subject: str = Field(min_length=1, max_length=200, pattern=r"^[^\r\n]+$")
    email_body: str = Field(min_length=1, max_length=30000)
    recipients: Recipients = Field(default_factory=Recipients)
    send_email: bool = False
    save_kb: bool = False
    attachment_formats: list[Literal["pdf", "docx", "md"]] = Field(default_factory=list, max_length=3)
