from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ReadInbox(Empty):
    retry_failed: bool = False

class Domain(Empty):
    domain: str = Field(min_length=3, max_length=253)

class Search(Empty):
    query: str = Field(min_length=2, max_length=1000)
    news: bool = False
    provider: Literal["tavily", "duckduckgo"] = "tavily"

class CalendarWindow(Empty):
    start: str
    end: str

class Scrape(Empty):
    url: str = Field(min_length=8, max_length=4000)
    timeout_seconds: float = Field(15, ge=1, le=15)

class Action(Empty):
    action_id: UUID
