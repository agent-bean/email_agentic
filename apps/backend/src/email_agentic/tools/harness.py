import time
from dataclasses import dataclass
from typing import Awaitable, Callable
from pydantic import BaseModel, ValidationError

from email_agentic.platform.errors import ToolDenied
from email_agentic.platform.telemetry import TOOLS, tracer


@dataclass(frozen=True)
class ToolContext:
    owner: str
    role: str
    scopes: frozenset[str]
    run_id: str | None = None


@dataclass
class Tool:
    schema: type[BaseModel]
    scope: str
    roles: frozenset[str]
    handler: Callable[..., Awaitable]
    authorize: Callable[..., Awaitable] | None = None


class ToolExecutor:
    def __init__(self, db, limit):
        self.db, self.limit = db, limit
        self.registry: dict[str, Tool] = {}

    def register(self, name, tool):
        if name in self.registry:
            raise ValueError("Duplicate tool")
        self.registry[name] = tool

    async def audit(self, context, name, outcome):
        await self.db.execute(
            """INSERT INTO audit_events(owner,actor_role,tool,run_id,outcome)
            VALUES(%s,%s,%s,%s,%s)""",
            (context.owner, context.role, name, context.run_id, outcome),
        )

    async def execute(self, name, arguments, context):
        tool = self.registry.get(name)
        gate = "schema"
        try:
            if not tool:
                raise ToolDenied(gate)
            try:
                request = tool.schema.model_validate(arguments)
            except ValidationError:
                raise ToolDenied(gate) from None
            gate = "authentication"
            if not context.owner:
                raise ToolDenied(gate)
            gate = "scopes"
            if tool.scope not in context.scopes or context.role not in tool.roles:
                raise ToolDenied(gate)
            if tool.authorize is not None and not await tool.authorize(request, context):
                raise ToolDenied(gate)
            gate = "rate_limit"
            row = await self.db.one(
                """INSERT INTO tool_limits VALUES(%s,%s,%s,1)
                ON CONFLICT(owner,tool,bucket) DO UPDATE SET calls=tool_limits.calls+1 RETURNING calls""",
                (context.owner, name, int(time.time() // 60)),
            )
            if row["calls"] > self.limit:
                raise ToolDenied(gate)
            gate = "audit"
            await self.audit(context, name, "intent")
        except ToolDenied:
            TOOLS.labels(name, "denied").inc()
            await self.audit(context, name, f"denied:{gate}")
            raise
        with tracer().start_as_current_span(f"tool.{name}"):
            try:
                result = await tool.handler(request, context)
            except Exception:
                TOOLS.labels(name, "failed").inc()
                await self.audit(context, name, "failed")
                raise
            TOOLS.labels(name, "succeeded").inc()
            await self.audit(context, name, "succeeded")
            return result
