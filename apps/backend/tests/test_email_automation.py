import base64
import json
import uuid
from datetime import datetime, UTC, timedelta
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest

from email_agentic.bootstrap import build_container
from email_agentic.domains.inbox.automation import automated, queue_intake
from email_agentic.domains.inbox.sync import GmailSync
from email_agentic.integrations.email_message import decode_message
from email_agentic.integrations.google import Google
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure, NotFound, Conflict


def raw_email():
    message = EmailMessage()
    message['From'] = 'Partner <partner@gmail.com>'
    message['To'] = 'owner@example.org'
    message['Subject'] = 'Cooperation with Example'
    message['Message-ID'] = '<partner-message@example.org>'
    message.set_content('I represent Example. Could we discuss our integration project?')
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def response_message():
    return {'raw': raw_email(), 'threadId': 'thread', 'internalDate': '1793257200000', 'labelIds': ['INBOX']}


async def test_gmail_sync_history_pagination_keeps_start_until_last_page():
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'owner@example.org', 'historyId': '900'})
        if request.url.path.endswith('/history'):
            assert request.url.params['startHistoryId'] == '100'
            if request.url.params.get('pageToken') == 'next':
                return httpx.Response(200, json={'historyId': '950'})
            return httpx.Response(200, json={'historyId': '900', 'nextPageToken': 'next', 'history': [
                {'messagesAdded': [{'message': {'id': 'new'}}]},
                {'labelsAdded': [{'message': {'id': 'new'}, 'labelIds': ['INBOX']}]},
                {'messagesAdded': [{'message': {'id': 'sent', 'labelIds': ['SENT']}}]},
            ]})
        assert request.url.path.endswith('/new')
        return httpx.Response(200, json=response_message())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'test-only'
        rows, cursor, more = await google.sync_inbox({'mode': 'history', 'history_id': '100'})
        assert len(rows) == 1 and more and cursor['history_id'] == '100'
        assert rows[0]['body'].startswith('I represent Example')
        assert cursor['page_token'] == 'next'
        rows, cursor, more = await google.sync_inbox(cursor)
        assert not rows and not more and cursor == {'mode': 'history', 'history_id': '950'}


async def test_gmail_sync_expired_cursor_reads_all_inbox_pages_before_history():
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'owner@example.org', 'historyId': '500'})
        if request.url.path.endswith('/history'):
            return httpx.Response(404, json={})
        assert request.url.path.endswith('/messages')
        if request.url.params.get('pageToken') == 'older':
            return httpx.Response(200, json={})
        return httpx.Response(200, json={'messages': [{'id': 'known'}], 'nextPageToken': 'older'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'test-only'
        rows, cursor, more = await google.sync_inbox({'mode': 'history', 'history_id': '1'}, {'known'})
        assert rows == [] and more and cursor == {'mode': 'full', 'history_id': '500', 'page_token': 'older'}
        rows, cursor, more = await google.sync_inbox(cursor, {'known'})
        assert not more and cursor == {'mode': 'history', 'history_id': '500'}


async def test_gmail_sync_refuses_wrong_mailbox():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={'emailAddress': 'other@example.org', 'historyId': '500'}))) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'test-only'
        with pytest.raises(ProviderFailure) as error:
            await google.sync_inbox(None)
        assert error.value.category == 'mailbox_mismatch'


