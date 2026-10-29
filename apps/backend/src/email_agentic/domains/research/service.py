import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.types.json import Jsonb

from email_agentic.platform.errors import NotFound
from email_agentic.runtime.jobs import enqueue


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(min_length=2, max_length=200)
    domain: str = Field(min_length=3, max_length=253)
    context: str = Field("", max_length=12000)
    source_email: str | None = Field(None, min_length=1, max_length=30000)

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


class ResearchService:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings

    async def create(self, owner, request, key):
        run_id = uuid.uuid4()
        config = {
            "target_seconds": self.settings.report_target_seconds,
            "timeout_seconds": self.settings.research_timeout_seconds,
            "model": self.settings.llm_model,
            "workflow_version": 4,
            "prompt_version": 7,
            "duckduckgo_enabled": self.settings.duckduckgo_enabled,
            "firecrawl_max_pages": self.settings.firecrawl_max_pages
            if self.settings.firecrawl_api_key.get_secret_value() else 0,
        }
        async with self.db.transaction() as connection:
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"request:{owner}:{key}",)
            )
            old = await (
                await connection.execute(
                    "SELECT entity_id FROM jobs WHERE owner=%s AND dedupe_key=%s",
                    (owner, f"request:{owner}:{key}"),
                )
            ).fetchone()
            if old:
                return old["entity_id"]
            await connection.execute(
                """INSERT INTO research_runs(id,owner,company_name,domain,context,source_email,config)
                VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, owner, request.company_name, request.domain, request.context,
                 request.source_email, Jsonb(config)),
            )
            await enqueue(connection, owner, "research", run_id, f"request:{owner}:{key}")
        return run_id

    async def get(self, owner, run_id):
        row = await self.db.one("SELECT * FROM research_runs WHERE id=%s AND owner=%s", (run_id, owner))
        if not row:
            raise NotFound()
        return row

    async def status(self, run_id, status, error=None):
        await self.db.execute(
            "UPDATE research_runs SET status=%s,error_code=%s,updated_at=now() WHERE id=%s",
            (status, error, run_id),
        )
