import base64
import io
import json
import uuid
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfWriter

from email_agentic.agents.contracts import Draft
from email_agentic.agents.report_generation import ReportGenerationAgent
from email_agentic.bootstrap import build_container
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.integrations.email_message import decode_message
from email_agentic.integrations.google import Google
from email_agentic.integrations.pdf import read_pdf
from email_agentic.platform.config import Settings
from email_agentic.platform.errors import Conflict, NotFound, ToolDenied
from email_agentic.tools.harness import ToolContext


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


async def test_mime_body_and_attachment_stay_separate_and_html_is_inert():
    msg = message()
    msg.add_alternative('<p>Alternative</p><script>never run</script>', subtype='html')
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    msg.add_attachment(output.getvalue(), maintype='application', subtype='pdf', filename='profile.pdf')
    parsed = await decode_message(msg.as_bytes(), 'mail-1', 'thread-1')
    assert parsed['body'] == '  Nội dung gốc.\n[DỮ LIỆU MẪU] stays literal.\n'
    assert parsed['headers']['Reply-To'] == 'reply@example.org'
    assert parsed['attachments'][0]['extraction']['status'] == 'no_text'
    assert 'profile.pdf' not in parsed['source_text']
    html = EmailMessage()
    html.set_content('<p>Hello</p><script>bad()</script><style>hidden</style><p>World</p>', subtype='html')
    source = await decode_message(html.as_bytes(), 'html', 'thread')
    assert 'Hello' in source['body'] and 'World' in source['body']
    assert 'bad()' not in source['body'] and 'hidden' not in source['body']
    assert source['html'] and source['body_format'] == 'html'


async def test_pdf_invalid_encrypted_and_size_limits_are_explicit():
    assert (await read_pdf(b'not PDF'))['status'] == 'invalid_pdf'
    assert (await read_pdf(b'x' * (10 * 1024 * 1024 + 1)))['status'] == 'too_large'
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt('password')
    output = io.BytesIO()
    writer.write(output)
    assert (await read_pdf(output.getvalue()))['status'] == 'encrypted'


def test_pdf_reports_truncation_when_one_page_exceeds_text_budget(monkeypatch):
    from email_agentic.integrations.pdf import extract, MAX_TEXT

    monkeypatch.setattr('pypdf.PdfReader', lambda stream: SimpleNamespace(
        is_encrypted=False, pages=[SimpleNamespace(extract_text=lambda: 'x' * (MAX_TEXT + 1))]))
    result = extract(b'bounded-page')
    assert result['status'] == 'succeeded'
    assert len(result['text']) == MAX_TEXT and result['truncated'] is True
    assert result['pages_read'] == result['pages'] == 1


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


async def test_import_ownership_snapshot_deduplication_and_draft_version(db):
    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        source = await decode_message(message().as_bytes(), 'mail-' + str(uuid.uuid4()), 'thread-1')
        await c.inbox.save(owner, 'google', source['id'], 'email', source)
        row = await db.one('SELECT * FROM inputs WHERE owner=%s', (owner,))
        request = ResearchRequest(company_name='Company', domain='example.org', source_input_id=row['id'])
        with pytest.raises(NotFound):
            await c.research.create('other@example.org', request, str(uuid.uuid4()))
        run_id = await c.research.create(owner, request, str(uuid.uuid4()))
        assert await c.research.create(owner, request, str(uuid.uuid4())) == run_id
        run = await c.research.get(owner, run_id)
        assert run['source_email'] == source['source_text']
        assert run['source_message']['thread_id'] == 'thread-1'
        changed = {**source, 'source_text': 'changed after import'}
        await c.inbox.save(owner, 'google', source['id'], 'email', changed)
        assert (await c.research.get(owner, run_id))['source_email'] == source['source_text']
        draft = Draft(markdown='Internal research', email_subject='Model subject', email_body='Cảm ơn anh/chị.')
        await c.reports.initial(run, draft, {})
        report = await c.reports.latest(owner, run_id)
        assert report['email_subject'] == 'Re: Trao đổi AI'
        assert report['recipients']['to'] == ['reply@example.org']
        assert not report['send_email'] and not report['save_kb']
        with pytest.raises(NotFound):
            await c.drafts.request('other@example.org', run_id, 1)
        with pytest.raises(Conflict):
            await c.drafts.request(owner, run_id, 2)
        draft_id = await c.drafts.request(owner, run_id, 1)
        assert await c.drafts.request(owner, run_id, 1) == draft_id
        assert len(await db.all("SELECT * FROM jobs WHERE kind='gmail_draft' AND entity_id=%s", (draft_id,))) == 1
        assert not await c.drafts.authorized('other@example.org', draft_id)
        assert await c.drafts.authorized(owner, draft_id)
        await c.drafts.package(owner, draft_id)
        assert (await c.drafts.package(owner, draft_id))['reconcile_only']
        await c.drafts.complete(draft_id, 'unknown')
        assert (await c.drafts.package(owner, draft_id))['reconcile_only']
        await c.drafts.complete(draft_id, 'succeeded', 'provider-draft', 'thread-1')
        assert await c.drafts.package(owner, draft_id) is None
        assert await db.one('SELECT id FROM publication_actions WHERE approval_id IN (SELECT id FROM approvals WHERE report_id=%s)', (report['id'],)) is None
        assert not await c.drafts.authorized(owner, uuid.uuid4())
        context = ToolContext(owner, 'web', frozenset({'web:read'}))
        with pytest.raises(ToolDenied, match="scopes"):
            await c.tools.execute('email.draft', {'action_id': str(draft_id)}, context)


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