async def test_gmail_sync_does_not_commit_cursor_or_intake_when_provider_fails(db):
    owner = f'{uuid.uuid4()}@example.org'
    source_id = str(uuid.uuid4())
    fail = True
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': owner, 'historyId': '500'})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': source_id}]})
        if request.url.path.endswith('/history'):
            return httpx.Response(200, json={'historyId': '501'})
        if fail:
            return httpx.Response(503, json={})
        return httpx.Response(200, json=response_message())
    settings = Settings(APP_ENV='test', GOOGLE_TEST_ACCOUNT_EMAIL=owner, EMAIL_AUTOMATION_ENABLED=True,
                        EMAIL_AUTOMATION_START_AT='2020-01-01T00:00:00Z', _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, settings)
        google.token = lambda: 'test-only'
        sync = GmailSync(db, google, settings)
        with pytest.raises(ProviderFailure):
            await sync.run(owner)
        assert not await db.one('SELECT * FROM sync_cursors WHERE owner=%s', (owner,))
        assert not await db.one('SELECT * FROM inputs WHERE owner=%s', (owner,))
        fail = False
        await sync.run(owner)
        await sync.run(owner)
    inputs = await db.all('SELECT id FROM inputs WHERE owner=%s', (owner,))
    assert len(inputs) == 1
    assert len(await db.all("SELECT * FROM jobs WHERE owner=%s AND kind='email_intake'", (owner,))) == 1
    assert json.loads((await db.one('SELECT cursor FROM sync_cursors WHERE owner=%s', (owner,)))['cursor'])['history_id'] == '501'


async def test_email_automation_creates_one_unconfirmed_run_and_tracks_usage(db):
    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, GOOGLE_TEST_ACCOUNT_EMAIL=owner,
                        EMAIL_AUTOMATION_ENABLED=True, EMAIL_AUTOMATION_START_AT='2020-01-01T00:00:00Z',
                        LLM_BASE_URL='https://example.org/v1', LLM_MODEL='test', LLM_API_KEY='test-only', _env_file=None)
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({
            'disposition': 'business', 'company_name': 'Example', 'domain': 'example.org', 'reason': 'business_request',
        })}}], 'usage': {'prompt_tokens': 20, 'completion_tokens': 10}})
    async with build_container(settings) as c, httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        c.llm.client = client
        source = await decode_message(base64.urlsafe_b64decode(raw_email()), str(uuid.uuid4()), 'thread')
        source['received_at'] = datetime.now(UTC).isoformat()
        await c.inbox.save(owner, 'google', source['id'], 'email', source)
        row = await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,))
        async with db.transaction() as connection:
            await queue_intake(connection, owner, row['id'])
            await queue_intake(connection, owner, row['id'])
        with pytest.raises(NotFound):
            await c.email_automation.run('other@example.org', row['id'])
        await c.email_automation.run(owner, row['id'])
        await c.email_automation.run(owner, row['id'])
        assert len(calls) == 1
        run = await db.one('SELECT * FROM research_runs WHERE owner=%s', (owner,))
        assert not run['identity_confirmed'] and run['source_email'] == source['source_text']
        assert run['source_message']['thread_id'] == 'thread'
        usage = await db.one('SELECT * FROM model_usage WHERE input_id=%s', (row['id'],))
        assert usage['run_id'] is None and usage['input_tokens'] == 20
        assert len(await db.all("SELECT * FROM jobs WHERE owner=%s AND kind='research'", (owner,))) == 1
        assert not await db.one('SELECT * FROM reports WHERE run_id=%s', (run['id'],))
        assert not await db.one('SELECT * FROM publication_actions WHERE approval_id IN (SELECT id FROM approvals WHERE owner=%s)', (owner,))
        await c.research.status(run['id'], 'awaiting_identity')
        with pytest.raises(NotFound):
            await c.approvals.confirm_identity('other@example.org', run['id'], 1, 'Correct', 'correct.org')
        await c.approvals.confirm_identity(owner, run['id'], 1, 'Correct', 'correct.org')
        confirmed = await c.research.get(owner, run['id'])
        assert confirmed['company_name'] == 'Correct' and confirmed['domain'] == 'correct.org'
        assert confirmed['identity_confirmed'] and confirmed['version'] == 2
        with pytest.raises(Conflict):
            await c.approvals.confirm_identity(owner, run['id'], 1, 'Changed', 'changed.org')


