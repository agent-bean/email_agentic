"""Provider capabilities consumed by research and intake agents."""

from typing import Any, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

Output = TypeVar("Output", bound=BaseModel)


class SearchProvider(Protocol):
    async def search(self, query: str, news: bool = False) -> dict[str, Any]: ...


class StructuredGenerator(Protocol):
    async def structured(
        self,
        run_id: UUID | str | None,
        schema: type[Output],
        system: str,
        payload: str,
        *,
        input_id: UUID | str | None = None,
    ) -> Output: ...
