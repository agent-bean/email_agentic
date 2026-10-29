"""Offline real OCR and Gmail receipt contract tests; never contact a mailbox."""
import base64
import io
import shutil
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from email_agentic.integrations.google import Google
from email_agentic.integrations.pdf import read_pdf, extract, MAX_OCR_PAGES
from email_agentic.platform.errors import ProviderFailure


def image_pdf():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new('RGB', (1200, 400), 'white')
    ImageDraw.Draw(image).text((60, 100), 'Customer export revenue 2026', fill='black',
                              font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 54))
    output = io.BytesIO()
    image.save(output, format='PDF', resolution=150)
    return output.getvalue()


def text_page(writer):
    page = writer.add_blank_page(width=400, height=200)
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
    stream = DecodedStreamObject()
    stream.set_data(b'BT /F1 20 Tf 20 100 Td (Original text layer) Tj ET')
    page[NameObject('/Contents')] = writer._add_object(stream)


@pytest.mark.skipif(not shutil.which('tesseract') or not shutil.which('pdftoppm'), reason='requires real OCR tools')
async def test_real_image_ocr_and_mixed_pdf_keep_page_provenance():
    writer = PdfWriter()
    text_page(writer)
    writer.add_page(PdfReader(io.BytesIO(image_pdf())).pages[0])
    output = io.BytesIO()
    writer.write(output)
    result = await read_pdf(output.getvalue())
    assert result['status'] == 'succeeded', result
    assert result['pages_read'] == result['pages'] == 2
    assert result['page_results'][0]['method'] == 'text'
    assert result['page_results'][0]['text'] == 'Original text layer'
    assert result['page_results'][1]['method'] == 'ocr'
    assert 'Customer export revenue 2026' in result['page_results'][1]['text']
    assert not result['truncated']


def test_ocr_absence_preserves_text_and_limit_is_explicit(monkeypatch):
    # Failure-path injection exercises reporting; successful OCR is tested with the real engine above.
    writer = PdfWriter()
    text_page(writer)
    page = PdfReader(io.BytesIO(image_pdf())).pages[0]
    for _ in range(MAX_OCR_PAGES + 1):
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    def unavailable(*args):
        raise FileNotFoundError()
    monkeypatch.setattr('email_agentic.integrations.pdf.ocr_page', unavailable)
    result = extract(output.getvalue())
    assert result['status'] == 'partial' and result['truncated']
    assert result['page_results'][0]['text'] == 'Original text layer'
    assert result['page_results'][1]['status'] == 'ocr_unavailable'
    assert result['page_results'][-1]['status'] == 'ocr_limit_reached'


@pytest.mark.parametrize('outcome', ['matched', 'mismatch', 'not_found', 'multiple_matches', 'wrong_mailbox', 'wrong_thread', 'wrong_recipient', 'missing_sent', 'wrong_correlation', 'wrong_receipt'])
async def test_sent_review_reads_actual_message_and_never_mutates(outcome):
    report = {'owner': 'owner@example.org', 'email_subject': 'Approved subject', 'email_body': 'Approved body',
              'recipients': {'to': ['customer@example.org']}, 'correlation_id': '<approved@example.org>',
              'provider_id': 'sent-1', 'source_message': {'thread_id': 'thread-1', 'headers': {'Message-ID': '<source@example.org>'}}}
    message = EmailMessage()
    message['From'] = report['owner']
    message['To'] = 'other@example.org' if outcome == 'wrong_recipient' else 'customer@example.org'
    message['Subject'] = report['email_subject']
    message['Message-ID'] = '<other@example.org>' if outcome == 'wrong_correlation' else report['correlation_id']
    message['In-Reply-To'] = '<source@example.org>'
    message.set_content('Tampered body' if outcome == 'mismatch' else report['email_body'])
    paths = []
    def transport(request):
        assert request.method == 'GET'
        paths.append(request.url.path)
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'wrong@example.org' if outcome == 'wrong_mailbox' else report['owner']})
        if request.url.path.endswith('/messages'):
            assert request.url.params['q'] == 'in:sent rfc822msgid:approved@example.org'
            return httpx.Response(200, json={'messages': [] if outcome == 'not_found' else
                [{'id': 'sent-1'}, {'id': 'sent-2'}] if outcome == 'multiple_matches' else [{'id': 'sent-1'}]})
        return httpx.Response(200, json={'id': 'other' if outcome == 'wrong_receipt' else 'sent-1', 'threadId': 'other' if outcome == 'wrong_thread' else 'thread-1', 'labelIds': [] if outcome == 'missing_sent' else ['SENT'],
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email=report['owner']))
        google.token = lambda: 'test-only'
        if outcome == 'wrong_mailbox':
            with pytest.raises(ProviderFailure, match='gmail'):
                await google.review_sent(report)
            assert len(paths) == 1
        else:
            assert (await google.review_sent(report))['verification'] == ('mismatch' if outcome.startswith('wrong_') or outcome == 'missing_sent' else outcome)
    assert len(paths) <= 3


