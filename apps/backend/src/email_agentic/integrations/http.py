import asyncio
import logging
import httpx
from email_agentic.platform.errors import ProviderFailure


async def json_request(client, provider, method, url, deadline_seconds=45, **kwargs):
    try:
        async with asyncio.timeout(deadline_seconds):
            response = await client.request(method, url, **kwargs)
    except (TimeoutError, httpx.RequestError) as exc:
        logging.getLogger(__name__).warning(
            "Provider transport failed: provider=%s error=%s budget_seconds=%s",
            provider, type(exc).__name__, deadline_seconds,
        )
        raise ProviderFailure(
            provider,
            transient=True,
            ambiguous=method == "POST" and provider == "gmail",
            category="network_or_timeout",
        ) from None
    if response.is_error:
        raise ProviderFailure(
            provider,
            transient=response.status_code in {408, 429, 500, 502, 503, 504},
            ambiguous=provider == "gmail" and method == "POST" and response.status_code >= 500,
            category=f"http_{response.status_code}",
        )
    try:
        return response.json()
    except ValueError:
        raise ProviderFailure(
            provider, ambiguous=provider == "gmail" and method == "POST", category="invalid_json"
        ) from None
