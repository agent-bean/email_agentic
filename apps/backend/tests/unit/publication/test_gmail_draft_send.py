import base64
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from types import SimpleNamespace
import json

import httpx
import pytest

from email_agentic.integrations.google import Google
from email_agentic.platform.errors import ProviderFailure


def approved():
    return {
        "email_subject": "Re: Discussion",
        "email_body": "Approved reply.",
        "recipients": {"to": ["customer@example.org"], "cc": [], "bcc": []},
        "correlation_id": "<action@example.org>",
        "gmail_draft_provider_id": "draft-1",
        "source_message": {"thread_id": "thread-1", "headers": {"Message-ID": "<source@example.org>"}},
    }


def raw_draft(report, body=None):
    msg = EmailMessage()
    msg["From"] = "owner@example.org"
    msg["To"] = "customer@example.org"
    msg["Subject"] = report["email_subject"]
    msg["Message-ID"] = "<exported-draft@example.org>"
    msg["In-Reply-To"] = "<source@example.org>"
    msg.set_content(body if body is not None else report["email_body"])
    return {
        "id": "draft-1",
        "message": {"threadId": "thread-1", "raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()},
    }


async def test_sending_exported_draft_consumes_it_with_approved_content_and_action_id():
    report = approved()
    paths = []

    def transport(request):
        paths.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=raw_draft(report))
        assert request.url.path.endswith("/drafts/send")
        payload = json.loads(request.content)
        assert payload["id"] == "draft-1"
        assert payload["message"]["threadId"] == "thread-1"
        msg = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(payload["message"]["raw"])
        )
        assert msg["Message-ID"] == report["correlation_id"]
        assert msg["To"] == "customer@example.org"
        assert msg["In-Reply-To"] == "<source@example.org>"
        assert msg.get_content().strip() == report["email_body"]
        return httpx.Response(200, json={"id": "sent-1", "threadId": "thread-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email="owner@example.org"))
        google.token = lambda: "unit-test-only"
        assert (await google.send(report))["id"] == "sent-1"
    assert paths == [("GET", "/gmail/v1/users/me/drafts/draft-1"), ("POST", "/gmail/v1/users/me/drafts/send")]


@pytest.mark.parametrize(
    "change", ["body", "recipient", "cc", "subject", "thread", "reply", "attachment", "missing"]
)
async def test_changed_or_missing_draft_is_never_sent_or_replaced(change):
    report = approved()
    draft = raw_draft(report)
    msg = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(draft["message"]["raw"]))
    if change == "body":
        msg.set_content("Edited in Gmail")
    if change == "recipient":
        msg.replace_header("To", "other@example.org")
    if change == "cc":
        msg["Cc"] = "other@example.org"
    if change == "subject":
        msg.replace_header("Subject", "Changed")
    if change == "thread":
        draft["message"]["threadId"] = "other-thread"
    if change == "reply":
        msg.replace_header("In-Reply-To", "<other@example.org>")
    if change == "attachment":
        msg.add_attachment(b"private", maintype="application", subtype="octet-stream", filename="extra.bin")
    draft["message"]["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    def transport(request):
        assert request.method == "GET"
        return httpx.Response(404 if change == "missing" else 200, json={} if change == "missing" else draft)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email="owner@example.org"))
        google.token = lambda: "unit-test-only"
        with pytest.raises(ProviderFailure):
            await google.send(report)


async def test_email_without_exported_draft_keeps_direct_send_contract():
    report = approved()
    report.pop("gmail_draft_provider_id")

    def transport(request):
        assert request.method == "POST" and request.url.path.endswith("/messages/send")
        return httpx.Response(200, json={"id": "sent-direct", "threadId": "thread-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        google = Google(client, SimpleNamespace(owner_email="owner@example.org"))
        google.token = lambda: "unit-test-only"
        assert (await google.send(report))["id"] == "sent-direct"
