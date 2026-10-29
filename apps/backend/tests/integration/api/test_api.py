import uuid

import httpx

from email_agentic.bootstrap import build_container
from email_agentic.main import create_app
from email_agentic.platform.config import Settings


async def test_api_uses_verified_owner_and_checks_origin(db):
    owner = f"{uuid.uuid4()}@example.invalid"
    settings = Settings(
        APP_ENV="local", DATABASE_URL=db.pool.conninfo, GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None
    )
    async with build_container(settings) as c:
        app = create_app(settings)
        app.state.container = c
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
            payload = {"company_name": "API boundary test", "domain": "example.com"}
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            assert (await client.post("/api/v1/runs", json=payload, headers=headers)).status_code == 403
            headers["Origin"] = "http://127.0.0.1:8000"
            forged = await client.post(
                "/api/v1/runs", json={**payload, "owner": "forged@example.invalid"}, headers=headers
            )
            assert forged.status_code == 422
            valid = await client.post("/api/v1/runs", json=payload, headers=headers)
            assert valid.status_code == 202
            assert (await c.research.get(owner, valid.json()["id"]))["owner"] == owner
        remote = httpx.ASGITransport(app=app, client=("203.0.113.1", 12345))
        async with httpx.AsyncClient(transport=remote, base_url="http://127.0.0.1:8000") as client:
            assert (await client.get("/api/v1/runs")).status_code == 403


async def test_identity_correction_api_validates_domain_and_keeps_version_guard(db):
    from email_agentic.domains.research.service import ResearchRequest
    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='local', DATABASE_URL=db.pool.conninfo,
                        GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None)
    async with build_container(settings) as c:
        app = create_app(settings)
        app.state.container = c
        run_id = await c.research.create(owner, ResearchRequest(company_name='Proposal', domain='example.org'), str(uuid.uuid4()))
        await c.research.status(run_id, 'awaiting_identity')
        transport = httpx.ASGITransport(app=app, client=('127.0.0.1', 12345))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1:8000') as client:
            headers = {'Origin': 'http://127.0.0.1:8000'}
            path = f'/api/v1/runs/{run_id}/identity'
            for payload in [
                {'version': 1, 'company_name': 'Correct'},
                {'version': 1, 'company_name': 'Correct', 'domain': 'https://example.org'},
                {'version': 1, 'company_name': 'Correct', 'domain': 'example.org', 'owner': 'other@example.org'},
            ]:
                assert (await client.post(path, json=payload, headers=headers)).status_code == 422
            payload = {'version': 1, 'company_name': 'Correct', 'domain': 'correct.org'}
            assert (await client.post(path, json=payload, headers=headers)).status_code == 202
            assert (await client.post(path, json=payload, headers=headers)).status_code == 409
            result = (await client.get(f'/api/v1/runs/{run_id}')).json()['run']
            assert result['company_name'] == 'Correct' and result['domain'] == 'correct.org'
