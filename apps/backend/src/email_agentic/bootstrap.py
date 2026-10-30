from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from email_agentic.models.tools import (
    Empty as Empty,
    ReadInbox as ReadInbox,
    Domain as Domain,
    Search as Search,
    CalendarWindow as CalendarWindow,
    Scrape as Scrape,
    Action as Action,
)

from email_agentic.domains.approvals.service import Approvals
from email_agentic.domains.companies.service import Companies
from email_agentic.domains.inbox.service import Inbox
from email_agentic.domains.inbox.drafts import GmailDrafts
from email_agentic.domains.inbox.automation import EmailAutomation
from email_agentic.domains.inbox.sync import GmailSync
from email_agentic.domains.inbox.calendar import CalendarAutomation
from email_agentic.domains.knowledge.service import Knowledge
from email_agentic.domains.publication.service import Publication
from email_agentic.domains.publication.application import PublicationApplication
from email_agentic.domains.inbox.draft_application import DraftApplication
from email_agentic.domains.reports.service import Reports
from email_agentic.domains.research.service import ResearchService
from email_agentic.integrations.google import Google
from email_agentic.integrations.firecrawl import Firecrawl
from email_agentic.integrations.duckduckgo import DuckDuckGo
from email_agentic.integrations.llm import LLM
from email_agentic.integrations.tavily import Tavily
from email_agentic.platform.database import Database
from email_agentic.ports.research import SearchProvider
from email_agentic.runtime.jobs import Jobs
from email_agentic.tools.harness import Tool, ToolExecutor


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
    calendar_automation: CalendarAutomation


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
            provider: SearchProvider = duckduckgo if request.provider == "duckduckgo" else tavily
            return await provider.search(request.query, request.news)

        async def scrape(request, context):
            return await firecrawl.scrape(request.url, request.timeout_seconds)

        async def read_email(request, context):
            return await GmailSync(db, google, settings).run(context.owner, request.retry_failed)

        draft_application = DraftApplication(drafts, google)
        publication_application = PublicationApplication(publication, google)

        async def create_draft(request, context):
            return await draft_application.execute(context.owner, request.action_id)

        async def publish(request, context):
            return await publication_application.execute(context.owner, request.action_id)

        for name, schema, scope, roles, handler in [
            ("company.lookup", Domain, "company:read", {"company", "research"}, lookup),
            ("memory.retrieve", Domain, "memory:read", {"memory", "research"}, retrieve),
            ("calendar.list", CalendarWindow, "calendar:read", {"calendar", "scheduler"}, calendar),
            ("web.search", Search, "web:read", {"web"}, search),
            ("web.scrape", Scrape, "web:read", {"web"}, scrape),
            ("email.read", ReadInbox, "email:read", {"email", "scheduler"}, read_email),
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
            Approvals(db, companies, settings.app_timezone),
            publication,
            knowledge,
            companies,
            Inbox(db),
            tools,
            llm,
            google,
            drafts,
            EmailAutomation(db, research, llm, settings),
            CalendarAutomation(db, research, llm, settings),
        )
        try:
            yield container
        finally:
            await db.close()
