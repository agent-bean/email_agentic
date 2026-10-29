"""Offline real OCR and Gmail receipt contract tests; never contact a mailbox."""
import base64
from email.message import EmailMessage
from types import SimpleNamespace

import httpx
import pytest

from email_agentic.integrations.google import Google
from email_agentic.platform.errors import ProviderFailure


@pytest.mark.parametrize(('known_receipt', 'outcome'), [
    (known, outcome) for known in (True, False)
    for outcome in ('matched', 'mismatch', 'not_found', 'wrong_mailbox', 'wrong_thread',
                    'wrong_recipient', 'missing_sent', 'wrong_correlation', 'wrong_receipt',
                    'message_missing', 'provider_failure')
] + [(False, 'multiple_matches'), (False, 'next_page')])
async def test_sent_review_reads_actual_message_and_never_mutates(known_receipt, outcome):
    report = {'owner': 'owner@example.org', 'email_subject': 'Approved subject', 'email_body': 'Approved body',
              'recipients': {'to': ['customer@example.org']}, 'correlation_id': '<approved@example.org>',
              'provider_id': 'sent-1' if known_receipt else None,
              'source_message': {'thread_id': 'thread-1', 'headers': {'Message-ID': '<source@example.org>'}}}
    message = EmailMessage()
    message['From'] = report['owner']
    message['To'] = 'other@example.org' if outcome == 'wrong_recipient' else 'customer@example.org'
    message['Subject'] = report['email_subject']
    message['Message-ID'] = '<normalized@mail.gmail.com>' if outcome == 'wrong_correlation' else report['correlation_id']
    message['In-Reply-To'] = '<source@example.org>'
    message.set_content('Tampered body' if outcome == 'mismatch' else report['email_body'])
    paths = []
    def transport(request):
        assert request.method == 'GET'
        paths.append(request.url.path)
        if request.url.path.endswith('/profile'):
            return httpx.Response(200, json={'emailAddress': 'wrong@example.org' if outcome == 'wrong_mailbox' else report['owner']})
        if request.url.path.endswith('/messages'):
            assert not known_receipt, 'Stored receipts must not depend on correlation search'
            assert request.url.params['q'] == 'in:sent rfc822msgid:approved@example.org'
            return httpx.Response(200, json={
                'messages': [] if outcome == 'not_found' else
                [{'id': 'sent-1'}, {'id': 'sent-2'}] if outcome == 'multiple_matches' else [{'id': 'sent-1'}],
                **({'nextPageToken': 'more'} if outcome == 'next_page' else {})})
        assert request.url.path.endswith('/messages/sent-1')
        if outcome == 'message_missing' or (known_receipt and outcome == 'not_found'):
            return httpx.Response(404)
        if outcome == 'provider_failure':
            return httpx.Response(403)
        return httpx.Response(200, json={'id': 'other' if outcome == 'wrong_receipt' else 'sent-1', 'threadId': 'other' if outcome == 'wrong_thread' else 'thread-1', 'labelIds': [] if outcome == 'missing_sent' else ['SENT'],
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()})
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email=report['owner']))
        google.token = lambda: 'test-only'
        if outcome in {'wrong_mailbox', 'provider_failure'}:
            with pytest.raises(ProviderFailure, match='gmail'):
                await google.review_sent(report)
            if outcome == 'wrong_mailbox':
                assert len(paths) == 1
        else:
            expected = ('matched' if known_receipt and outcome == 'wrong_correlation' else
                        'not_found' if outcome == 'message_missing' else
                        'multiple_matches' if outcome == 'next_page' else
                        'mismatch' if outcome.startswith('wrong_') or outcome == 'missing_sent' else outcome)
            assert (await google.review_sent(report))['verification'] == expected
    assert len(paths) <= (2 if known_receipt else 3)
