"""Structural provider boundaries; existing Google adapters and doubles satisfy them."""

from typing import Any, Protocol


class EmailSender(Protocol):
    async def send(self, report: dict[str, Any]) -> object: ...


class DraftProvider(Protocol):
    async def find_draft(self, correlation_id: str) -> object | None: ...

    async def create_draft(self, report: dict[str, Any]) -> object: ...
