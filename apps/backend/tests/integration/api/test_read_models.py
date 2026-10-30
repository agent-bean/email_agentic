from contextlib import asynccontextmanager
from types import SimpleNamespace
import uuid

import httpx
import pytest

from email_agentic.api.queries import WorkspaceQueries
from email_agentic.bootstrap import build_container
from email_agentic.main import create_app
from email_agentic.models.agents import Draft
from email_agentic.models.reports import ReportEdit
from email_agentic.models.research import ResearchRequest
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import NotFound


async def test_detail_reads_one_snapshot_during_concurrent_edit(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Snapshot", domain="example.com"), str(uuid.uuid4())
        )
        run = await c.research.get(owner, run_id)
        first = await c.reports.initial(
            run, Draft(markdown="Original", email_subject="Subject", email_body="Body"), {}
        )

        @asynccontextmanager
        async def transaction():
            async with db.transaction() as connection:
                async def execute(sql, params=()):
                    cursor = await connection.execute(sql, params)
                    if sql.startswith("SELECT * FROM research_runs"):
                        # Commit on a separate real connection between projection queries.
                        await c.reports.edit(owner, run_id, ReportEdit(
                            version=1, markdown="Changed", email_subject="Subject", email_body="Body"
                        ))
                    return cursor
                yield SimpleNamespace(execute=execute)

        result = await WorkspaceQueries(SimpleNamespace(transaction=transaction)).run_detail(owner, run_id, False)
        assert result["reports"][0]["id"] == first
        assert result["approvals"][0]["status"] == "pending"
        latest = await WorkspaceQueries(db).run_detail(owner, run_id, False)
        assert latest["reports"][0]["version"] == 2
        with pytest.raises(NotFound):
            await WorkspaceQueries(db).run_detail("other@example.invalid", run_id, False)


async def test_input_contract_preserves_failed_expired_and_provider_metadata(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(APP_ENV="local", DATABASE_URL=db.pool.conninfo,
                        GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None)
    async with build_container(settings) as c:
        await c.inbox.save(owner, "google", "failed", "email", {"id": "failed", "status": "read_failed"})
        await c.inbox.save(owner, "google", "expired", "email", {"status": "expired"})
        await c.inbox.save(owner, "google", "meeting", "meeting", {
            "id": "meeting", "summary": "Review", "status": "confirmed", "etag": "provider-version",
            "start": {"dateTime": "2030-01-01T10:00:00+07:00", "timeZone": "Asia/Bangkok"},
        })
        app = create_app(settings)
        app.state.container = c
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
            response = await client.get("/api/v1/inputs")
            assert response.status_code == 200
            rows = {row["source_id"]: row for row in response.json()}
            assert rows["failed"]["content"]["status"] == "read_failed"
            assert rows["expired"]["content"]["status"] == "expired"
            assert rows["meeting"]["kind"] == "meeting"
            assert rows["meeting"]["content"]["etag"] == "provider-version"
            assert rows["meeting"]["content"]["start"]["timeZone"] == "Asia/Bangkok"
            for path in ("/companies", "/knowledge", "/system", "/me"):
                assert (await client.get("/api/v1" + path)).status_code == 200


async def test_detail_includes_blocked_gmail_draft(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(APP_ENV="local", DATABASE_URL=db.pool.conninfo,
                        GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None)
    async with build_container(settings) as c:
        run_id = await c.research.create(
            owner, ResearchRequest(company_name="Blocked draft", domain="example.com"), str(uuid.uuid4())
        )
        report_id = await c.reports.initial(
            await c.research.get(owner, run_id),
            Draft(markdown="Report", email_subject="Subject", email_body="Body"), {},
        )
        draft_id = uuid.uuid4()
        await db.execute(
            """INSERT INTO gmail_drafts(id,run_id,report_id,owner,status,correlation_id)
            VALUES(%s,%s,%s,%s,'blocked',%s)""",
            (draft_id, run_id, report_id, owner, f"<{draft_id}@email-agentic.invalid>"),
        )
        app = create_app(settings)
        app.state.container = c
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
            response = await client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["gmail_drafts"][0]["status"] == "blocked"
