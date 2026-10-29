import uuid

import pytest

from email_agentic.bootstrap import build_container
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure, ToolDenied
from email_agentic.tools.harness import ToolContext


async def test_disabled_provider_obeys_tool_schema_role_and_audit(db):
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo,
                        DUCKDUCKGO_ENABLED=False, _env_file=None)
    async with build_container(settings) as c:
        owner = f"{uuid.uuid4()}@example.invalid"
        context = ToolContext(owner, "web", frozenset({"web:read"}))
        request = {"query": "Company", "provider": "duckduckgo"}
        with pytest.raises(ToolDenied, match="scopes"):
            await c.tools.execute("web.search", request,
                                  ToolContext(owner, "calendar", frozenset({"web:read"})))
        with pytest.raises(ToolDenied, match="schema"):
            await c.tools.execute("web.search", {**request, "provider": "auto"}, context)
        with pytest.raises(ProviderFailure) as error:
            await c.tools.execute("web.search", request, context)
        assert error.value.category == "disabled"
        events = await db.all("SELECT outcome FROM audit_events WHERE owner=%s ORDER BY id", (owner,))
        assert [e["outcome"] for e in events] == ["denied:scopes", "denied:schema", "intent", "failed"]
