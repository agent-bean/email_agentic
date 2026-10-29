import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator
from psycopg.types.json import Jsonb

from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.runtime.jobs import enqueue


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company_name: str = Field(min_length=2, max_length=200)
    domain: str = Field(min_length=3, max_length=253)
    context: str = Field("", max_length=12000)
    source_email: str | None = Field(None, min_length=1, max_length=30000)
    source_input_id: uuid.UUID | None = None

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
            "prompt_version": 8,
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
            source = None
            source_email = request.source_email
            if request.source_input_id:
                if request.source_email is not None:
                    raise Conflict("Choose a Gmail source or manual email text, not both")
                row = await (await connection.execute(
                    "SELECT * FROM inputs WHERE id=%s AND owner=%s AND provider='google' AND kind='email' FOR UPDATE",
                    (request.source_input_id, owner),
                )).fetchone()
                if not row:
                    raise NotFound()
                source = row["content"]
                if source.get("status") != "succeeded" or not source.get("source_text") or not source.get("headers", {}).get("Message-ID"):
                    raise Conflict("Email source is unavailable; synchronize Gmail again")
                source_email = source["source_text"]
                if len(source_email) > 30000:
                    raise Conflict("Email is longer than 30,000 characters; cannot import without truncating")
                previous = await (await connection.execute(
                    "SELECT id,company_name,domain FROM research_runs WHERE owner=%s AND source_input_id=%s",
                    (owner, request.source_input_id),
                )).fetchone()
                if previous:
                    if previous["company_name"] != request.company_name or previous["domain"] != request.domain:
                        raise Conflict("This email already has a research run for a different company")
                    return previous["id"]
            await connection.execute(
                """INSERT INTO research_runs(id,owner,company_name,domain,context,source_email,config,source_input_id,source_message)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (run_id, owner, request.company_name, request.domain, request.context,
                 source_email, Jsonb(config), request.source_input_id, Jsonb(source) if source else None),
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
