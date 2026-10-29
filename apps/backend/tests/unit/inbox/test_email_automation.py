import base64
from datetime import datetime, UTC, timedelta
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest

from email_agentic.domains.inbox.automation import automated
from email_agentic.integrations.google import Google
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import ProviderFailure


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


@pytest.mark.parametrize('reason,retry', [('userRateLimitExceeded', True), ('rateLimitExceeded', True), ('forbidden', False)])
async def test_gmail_sync_distinguishes_rate_limits_from_unreadable_message(reason, retry):
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'owner@example.org', 'historyId': '500'})
        if request.url.path.endswith('/messages'):
            return httpx.Response(200, json={'messages': [{'id': 'denied'}, {'id': 'readable'}]})
        if request.url.path.endswith('/denied'):
            return httpx.Response(403, json={'error': {'errors': [{'reason': reason}]}})
        return httpx.Response(200, json=response_message())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'test-only'
        if retry:
            with pytest.raises(ProviderFailure) as error:
                await google.sync_inbox(None)
            assert error.value.transient is True
        else:
            rows, cursor, more = await google.sync_inbox(None)
            assert rows[0]['status'] == 'read_failed' and rows[1]['status'] == 'succeeded'
            assert not more and cursor['mode'] == 'history'


async def test_gmail_sync_retries_failed_message_even_without_new_history():
    def respond(request):
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'owner@example.org', 'historyId': '500'})
        if request.url.path.endswith('/history'):
            return httpx.Response(200, json={'historyId': '501'})
        assert request.url.path.endswith('/retry')
        return httpx.Response(200, json=response_message())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'test-only'
        rows, _, _ = await google.sync_inbox({'mode': 'history', 'history_id': '500'}, retry_ids=['retry'])
        assert len(rows) == 1 and rows[0]['status'] == 'succeeded'
