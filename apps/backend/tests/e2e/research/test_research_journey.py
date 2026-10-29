"""Public API journey against real application services and isolated PostgreSQL."""
import uuid

import httpx

from email_agentic.main import create_app
from email_agentic.platform.config import Settings


async def test_owner_creates_and_reopens_one_research_request(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(
        APP_ENV="local", DATABASE_URL=db.pool.conninfo,
        GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
            assert (await client.get("/health/ready")).status_code == 200
            assert (await client.get("/api/v1/me")).json()["email"] == owner
            headers = {"Origin": "http://127.0.0.1:8000", "Idempotency-Key": str(uuid.uuid4())}
            payload = {
                "company_name": "Research journey", "domain": "example.com",
                "context": "Prepare a meeting", "source_email": "Please discuss our requirements.",
            }
            created = await client.post("/api/v1/runs", json=payload, headers=headers)
            assert created.status_code == 202
            run_id = created.json()["id"]
            repeated = await client.post("/api/v1/runs", json=payload, headers=headers)
            assert repeated.status_code == 202
            assert repeated.json()["id"] == run_id
            listing = await client.get("/api/v1/runs")
            assert listing.status_code == 200
            assert [row["id"] for row in listing.json()] == [run_id]
            reopened = await client.get(f"/api/v1/runs/{run_id}")
            assert reopened.status_code == 200
            detail = reopened.json()
            assert detail["run"]["source_email"] == payload["source_email"]
            assert detail["run"]["context"] == payload["context"]
            assert detail["run"]["status"] == "queued"
            assert detail["reports"] == detail["approvals"] == detail["actions"] == []
