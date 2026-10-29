import asyncio
from urllib.parse import urlsplit

from ddgs import DDGS
from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

from email_agentic.integrations.http import bounded_retry
from email_agentic.platform.errors import ProviderFailure


class DuckDuckGo:
    def __init__(self, enabled=True):
        self.enabled = enabled
        # Keep the unkeyed provider to one active request per application process.
        self.slots = asyncio.Semaphore(1)
        self.cooldown_until = 0

    async def search(self, query, news=False):
        if not self.enabled:
            raise ProviderFailure("duckduckgo", category="disabled")
        async with self.slots:
            if asyncio.get_running_loop().time() < self.cooldown_until:
                raise ProviderFailure("duckduckgo", category="rate_limited")

            async def request(remaining):
                return await self._request(query, news)

            try:
                return await bounded_retry(request, 20, provider="duckduckgo")
            except ProviderFailure as exc:
                if exc.category in {"rate_limited", "search_failed"}:
                    self.cooldown_until = asyncio.get_running_loop().time() + 10
                raise

    async def _request(self, query, news):
        # DDGS is synchronous; its HTTP timeout also bounds work after task cancellation.
        task = asyncio.create_task(asyncio.to_thread(self._search, query, news))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Hold the slot until the bounded HTTP work exits, even on workflow cancellation.
            try:
                await task
            except Exception:
                pass
            raise

    def _search(self, query, news):
        try:
            with DDGS(timeout=10) as client:
                method = client.news if news else client.text
                rows = method(query, backend="duckduckgo", max_results=8,
                              region="wt-wt", timelimit="m" if news else None)
        except TimeoutException as exc:
            raise ProviderFailure("duckduckgo", transient=True, category="timeout") from exc
        except RatelimitException as exc:
            raise ProviderFailure("duckduckgo", transient=True, category="rate_limited") from exc
        except DDGSException as exc:
            raise ProviderFailure("duckduckgo", transient=True, category="search_failed") from exc
        results = []
        if not isinstance(rows, list):
            raise ProviderFailure("duckduckgo", category="invalid_receipt")
        seen = set()
        for row in rows[:8]:
            if not isinstance(row, dict):
                continue
            url = row.get("url" if news else "href")
            try:
                parts = urlsplit(url) if isinstance(url, str) else None
                valid = parts and parts.scheme in {"http", "https"} and parts.hostname
            except ValueError:
                valid = False
            if not valid or url in seen:
                continue
            seen.add(url)
            results.append({
                "url": url,
                "title": row.get("title") if isinstance(row.get("title"), str) else "",
                "content": row.get("body") if isinstance(row.get("body"), str) else "",
                "published_date": row.get("date") if news and isinstance(row.get("date"), str) else None,
            })
        return {"query": query, "results": results}
