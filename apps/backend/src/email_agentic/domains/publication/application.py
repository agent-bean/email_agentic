"""Execute approved publication without holding a transaction across provider calls."""

from pydantic import ValidationError
from uuid import UUID

from email_agentic.domains.publication.ports import EmailSender
from email_agentic.domains.publication.service import Publication
from email_agentic.models.publication import MessageReceipt, PublicationPackage
from email_agentic.platform.errors import ProviderFailure


class PublicationApplication:
    def __init__(self, publication: Publication, provider: EmailSender):
        self.publication, self.provider = publication, provider

    async def execute(self, owner: str, action_id: UUID):
        row = await self.publication.package(owner, action_id)
        if row is None:
            return {"status": "unchanged"}
        package = PublicationPackage.model_validate(row)
        report = package.provider_payload()
        try:
            if package.action_kind == "kb":
                await self.publication.save_kb(report)
                return {"status": "succeeded"}
            response = await self.provider.send(report)
            try:
                receipt = MessageReceipt.model_validate(response)
            except ValidationError:
                raise ProviderFailure("gmail", ambiguous=True, category="invalid_receipt") from None
            if package.source_message and receipt.thread_id != package.source_message["thread_id"]:
                raise ProviderFailure("gmail", ambiguous=True, category="invalid_receipt")
            await self.publication.complete(action_id, "succeeded", receipt.id)
            return {"status": "succeeded"}
        except ProviderFailure as exc:
            await self.publication.complete(
                action_id, "unknown" if exc.ambiguous else "failed",
                error=f"{exc.provider}:{exc.category}",
            )
            raise
