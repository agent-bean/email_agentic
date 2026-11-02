"""Create or reconcile a Gmail draft while preserving uncertain delivery state."""

from pydantic import ValidationError
from uuid import UUID

from email_agentic.domains.inbox.drafts import GmailDrafts
from email_agentic.domains.publication.ports import DraftProvider
from email_agentic.models.publication import DraftPackage, DraftReceipt
from email_agentic.platform.errors import ProviderFailure


def checked_receipt(response, package):
    try:
        receipt = DraftReceipt.model_validate(response)
    except ValidationError:
        raise ProviderFailure("gmail", ambiguous=True, category="invalid_draft_receipt") from None
    if receipt.message.thread_id != (package.source_message or {}).get("thread_id"):
        raise ProviderFailure("gmail", ambiguous=True, category="invalid_draft_receipt")
    return receipt


class DraftApplication:
    def __init__(self, drafts: GmailDrafts, provider: DraftProvider):
        self.drafts, self.provider = drafts, provider

    async def execute(self, owner: str, draft_id: UUID):
        row = await self.drafts.package(owner, draft_id)
        if row is None:
            return {"status": "unchanged"}
        package = DraftPackage.model_validate(row)
        try:
            response = await self.provider.find_draft(package.correlation_id)
            if response is None and not package.reconcile_only:
                response = await self.provider.create_draft(package.provider_payload())
            if response is None:
                await self.drafts.complete(draft_id, "unknown", error="receipt_not_found")
                return {"status": "unknown"}
            receipt = checked_receipt(response, package)
            await self.drafts.complete(draft_id, "succeeded", receipt.id, receipt.message.thread_id)
            return {"status": "succeeded"}
        except ProviderFailure as exc:
            if exc.ambiguous:
                # A lost POST response is not permission to create another draft.
                try:
                    response = await self.provider.find_draft(package.correlation_id)
                    if response is not None:
                        receipt = checked_receipt(response, package)
                        await self.drafts.complete(
                            draft_id, "succeeded", receipt.id, receipt.message.thread_id,
                        )
                        return {"status": "succeeded"}
                except ProviderFailure:
                    pass
            await self.drafts.complete(
                draft_id, "unknown" if exc.ambiguous or package.reconcile_only else "failed",
                error=f"{exc.provider}:{exc.category}",
            )
            raise