async def test_draft_is_blocked_if_report_changed_and_unknown_retry_does_not_reset_budget(db):
    from email_agentic.domains.reports.service import ReportEdit

    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='test', DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        source = await decode_message(message().as_bytes(), 'mail-' + str(uuid.uuid4()), 'thread-2')
        await c.inbox.save(owner, 'google', source['id'], 'email', source)
        row = await db.one('SELECT id FROM inputs WHERE owner=%s', (owner,))
        run_id = await c.research.create(owner, ResearchRequest(company_name='Company', domain='example.org', source_input_id=row['id']), str(uuid.uuid4()))
        run = await c.research.get(owner, run_id)
        await c.reports.initial(run, Draft(markdown='Brief', email_subject='Hello', email_body='Reply'), {})
        report = await c.reports.latest(owner, run_id)
        pending = await c.drafts.request(owner, run_id, 1)
        edit = ReportEdit(version=1, markdown=report['markdown'], email_subject=report['email_subject'], email_body='Edited reply', recipients=report['recipients'])
        await c.reports.edit(owner, run_id, edit)
        assert await c.drafts.package(owner, pending) is None
        assert (await db.one('SELECT status FROM gmail_drafts WHERE id=%s', (pending,)))['status'] == 'blocked'
        current = await c.drafts.request(owner, run_id, 2)
        await c.drafts.complete(current, 'unknown')
        await db.execute("UPDATE jobs SET status='done',attempt=2 WHERE entity_id=%s AND kind='gmail_draft'", (current,))
        assert await c.drafts.request(owner, run_id, 2) == current
        job = await db.one("SELECT status,attempt FROM jobs WHERE entity_id=%s AND kind='gmail_draft'", (current,))
        assert job['status'] == 'pending' and job['attempt'] == 2
        assert (await c.drafts.package(owner, current))['reconcile_only']
        await c.drafts.complete(current, 'unknown')
        await db.execute("UPDATE jobs SET status='done',attempt=3 WHERE entity_id=%s AND kind='gmail_draft'", (current,))
        with pytest.raises(Conflict, match='ba lần'):
            await c.drafts.request(owner, run_id, 2)


async def test_missing_compose_scope_rejects_export_without_creating_job(db, tmp_path):
    from email_agentic.main import create_app

    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='local', DATABASE_URL=db.pool.conninfo, GOOGLE_TEST_ACCOUNT_EMAIL=owner,
                        google_oauth_token_file=tmp_path / 'missing-token.json', _env_file=None)
    async with build_container(settings) as c:
        app = create_app(settings)
        app.state.container = c
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 4321)), base_url='http://127.0.0.1:8000') as client:
            result = await client.post(f'/api/v1/runs/{uuid.uuid4()}/gmail-draft', json={'version': 1}, headers={'Origin': 'http://127.0.0.1:8000'})
            assert result.status_code == 409 and 'gmail.compose' in result.json()['detail']
        assert not await db.one("SELECT id FROM jobs WHERE owner=%s AND kind='gmail_draft'", (owner,))