@pytest.mark.parametrize('headers', [
    {'From': 'Owner <owner@example.org>'}, {'From': 'noreply@notify.cloudflare.com'},
    {'From': 'notifications@github.com'}, {'Auto-Submitted': 'auto-generated'}, {'List-Id': 'newsletter'},
])
def test_email_automation_skips_machine_and_own_mail(headers):
    assert automated({'headers': headers}, 'owner@example.org')


def test_email_automation_requires_explicit_timezone_start():
    with pytest.raises(ValueError):
        Settings(APP_ENV='test', EMAIL_AUTOMATION_ENABLED=True, _env_file=None)
    with pytest.raises(ValueError):
        Settings(APP_ENV='test', EMAIL_AUTOMATION_ENABLED=True,
                 EMAIL_AUTOMATION_START_AT=datetime.now(UTC).replace(tzinfo=None), _env_file=None)
    settings = Settings(APP_ENV='test', EMAIL_AUTOMATION_ENABLED=True,
                        EMAIL_AUTOMATION_START_AT=datetime.now(UTC) - timedelta(days=1), _env_file=None)
    assert settings.email_automation_enabled


async def test_gmail_sync_transaction_rolls_back_inputs_when_intake_queue_fails(db, monkeypatch):
    owner = f'{uuid.uuid4()}@example.org'
    source_id = str(uuid.uuid4())
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': owner, 'historyId': '500'})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': source_id}], 'nextPageToken': 'next'})
        return httpx.Response(200, json=response_message())
    async def fail_queue(*args):
        raise RuntimeError('Interrupted before cursor commit')
    monkeypatch.setattr('email_agentic.domains.inbox.sync.queue_intake', fail_queue)
    settings = Settings(APP_ENV='test', GOOGLE_TEST_ACCOUNT_EMAIL=owner, EMAIL_AUTOMATION_ENABLED=True,
                        EMAIL_AUTOMATION_START_AT='2020-01-01T00:00:00Z', _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, settings)
        google.token = lambda: 'test-only'
        with pytest.raises(RuntimeError, match='Interrupted'):
            await GmailSync(db, google, settings).run(owner)
    assert not await db.one('SELECT * FROM inputs WHERE owner=%s', (owner,))
    assert not await db.one('SELECT * FROM sync_cursors WHERE owner=%s', (owner,))
    assert not await db.one('SELECT * FROM jobs WHERE owner=%s', (owner,))


async def test_gmail_sync_queues_next_page_and_old_mail_does_not_trigger_intake(db):
    owner = f'{uuid.uuid4()}@example.org'
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': owner, 'historyId': '500'})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': 'old'}], 'nextPageToken': 'next'})
        return httpx.Response(200, json=response_message())
    settings = Settings(APP_ENV='test', GOOGLE_TEST_ACCOUNT_EMAIL=owner, EMAIL_AUTOMATION_ENABLED=True,
                        EMAIL_AUTOMATION_START_AT='2030-01-01T00:00:00Z', _env_file=None)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, settings)
        google.token = lambda: 'test-only'
        await GmailSync(db, google, settings).run(owner)
    jobs = await db.all('SELECT * FROM jobs WHERE owner=%s', (owner,))
    assert len(jobs) == 1 and jobs[0]['kind'] == 'scan_email'
    assert json.loads((await db.one('SELECT cursor FROM sync_cursors WHERE owner=%s', (owner,)))['cursor'])['page_token'] == 'next'
    assert not await db.one('SELECT * FROM email_triage WHERE owner=%s', (owner,))


async def test_email_automation_disabled_preserves_pending_intake_jobs(db):
    from email_agentic.runtime.jobs import Jobs, enqueue
    owner = f'{uuid.uuid4()}@example.org'
    async with db.transaction() as connection:
        await enqueue(connection, owner, 'email_intake', uuid.uuid4(), f'intake-toggle:{owner}')
    assert await Jobs(db).claim(['email_intake'], excluded=('email_intake',)) is None
    row = await db.one('SELECT status,attempt FROM jobs WHERE owner=%s', (owner,))
    assert row == {'status': 'pending', 'attempt': 0}
