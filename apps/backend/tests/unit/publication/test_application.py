from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from email_agentic.domains.inbox.draft_application import DraftApplication
from email_agentic.domains.publication.application import PublicationApplication
from email_agentic.platform.errors import ProviderFailure


def package(**overrides):
    return {
        "id": uuid4(), "owner": "owner@example.invalid", "run_id": uuid4(),
        "markdown": "Briefing", "action_id": uuid4(), "action_kind": "email",
        "email_subject": "Re: Question", "email_body": "Approved answer",
        "recipients": {"to": ["customer@example.invalid"], "cc": [], "bcc": []},
        "correlation_id": "<action@example.invalid>",
        "source_message": {"thread_id": "thread-1", "headers": {"Message-ID": "<source@example.invalid>"}},
        "reconcile_only": False, **overrides,
    }


@pytest.mark.parametrize("receipt", [None, [], {}, {"id": 42}, {"id": "sent", "threadId": "other"}])
async def test_invalid_send_receipts_preserve_uncertainty(receipt):
    row = package()
    publication = SimpleNamespace(package=AsyncMock(return_value=row), complete=AsyncMock())
    provider = SimpleNamespace(send=AsyncMock(return_value=receipt))
    request, context = SimpleNamespace(action_id=row["action_id"]), SimpleNamespace(owner=row["owner"])
    with pytest.raises(ProviderFailure) as error:
        await PublicationApplication(publication, provider).execute(context.owner, request.action_id)
    assert error.value.ambiguous
    publication.complete.assert_awaited_once_with(request.action_id, "unknown", error="gmail:invalid_receipt")
    assert provider.send.await_args.args[0]["email_body"] == row["email_body"]


async def test_knowledge_failure_never_calls_email_provider():
    row = package(action_kind="kb")
    publication = SimpleNamespace(package=AsyncMock(return_value=row), save_kb=AsyncMock(side_effect=RuntimeError("database")))
    provider = SimpleNamespace(send=AsyncMock())
    with pytest.raises(RuntimeError, match="database"):
        await PublicationApplication(publication, provider).execute(
            row["owner"], row["action_id"],
        )
    provider.send.assert_not_awaited()


async def test_uncertain_draft_is_reconciled_without_creating_a_replacement():
    row = package(reconcile_only=True)
    drafts = SimpleNamespace(package=AsyncMock(return_value=row), complete=AsyncMock())
    provider = SimpleNamespace(find_draft=AsyncMock(return_value=None), create_draft=AsyncMock())
    request = SimpleNamespace(action_id=row["action_id"])
    result = await DraftApplication(drafts, provider).execute(row["owner"], request.action_id)
    assert result == {"status": "unknown"}
    provider.create_draft.assert_not_awaited()
    drafts.complete.assert_awaited_once_with(request.action_id, "unknown", error="receipt_not_found")


async def test_lost_draft_response_can_be_reconciled_with_a_valid_receipt():
    row = package()
    receipt = {"id": "draft-1", "message": {"threadId": "thread-1"}}
    drafts = SimpleNamespace(package=AsyncMock(return_value=row), complete=AsyncMock())
    provider = SimpleNamespace(
        find_draft=AsyncMock(side_effect=[None, receipt]),
        create_draft=AsyncMock(side_effect=ProviderFailure("gmail", ambiguous=True)),
    )
    request = SimpleNamespace(action_id=row["action_id"])
    assert await DraftApplication(drafts, provider).execute(row["owner"], request.action_id) == {
        "status": "succeeded",
    }
    provider.create_draft.assert_awaited_once()
    drafts.complete.assert_awaited_once_with(request.action_id, "succeeded", "draft-1", "thread-1")


async def test_malformed_draft_receipt_during_reconciliation_stays_unknown():
    row = package()
    drafts = SimpleNamespace(package=AsyncMock(return_value=row), complete=AsyncMock())
    provider = SimpleNamespace(
        find_draft=AsyncMock(side_effect=[None, {"id": "draft-1", "message": {"threadId": "wrong"}}]),
        create_draft=AsyncMock(return_value={"id": 42}),
    )
    request = SimpleNamespace(action_id=row["action_id"])
    with pytest.raises(ProviderFailure):
        await DraftApplication(drafts, provider).execute(row["owner"], request.action_id)
    drafts.complete.assert_awaited_once_with(request.action_id, "unknown", error="gmail:invalid_draft_receipt")
