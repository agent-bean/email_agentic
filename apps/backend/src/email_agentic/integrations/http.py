import asyncio
import logging
import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from email_agentic.platform.errors import ProviderFailure
from email_agentic.runtime.budget import remaining_budget, reserve_attempt


def retry_delay(value):
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


async def bounded_retry(operation, budget, *, provider, operation_key=None):
    deadline = asyncio.get_running_loop().time() + remaining_budget(budget)
    for attempt in range(3):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise ProviderFailure(provider, transient=True, category="network_or_timeout")
        try:
            async with asyncio.timeout(max(0, remaining)):
                if operation_key is not None:
                    key = hashlib.sha256(f"{provider}:{operation_key}".encode()).hexdigest()
                    if not await reserve_attempt(key):
                        raise ProviderFailure(provider, category="retry_exhausted")
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                return await operation(remaining)
        except TimeoutError:
            raise ProviderFailure(provider, transient=True, category="network_or_timeout") from None
        except ProviderFailure as exc:
            delay = exc.retry_after if exc.retry_after is not None else 0.25 * 2 ** attempt
            if (
                not exc.transient
                or exc.ambiguous
                or attempt == 2
                or delay >= deadline - asyncio.get_running_loop().time()
            ):
                raise
            await asyncio.sleep(delay)


async def json_request(client, provider, method, url, deadline_seconds=45, **kwargs):
    deadline_seconds = remaining_budget(deadline_seconds)
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
        category = f"http_{response.status_code}"
        rate_limited = False
        if provider == "gmail" and response.status_code == 403:
            try:
                reasons = {item.get("reason") for item in response.json()["error"]["errors"]}
            except (AttributeError, KeyError, TypeError, ValueError):
                reasons = set()
            rate_limited = bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded"})
            for reason, label in (("dailyLimitExceeded", "daily_limit"),
                                  ("domainPolicy", "domain_policy"),
                                  ("insufficientPermissions", "permissions")):
                if reason in reasons:
                    category = label
        raise ProviderFailure(
            provider,
            transient=rate_limited or response.status_code in {408, 429, 500, 502, 503, 504},
            ambiguous=provider == "gmail" and method == "POST" and response.status_code >= 500,
            category=category,
            retry_after=retry_delay(response.headers.get("Retry-After")),
        )
    try:
        return response.json()
    except ValueError:
        raise ProviderFailure(
            provider, ambiguous=provider == "gmail" and method == "POST", category="invalid_json"
        ) from None
