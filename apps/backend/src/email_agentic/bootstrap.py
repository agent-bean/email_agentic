from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from email_agentic.domains.approvals.service import Approvals
from email_agentic.domains.companies.service import Companies
from email_agentic.domains.inbox.service import Inbox
from email_agentic.domains.inbox.drafts import GmailDrafts
from email_agentic.domains.inbox.automation import EmailAutomation
from email_agentic.domains.inbox.sync import GmailSync
from email_agentic.domains.knowledge.service import Knowledge
from email_agentic.domains.publication.service import Publication
from email_agentic.domains.reports.service import Reports
from email_agentic.domains.research.service import ResearchService
from email_agentic.integrations.google import Google
from email_agentic.integrations.firecrawl import Firecrawl
from email_agentic.integrations.duckduckgo import DuckDuckGo
from email_agentic.integrations.llm import LLM
from email_agentic.integrations.tavily import Tavily
from email_agentic.platform.database import Database
from email_agentic.platform.errors import ProviderFailure
from email_agentic.runtime.jobs import Jobs
from email_agentic.tools.harness import Tool, ToolExecutor


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


@dataclass
class Container:
    settings: object
    db: Database
    jobs: Jobs
    research: ResearchService
    reports: Reports
    approvals: Approvals
    publication: Publication
    knowledge: Knowledge
    companies: Companies
    inbox: Inbox
    tools: ToolExecutor
    llm: LLM
    google: Google
    drafts: GmailDrafts
    email_automation: EmailAutomation


@asynccontextmanager
async def build_container(settings):
    db = Database(settings.dsn)
    await db.open()
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        companies = Companies(db)
        knowledge = Knowledge(db)
        google = Google(client, settings)
        tavily = Tavily(client, settings.tavily_api_key.get_secret_value())
        duckduckgo = DuckDuckGo(settings.duckduckgo_enabled)
        firecrawl = Firecrawl(client, settings.firecrawl_api_key.get_secret_value())
        publication = Publication(db, knowledge)
        drafts = GmailDrafts(db)
        tools = ToolExecutor(db, settings.tool_limit_per_minute)

        async def lookup(request, context):
            return await companies.lookup(context.owner, request.domain)

        async def retrieve(request, context):
            return await knowledge.retrieve(context.owner, request.domain)

        async def calendar(request, context):
            return await google.calendar(request.start, request.end)

        async def search(request, context):
            provider = duckduckgo if request.provider == "duckduckgo" else tavily
            return await provider.search(request.query, request.news)

        async def scrape(request, context):
            return await firecrawl.scrape(request.url, request.timeout_seconds)

        async def read_email(request, context):
            return await GmailSync(db, google, settings).run(context.owner)

        async def create_draft(request, context):
            report = await drafts.package(context.owner, request.action_id)
            if report is None:
                return {"status": "unchanged"}
            try:
                response = await google.find_draft(report["correlation_id"])
                if response is None and not report["reconcile_only"]:
                    response = await google.create_draft(report)
                if response is None:
                    await drafts.complete(request.action_id, "unknown", error="receipt_not_found")
                    return {"status": "unknown"}
                if not response.get("id") or response.get("message", {}).get("threadId") != report["source_message"]["thread_id"]:
                    raise ProviderFailure("gmail", ambiguous=True, category="invalid_draft_receipt")
                await drafts.complete(request.action_id, "succeeded", response["id"], response["message"]["threadId"])
                return {"status": "succeeded"}
            except ProviderFailure as exc:
                if exc.ambiguous:
                    # A lost POST response is not permission to create another draft.
                    try:
                        receipt = await google.find_draft(report["correlation_id"])
                        if receipt and receipt.get("message", {}).get("threadId") == report["source_message"]["thread_id"]:
                            await drafts.complete(request.action_id, "succeeded", receipt["id"], receipt["message"]["threadId"])
                            return {"status": "succeeded"}
                    except ProviderFailure:
                        pass
                await drafts.complete(request.action_id, "unknown" if exc.ambiguous or report["reconcile_only"] else "failed",
                                      error=f"{exc.provider}:{exc.category}")
                raise

        async def publish(request, context):
            report = await publication.package(context.owner, request.action_id)
            if report is None:
                return {"status": "unchanged"}
            try:
                if report["action_kind"] == "kb":
                    await publication.save_kb(report)
                    return {"status": "succeeded"}
                response = await google.send(report)
                if (not isinstance(response.get("id"), str) or not response["id"]
                    or (report.get("source_message")
                        and response.get("threadId") != report["source_message"]["thread_id"])):
                    raise ProviderFailure("gmail", ambiguous=True, category="invalid_receipt")
                await publication.complete(request.action_id, "succeeded", response["id"])
                return {"status": "succeeded"}
            except ProviderFailure as exc:
                await publication.complete(
                    request.action_id, "unknown" if exc.ambiguous else "failed", error=f"{exc.provider}:{exc.category}"
                )
                raise

        for name, schema, scope, roles, handler in [
            ("company.lookup", Domain, "company:read", {"company", "research"}, lookup),
            ("memory.retrieve", Domain, "memory:read", {"memory", "research"}, retrieve),
            ("calendar.list", CalendarWindow, "calendar:read", {"calendar", "scheduler"}, calendar),
            ("web.search", Search, "web:read", {"web"}, search),
            ("web.scrape", Scrape, "web:read", {"web"}, scrape),
            ("email.read", Empty, "email:read", {"email", "scheduler"}, read_email),
            ("email.draft", Action, "email:draft", {"email"}, create_draft),
            ("email.send", Action, "publication:execute", {"publication"}, publish),
            ("knowledge.publish", Action, "publication:execute", {"publication"}, publish),
        ]:
            authorize = None
            if name == "email.draft":
                async def authorize(request, context):
                    return await drafts.authorized(context.owner, request.action_id)
            if name in {"email.send", "knowledge.publish"}:
                kind = "email" if name == "email.send" else "kb"

                async def authorize(request, context, expected_kind=kind):
                    return await publication.authorized(context.owner, request.action_id, expected_kind)

            tools.register(name, Tool(schema, scope, frozenset(roles), handler, authorize))
        research = ResearchService(db, settings)
        llm = LLM(db, settings, client)
        container = Container(
            settings,
            db,
            Jobs(db),
            research,
            Reports(db, knowledge),
            Approvals(db, companies),
            publication,
            knowledge,
            companies,
            Inbox(db),
            tools,
            llm,
            google,
            drafts,
            EmailAutomation(db, research, llm, settings),
        )
        try:
            yield container
        finally:
            await db.close()