async def test_sent_review_owner_scope_and_read_only_receipts(db):
    import uuid
    from email_agentic.agents.contracts import Draft
    from email_agentic.bootstrap import build_container
    from email_agentic.domains.research.service import ResearchRequest
    from email_agentic.domains.reports.service import ReportEdit, Recipients
    from email_agentic.main import create_app
    from email_agentic.platform.config import Settings

    owner = f'{uuid.uuid4()}@example.org'
    settings = Settings(APP_ENV='local', DATABASE_URL=db.pool.conninfo, GOOGLE_TEST_ACCOUNT_EMAIL=owner, _env_file=None)
    async with build_container(settings) as c:
        run_id = await c.research.create(owner, ResearchRequest(company_name='Receipt review', domain='example.org'), str(uuid.uuid4()))
        run = await c.research.get(owner, run_id)
        await c.reports.initial(run, Draft(markdown='Brief', email_subject='Approved', email_body='Body'), {})
        await c.reports.edit(owner, run_id, ReportEdit(version=1, markdown='Brief', email_subject='Approved',
                                                     email_body='Body', recipients=Recipients(to=[owner]), send_email=True))
        report = await c.reports.latest(owner, run_id)
        approval = await db.one('SELECT id FROM approvals WHERE report_id=%s', (report['id'],))
        await c.approvals.decide(owner, approval['id'], True)
        action = await db.one("SELECT * FROM publication_actions WHERE approval_id=%s AND kind='email'", (approval['id'],))
        await c.publication.complete(action['id'], 'unknown', error='timeout')
        before = await db.one('SELECT * FROM publication_actions WHERE id=%s', (action['id'],))
        jobs_before = await db.all('SELECT * FROM jobs WHERE owner=%s ORDER BY id', (owner,))
        paths = []
        def transport(request):
            assert request.method == 'GET'
            paths.append(request.url.path)
            return httpx.Response(200, json={'emailAddress': owner} if request.url.path.endswith('/profile') else {'messages': []})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as google_client:
            c.google.client = google_client
            c.google.token = lambda: 'test-only'
            from email_agentic.platform.errors import NotFound
            with pytest.raises(NotFound):
                await c.publication.sent_review('other@example.org', action['id'], c.google)
            assert paths == []
            app = create_app(settings)
            app.state.container = c
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 4321)), base_url='http://127.0.0.1:8000') as client:
                listing = await client.get('/api/v1/sent-review')
                assert listing.status_code == 200
                assert listing.headers['cache-control'] == 'private, no-store'
                assert listing.json()[0]['email_body'] == 'Body'
                assert listing.json()[0]['version'] == 2
                assert [row['id'] for row in listing.json()] == [str(action['id'])]
                result = await client.get(f"/api/v1/sent-review/{action['id']}")
                assert result.status_code == 200 and result.json()['verification'] == 'not_found'
                assert result.headers['cache-control'] == 'private, no-store'
                assert (await client.get(f'/api/v1/sent-review/{uuid.uuid4()}')).status_code == 404
        assert await db.one('SELECT * FROM publication_actions WHERE id=%s', (action['id'],)) == before
        assert await db.all('SELECT * FROM jobs WHERE owner=%s ORDER BY id', (owner,)) == jobs_before
        await db.execute('UPDATE research_runs SET history_purged_at=now(),source_message=NULL WHERE id=%s', (run_id,))
        paths.clear()
        assert await c.publication.sent_review(owner, action['id'], c.google) == {'verification': 'content_expired', 'provider_id': None}
        assert paths == []
        source_id = 'retained-source-' + str(uuid.uuid4())
        await c.inbox.save(owner, 'google', source_id, 'email', {'id': source_id})
        source = await db.one('SELECT id FROM inputs WHERE owner=%s AND source_id=%s', (owner, source_id))
        await db.execute('UPDATE research_runs SET history_purged_at=NULL,source_input_id=%s WHERE id=%s', (source['id'], run_id))
        assert await c.publication.sent_review(owner, action['id'], c.google) == {'verification': 'content_expired', 'provider_id': None}
        assert paths == []


