import base64
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from types import SimpleNamespace

import httpx
import pytest

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


async def prepare_publication(c, db):
    import uuid
    from email_agentic.agents.contracts import Draft
    from email_agentic.domains.research.service import ResearchRequest
    from email_agentic.domains.reports.service import ReportEdit
    from email_agentic.integrations.email_message import decode_message

    owner = f"{uuid.uuid4()}@example.org"
    original = EmailMessage()
    original["From"] = "customer@example.org"
    original["To"] = owner
    original["Subject"] = "Discussion"
    original["Message-ID"] = "<source@example.org>"
    original.set_content("Request")
    source = await decode_message(original.as_bytes(), "mail-" + str(uuid.uuid4()), "thread-1")
    await c.inbox.save(owner, "google", source["id"], "email", source)
    item = await db.one("SELECT id FROM inputs WHERE owner=%s", (owner,))
    rid = await c.research.create(
        owner,
        ResearchRequest(company_name="Company", domain="example.org", source_input_id=item["id"]),
        str(uuid.uuid4()),
    )
    run = await c.research.get(owner, rid)
    await c.reports.initial(
        run, Draft(markdown="Briefing", email_subject="Reply", email_body="Approved reply."), {}
    )
    draft_id = await c.drafts.request(owner, rid, 1)
    await c.drafts.complete(draft_id, "succeeded", "draft-1", "thread-1")
    report = await c.reports.latest(owner, rid)
    await c.reports.edit(
        owner,
        rid,
        ReportEdit(
            **{k: report[k] for k in ("version", "markdown", "email_subject", "email_body", "recipients")},
            send_email=True,
        ),
    )
    latest = await c.reports.latest(owner, rid)
    assert await c.drafts.request(owner, rid, 2) == draft_id
    approval = await db.one("SELECT id FROM approvals WHERE report_id=%s", (latest["id"],))
    await c.approvals.decide(owner, approval["id"], True)
    action = await db.one("SELECT * FROM publication_actions WHERE approval_id=%s", (approval["id"],))
    return owner, rid, draft_id, action


@pytest.mark.parametrize("outcome", ["succeeded", "timeout", "edited"])
async def test_approved_send_binds_previous_identical_version_and_never_reposts(db, outcome):
    from email_agentic.bootstrap import build_container
    from email_agentic.platform.config import Settings
    from email_agentic.platform.errors import Conflict
    from email_agentic.tools.harness import ToolContext

    settings = Settings(APP_ENV="test", DATABASE_URL=db.pool.conninfo, _env_file=None)
    async with build_container(settings) as c:
        owner, rid, draft_id, action = await prepare_publication(c, db)
        posts = []

        def transport(request):
            if request.method == "GET":
                data = raw_draft(approved(), body="Edited privately" if outcome == "edited" else None)
                msg = BytesParser(policy=policy.default).parsebytes(
                    base64.urlsafe_b64decode(data["message"]["raw"])
                )
                msg.replace_header("From", owner)
                data["message"]["raw"] = base64.urlsafe_b64encode(msg.as_bytes()).decode()
                return httpx.Response(200, json=data)
            assert request.url.path.endswith("/drafts/send")
            posts.append(request)
            if outcome == "timeout":
                raise httpx.ReadError("response lost")
            return httpx.Response(200, json={"id": "sent-1", "threadId": "thread-1"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            c.google.client = client
            c.google.token = lambda: "unit-test-only"
            c.google.settings = settings.model_copy(update={"owner_email": owner})
            ctx = ToolContext(owner, "publication", frozenset({"publication:execute"}))
            if outcome != "succeeded":
                with pytest.raises(ProviderFailure):
                    await c.tools.execute("email.send", {"action_id": str(action["id"])}, ctx)
            else:
                await c.tools.execute("email.send", {"action_id": str(action["id"])}, ctx)
            saved = await db.one("SELECT * FROM publication_actions WHERE id=%s", (action["id"],))
            assert saved["gmail_draft_id"] == draft_id
            assert saved["status"] == {"timeout": "unknown", "edited": "failed"}.get(outcome, "succeeded")
            if outcome != "edited":
                assert await c.tools.execute("email.send", {"action_id": str(action["id"])}, ctx) == {
                    "status": "unchanged"
                }
                with pytest.raises(Conflict, match="Gmail Draft"):
                    await c.drafts.request(owner, rid, 2)
            assert len(posts) == (0 if outcome == "edited" else 1)
            draft = await db.one("SELECT status FROM gmail_drafts WHERE id=%s", (draft_id,))
            assert draft["status"] == ("sent" if outcome == "succeeded" else "succeeded")
            from email_agentic.api.routes import run_detail
            from email_agentic.platform.auth import Actor

            detail = await run_detail(
                rid, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=c))), Actor(owner)
            )
            assert len(detail["reports"]) == 1 and detail["reports"][0]["version"] == 2
            assert detail["gmail_drafts"][0]["matches_current"] is True
            assert detail["gmail_drafts"][0]["status"] == draft["status"]
            assert not await db.one(
                "SELECT id FROM publication_actions WHERE approval_id=%s AND kind='kb'",
                (action["approval_id"],),
            )
