import uuid
import pytest
from pydantic import BaseModel, ConfigDict
from email_agentic.platform.errors import ToolDenied
from email_agentic.tools.harness import Tool, ToolContext, ToolExecutor


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: int


async def test_harness_checks_before_execute_and_writes_safe_audit(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    executed = []

    async def handler(request, context):
        executed.append(request.value)
        return request.value * 2

    tools = ToolExecutor(db, limit=1)
    tools.register("test.double", Tool(Input, "read", frozenset({"research"}), handler))
    context = ToolContext(owner, "research", frozenset({"read"}))
    with pytest.raises(ToolDenied, match="schema"):
        await tools.execute("test.double", {"value": 3, "owner": "forged"}, context)
    with pytest.raises(ToolDenied, match="scopes"):
        await tools.execute("test.double", {"value": 3}, ToolContext(owner, "web", frozenset({"read"})))
    assert not executed
    assert await tools.execute("test.double", {"value": 3}, context) == 6
    with pytest.raises(ToolDenied, match="rate_limit"):
        await tools.execute("test.double", {"value": 4}, context)
    assert executed == [3]
    audit = await db.all("SELECT outcome FROM audit_events WHERE owner=%s ORDER BY id", (owner,))
    assert [x["outcome"] for x in audit] == [
        "denied:schema",
        "denied:scopes",
        "intent",
        "succeeded",
        "denied:rate_limit",
    ]
