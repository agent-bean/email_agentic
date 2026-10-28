import asyncio
import json
import re
import uuid
from datetime import datetime, UTC
from email.utils import parsedate_to_datetime
from typing import TypedDict
from urllib.parse import urlsplit, urlunsplit

from langgraph.graph import StateGraph, START, END

from email_agentic.agents.calendar import CalendarAgent
from email_agentic.agents.company_info import CompanyInfoAgent
from email_agentic.agents.human_approval import HumanApprovalAgent
from email_agentic.agents.memory import MemoryAgent
from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.agents.web_research import WebResearchAgent
from email_agentic.tools.harness import ToolContext
from email_agentic.platform.errors import Conflict


class ResearchState(TypedDict, total=False):
    run_id: str


def canonical_url(value):
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return None
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/") or "/", parts.query, ""))


def publication_date(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            return None
    return date if date.tzinfo else date.replace(tzinfo=UTC)


def make_graph(container, checkpointer):
    c = container
    human = HumanApprovalAgent()

    async def run_record(state):
        return await c.db.one("SELECT * FROM research_runs WHERE id=%s", (state["run_id"],))

    async def identity(state):
        run = await run_record(state)
        if not run["identity_confirmed"]:
            await c.research.status(run["id"], "awaiting_identity")
            human.wait("identity", run["id"])
            run = await run_record(state)
            if not run["identity_confirmed"]:
                raise Conflict("Identity was not confirmed")
        await c.research.status(run["id"], "running")
        return {}

    async def gather(state):
        run = await run_record(state)
        definitions = [
            ("company", CompanyInfoAgent(c.tools), "company:read"),
            ("memory", MemoryAgent(c.tools), "memory:read"),
            ("calendar", CalendarAgent(c.tools), "calendar:read"),
            ("web", WebResearchAgent(c.tools), "web:read"),
        ]

        async def branch(name, agent, scope):
            existing = await c.db.one(
                "SELECT result FROM branch_results WHERE run_id=%s AND branch=%s", (run["id"], name)
            )
            if existing and existing["result"]["status"] == "succeeded":
                return
            context = ToolContext(run["owner"], name, frozenset({scope}), str(run["id"]))
            try:
                data = await agent.run(run, context)
                result = {
                    "role": name,
                    "status": "succeeded",
                    "data": json.loads(json.dumps(data, default=str)),
                }
            except Exception as exc:
                result = {"role": name, "status": "failed", "error_code": type(exc).__name__}
            await c.jobs.save_branch(run["id"], name, result)
            if name == "web" and result["status"] == "succeeded":
                for response in result["data"]:
                    for item in response.get("results", []):
                        url = canonical_url(item.get("url", ""))
                        if not url:
                            continue
                        date = publication_date(item.get("published_date"))
                        # Query-matched excerpts precede page text so navigation cannot displace them.
                        content = "\n\n".join(
                            text for text in (item.get("content"), item.get("raw_content")) if text
                        )[:8000]
                        await c.db.execute(
                            """INSERT INTO evidence(id,run_id,url,title,content,published_at)
                            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(run_id,url) DO NOTHING""",
                            (
                                uuid.uuid4(),
                                run["id"],
                                url,
                                item.get("title", "")[:1000],
                                content,
                                date,
                            ),
                        )

        await asyncio.gather(*(branch(*entry) for entry in definitions))
        return {}

    async def report(state):
        run = await run_record(state)
        existing = await c.db.one("SELECT id FROM reports WHERE run_id=%s LIMIT 1", (run["id"],))
        if existing:
            return {}
        evidence = await c.db.all(
            "SELECT id,url,title,content,published_at FROM evidence WHERE run_id=%s", (run["id"],)
        )
        if not evidence:
            raise Conflict("No evidence was retrieved; report generation stopped")
        branches = await c.db.all("SELECT branch,result FROM branch_results WHERE run_id=%s", (run["id"],))
        draft = await ReportGenerationAgent(c.llm).run(run, evidence, branches)
        known = {entry["url"] for entry in evidence}
        cited = {canonical_url(url) for url in re.findall(r"\]\((https?://[^)\s]+)\)", draft.markdown)}
        unknown = cited - known
        if unknown:
            raise Conflict("Report contains an unsupported source URL")
        elapsed = (datetime.now(UTC) - run["created_at"]).total_seconds()
        quality = {
            "cited_sources": len(cited & known),
            "source_target_met": len(cited & known) >= 12,
            "elapsed_seconds": elapsed,
            "target_seconds": run["config"]["target_seconds"],
            "time_target_met": elapsed <= run["config"]["target_seconds"],
            "factual_accuracy": "requires_review",
            "completeness": "not_evaluated",
            "readiness": "requires_review",
            "branch_failures": [x["branch"] for x in branches if x["result"]["status"] == "failed"],
            "search_failures": [
                response["research_area"]
                for branch in branches
                if branch["branch"] == "web"
                for response in (branch["result"].get("data") or [])
                if response.get("status") == "failed"
            ],
        }
        await c.reports.initial(run, draft, quality)
        await c.db.execute(
            "UPDATE research_runs SET elapsed_seconds=%s,status='draft_ready' WHERE id=%s",
            (elapsed, run["id"]),
        )
        return {}

    async def approval(state):
        run = await run_record(state)
        decision = await c.db.one(
            """SELECT a.* FROM approvals a JOIN reports r ON r.id=a.report_id
            WHERE r.run_id=%s ORDER BY r.version DESC LIMIT 1""",
            (run["id"],),
        )
        if decision["status"] == "pending":
            human.wait("publication_approval", decision["id"])
            decision = await c.db.one(
                """SELECT a.* FROM approvals a JOIN reports r ON r.id=a.report_id
                WHERE r.run_id=%s ORDER BY r.version DESC LIMIT 1""",
                (run["id"],),
            )
        if decision["status"] == "pending":
            raise Conflict("No current approval decision is available")
        return {}

    graph = StateGraph(ResearchState)
    for name, node in [
        ("identity", identity),
        ("gather", gather),
        ("report", report),
        ("approval", approval),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "identity")
    graph.add_edge("identity", "gather")
    graph.add_edge("gather", "report")
    graph.add_edge("report", "approval")
    graph.add_edge("approval", END)
    return graph.compile(checkpointer=checkpointer)