@pytest.mark.parametrize('cancel', [False, True])
async def test_pdf_parent_removes_private_files_after_timeout_or_cancellation(monkeypatch, cancel):
    import asyncio
    import sys
    from pathlib import Path
    from email_agentic.integrations import pdf

    original_spawn = asyncio.create_subprocess_exec
    original_timeout = asyncio.timeout
    roots = []
    async def spawn(*args, **kwargs):
        roots.append(Path(kwargs['env']['TMPDIR']))
        script = "import os,time;from pathlib import Path;Path(os.environ['TMPDIR'],'private.pdf').write_bytes(b'private');time.sleep(30)"
        return await original_spawn(sys.executable, '-c', script, **kwargs)
    monkeypatch.setattr(pdf.asyncio, 'create_subprocess_exec', spawn)
    if not cancel:
        monkeypatch.setattr(pdf.asyncio, 'timeout', lambda seconds: original_timeout(.3))
    task = asyncio.create_task(pdf.read_pdf(b'private bytes'))
    if cancel:
        async with original_timeout(5):
            while not roots or not (roots[0] / 'private.pdf').exists():
                await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert await task == {'status': 'timeout'}
    assert roots and not roots[0].exists()


@pytest.mark.skipif(not shutil.which('tesseract') or not shutil.which('pdftoppm'), reason='requires real OCR tools')
async def test_real_inline_image_ocr_after_blank_pages_keeps_ocr_budget():
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new('RGB', (1200, 400), 'white')
    ImageDraw.Draw(image).text((60, 100), 'Customer export revenue 2026', fill='black',
                              font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 54))
    writer = PdfWriter()
    for _ in range(MAX_OCR_PAGES + 1):
        writer.add_blank_page(width=600, height=200)
    page = writer.add_blank_page(width=600, height=200)
    page[NameObject('/Resources')] = DictionaryObject()
    stream = DecodedStreamObject()
    stream.set_data(b'q 600 0 0 200 0 0 cm BI /W 1200 /H 400 /BPC 8 /CS /RGB /F /AHx ID\n'
                    + image.tobytes().hex().encode() + b'>\nEI Q')
    page[NameObject('/Contents')] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    result = await read_pdf(output.getvalue())
    assert result['status'] == 'succeeded', result
    assert not result['truncated']
    assert len(result['page_results']) == MAX_OCR_PAGES + 2
    assert all(page['method'] == 'text' and page['status'] == 'no_text' for page in result['page_results'][:-1])
    final = result['page_results'][-1]
    assert final['method'] == 'ocr' and final['status'] == 'succeeded'
    assert 'Customer export revenue 2026' in final['text']
