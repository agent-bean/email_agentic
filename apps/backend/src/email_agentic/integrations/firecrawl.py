from ipaddress import ip_address
from urllib.parse import urlsplit

from email_agentic.integrations.http import json_request
from email_agentic.platform.errors import ProviderFailure


class Firecrawl:
    def __init__(self, client, key):
        self.client, self.key = client, key

    async def scrape(self, url, timeout_seconds=15):
        try:
            parts = urlsplit(url)
        except ValueError:
            raise ProviderFailure("firecrawl", category="invalid_url") from None
        host = parts.hostname or ""
        public = (
            "." in host and host.rstrip(".") != "localhost"
            and not host.rstrip(".").endswith((".localhost", ".local", ".internal"))
            and not host.replace(".", "").isdigit()
        )
        try:
            public = ip_address(host).is_global
        except ValueError:
            pass
        if parts.scheme not in {"http", "https"} or parts.username or parts.password or not public:
            raise ProviderFailure("firecrawl", category="invalid_url")
        if not self.key:
            raise ProviderFailure("firecrawl", category="not_configured")
        response = await json_request(
            self.client, "firecrawl", "POST", "https://api.firecrawl.dev/v2/scrape",
            deadline_seconds=timeout_seconds, timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {self.key}"},
            json={
                "url": url, "formats": ["markdown"], "onlyMainContent": True,
                "parsers": [],
                "timeout": max(1000, int((timeout_seconds - 1) * 1000)),
                "skipTlsVerification": False,
            },
        )
        if not isinstance(response, dict) or response.get("success") is not True:
            raise ProviderFailure("firecrawl", category="invalid_receipt")
        data = response.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("markdown"), str):
            raise ProviderFailure("firecrawl", category="missing_content")
        markdown = data["markdown"]
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict) or not isinstance(metadata.get("statusCode", 200), int):
            raise ProviderFailure("firecrawl", category="invalid_receipt")
        if metadata.get("error") or metadata.get("statusCode", 200) >= 400:
            raise ProviderFailure("firecrawl", category="page_error")
        if not markdown.strip():
            raise ProviderFailure("firecrawl", category="empty_content")
        return {"markdown": markdown, "metadata": metadata}
