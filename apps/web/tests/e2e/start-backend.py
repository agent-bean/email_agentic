"""Real API for browser tests, isolated from credentials, workers and customer data."""
import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
import uvicorn
from psycopg.conninfo import conninfo_to_dict

from email_agentic.agents.contracts import Draft
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.main import create_app
from email_agentic.platform.config import Settings


def settings():
    dsn = os.environ.get("TEST_DATABASE_URL", "")
    parameters = conninfo_to_dict(dsn)
    if parameters.get("dbname") != "email_agentic_test" or parameters.get("host") not in {
        "127.0.0.1", "localhost", "::1",
    }:
        raise SystemExit("Browser tests require a migrated, backed-up local email_agentic_test database")
    # Settings' environment source must not import the user's provider credentials.
    for name, field in Settings.model_fields.items():
        for key in tuple(os.environ):
            if key.casefold() == (field.alias or name).casefold():
                os.environ.pop(key)
    return Settings(
        _env_file=None, APP_ENV="local", DATABASE_URL=dsn,
        GOOGLE_TEST_ACCOUNT_EMAIL=f"web-e2e-{uuid.uuid4()}@example.invalid",
        app_origin="http://127.0.0.1:5173", google_oauth_token_file=Path('/nonexistent/e2e-token.json'),
        duckduckgo_enabled=False, scheduler_enabled=False,
        email_automation_enabled=False, calendar_automation_enabled=False,
    )


async def seed_review(config, viewport):
    # Explicit fixture: exercises review/versioning, not LLM output quality.
    async with build_container(config) as c:
        run_id = await c.research.create(config.owner_email, ResearchRequest(
            company_name=f"Browser review fixture {viewport}", domain="example.org",
            context="Test fixture for approval and version safety",
        ), str(uuid.uuid4()))
        run = await c.research.get(config.owner_email, run_id)
        await c.reports.initial(run, Draft(
            markdown="# Báo cáo kiểm thử\n\nNội dung nội bộ để kiểm thử quy trình duyệt.",
            email_subject="Trao đổi nhu cầu", email_body="Chào anh/chị, xin xác nhận nhu cầu trao đổi.",
        ), {"factual_accuracy": "requires_review", "completeness": "not_evaluated"})
        await c.research.status(run_id, "draft_ready")


def cleanup(config):
    # Delete only this test server's unique owner; no production data is reachable.
    with psycopg.connect(config.dsn) as connection:
        owner = (config.owner_email,)
        connection.execute("DELETE FROM publication_actions WHERE approval_id IN "
                           "(SELECT id FROM approvals WHERE owner=%s)", owner)
        for table in ("gmail_drafts", "report_files", "knowledge", "approvals", "reports", "jobs"):
            connection.execute(f"DELETE FROM {table} WHERE owner=%s", owner)
        connection.execute("DELETE FROM research_runs WHERE owner=%s", owner)


if __name__ == "__main__":
    config = settings()
    try:
        for viewport in ("desktop", "tablet", "mobile"):
            asyncio.run(seed_review(config, viewport))
        app = create_app(config)
        application_lifespan = app.router.lifespan_context

        @asynccontextmanager
        async def test_lifespan(application):
            try:
                async with application_lifespan(application):
                    yield
            finally:
                # Uvicorn re-raises SIGTERM after lifespan shutdown, before outer finally.
                await asyncio.to_thread(cleanup, config)

        app.router.lifespan_context = test_lifespan
        uvicorn.run(app, host="127.0.0.1", port=18000, log_level="warning")
    finally:
        cleanup(config)
