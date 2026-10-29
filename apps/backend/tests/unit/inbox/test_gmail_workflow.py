import base64
import json
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from types import SimpleNamespace

import httpx

from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.integrations.email_message import decode_message
from email_agentic.integrations.google import Google


def message():
    msg = EmailMessage()
    msg['From'] = 'Customer <customer@example.org>'
    msg['To'] = 'owner@example.org'
    msg['Reply-To'] = 'reply@example.org'
    msg['Subject'] = 'Trao đổi AI'
    msg['Message-ID'] = '<source@example.org>'
    msg['References'] = '<earlier@example.org>'
    msg.set_content('  Nội dung gốc.\n[DỮ LIỆU MẪU] stays literal.\n')
    return msg


async def test_gmail_draft_mime_keeps_thread_headers_and_never_calls_send():
    source = await decode_message(message().as_bytes(), 'mail-1', 'thread-1')
    report = {'email_subject': 'Re: Trao đổi AI', 'email_body': 'Cảm ơn anh/chị.',
              'recipients': {'to': ['reply@example.org']}, 'source_message': source,
              'correlation_id': '<draft@example.org>'}
    def transport(request):
        assert request.url.path.endswith('/drafts')
        assert request.method == 'POST'
        body = json.loads(request.content)['message']
        assert body['threadId'] == 'thread-1'
        mime = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(body['raw']))
        assert mime['In-Reply-To'] == '<source@example.org>'
        assert mime['References'] == '<earlier@example.org> <source@example.org>'
        assert mime['To'] == 'reply@example.org'
        assert mime['Subject'] == 'Re: Trao đổi AI'
        assert mime['Message-ID'] == '<draft@example.org>'
        return httpx.Response(200, json={'id': 'draft-1', 'message': {'threadId': 'thread-1'}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'unit-test-only'
        assert (await google.create_draft(report))['id'] == 'draft-1'


async def test_attachment_context_is_not_truncated_into_email_or_external_queries():
    class Capture:
        async def structured(self, run_id, schema, system, payload):
            data = json.loads(payload)
            assert data['source_email'] == 'Customer request'
            assert data['attachments'][0]['extraction']['text'].endswith('END')
            assert 'untrusted' in system
    await ReportGenerationAgent(Capture()).run(
        {'id': 'run', 'company_name': 'Company', 'domain': 'example.org', 'context': '',
         'source_email': 'Customer request', 'source_message': {'attachments': [
             {'filename': 'profile.pdf', 'extraction': {'status': 'succeeded', 'text': 'x' * 10000 + 'END'}}]}},
        [], [])


async def test_recent_sync_skips_imported_mail_and_keeps_results_when_one_mail_is_denied():
    raw = base64.urlsafe_b64encode(message().as_bytes()).decode()
    paths = []
    def transport(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/messages'):
            assert request.url.params['maxResults'] == '50'
            return httpx.Response(200, json={'messages': [{'id': 'known'}, {'id': 'new'}, {'id': 'denied'}], 'nextPageToken': 'older'})
        if request.url.path.endswith('/denied'):
            return httpx.Response(403, json={'error': 'denied'})
        assert request.url.path.endswith('/new')
        return httpx.Response(200, json={'raw': raw, 'threadId': 'thread-1'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email='owner@example.org'))
        google.token = lambda: 'unit-test-only'
        items = await google.inbox({'known'})
    assert [x['id'] for x in items] == ['new', 'denied']
    assert items[0]['body'].startswith('  Nội dung gốc.')
    assert items[1]['status'] == 'read_failed'
    assert len(paths) == 3


def test_draft_capability_requires_compose_not_send_scope(tmp_path):
    path = tmp_path / 'token.json'
    google = Google(None, SimpleNamespace(google_token_path=path))
    assert not google.drafts_available
    path.write_text(json.dumps({'scopes': ['https://www.googleapis.com/auth/gmail.send']}))
    assert not google.drafts_available
    path.write_text(json.dumps({'scopes': ['https://www.googleapis.com/auth/gmail.compose']}))
    assert google.drafts_available
