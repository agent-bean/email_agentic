import asyncio
from urllib.parse import urldefrag

from email_agentic.platform.errors import ProviderFailure, ToolDenied


class WebResearchAgent:
    def __init__(self, tools, read_pages=0, duckduckgo_enabled=False):
        self.tools = tools
        self.read_pages = read_pages
        self.providers = ("tavily", "duckduckgo") if duckduckgo_enabled else ("tavily",)

    async def run(self, run, context):
        company = run["company_name"]
        domain = run["domain"]
        # Only confirmed company identity enters public search, never email or meeting context.
        queries = [
            # The confirmed domain disambiguates the entity without excluding
            # regulators, customer accounts or counterpart announcements.
            ("identity", f"{company} {domain} company legal entity annual report employees revenue", False),
            ("products", f"{company} {domain} company business products platforms technology services", False),
            ("deployments", f"{company} {domain} case study customer deployment results implementation", False),
            ("partners", f"{company} {domain} partnership cooperation technology partner agreement", False),
            ("adoption", f"{company} {domain} digital transformation ERP CRM AI automation implementation", False),
            ("news", f"{company} {domain} announcements business technology investment", True),
        ]
        # Leave capacity for the calendar request in the parallel collection branch.
        slots = asyncio.Semaphore(3)
        provider_slots = {"tavily": asyncio.Semaphore(3), "duckduckgo": asyncio.Semaphore(1)}

        async def search(area, query, news, provider):
            # Wait for the serial secondary provider before claiming shared capacity.
            # Otherwise queued DDG calls can starve independent primary searches.
            async with provider_slots[provider], slots:
                try:
                    response = await self.tools.execute(
                        "web.search", {"query": query, "news": news, "provider": provider}, context
                    )
                except ProviderFailure as exc:
                    return {
                        "research_area": area,
                        "provider": provider,
                        "status": "failed",
                        "error_code": exc.category,
                        "results": [],
                    }
                return {**response, "research_area": area, "provider": provider, "status": "succeeded"}

        responses = await asyncio.gather(*(
            search(*query, provider) for query in queries for provider in self.providers
        ))
        if all(response["status"] == "failed" for response in responses):
            raise ProviderFailure("web_search", category="all_searches_failed")
        await self.read_sources(responses, context)
        return responses

    async def read_sources(self, responses, context):
        # Round-robin by search rank preserves coverage across research topics.
        # Keep long search-provider page excerpts; spend page reads on missing content.
        available = {}
        for response in responses:
            for item in response["results"]:
                key = urldefrag(item.get("url", ""))[0].rstrip("/")
                content = item.get("raw_content") or ""
                if key and len(content) > len(available.get(key, "")):
                    available[key] = content
        sufficient = {key for key, content in available.items() if len(content.strip()) >= 6000}
        selected = {}
        max_results = max((len(response["results"]) for response in responses), default=0)
        for rank in range(max_results):
            for response in responses:
                if rank >= len(response["results"]):
                    continue
                item = response["results"][rank]
                url = urldefrag(item.get("url", ""))[0].rstrip("/")
                if url and url not in sufficient and url not in selected and len(selected) < self.read_pages:
                    selected[url] = item["url"]

        slots = asyncio.Semaphore(2)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 45

        async def read(url):
            async with slots:
                remaining = deadline - loop.time()
                if remaining < 1:
                    return {"status": "failed", "error_code": "collection_deadline"}
                try:
                    data = await self.tools.execute(
                        "web.scrape", {"url": url, "timeout_seconds": min(15, remaining)}, context
                    )
                    result = {"status": "succeeded", "markdown": data["markdown"][:12000]}
                    # Keep article-specific date candidates apart from search dates.
                    # Generic/update metadata can describe the site header, not the article.
                    metadata = data.get("metadata") or {}
                    publication_metadata = {
                        key: metadata[key][:200]
                        for key in ("article:published_time", "datePublished", "publishedTime", "published_time")
                        if isinstance(metadata, dict) and isinstance(metadata.get(key), str)
                    }
                    if publication_metadata:
                        result["publication_metadata"] = publication_metadata
                    return result
                except ProviderFailure as exc:
                    return {"status": "failed", "error_code": exc.category}
                except ToolDenied as exc:
                    return {"status": "failed", "error_code": f"tool_{exc.gate}"}

        read_results = await asyncio.gather(*(read(url) for url in selected.values()))
        reads = dict(zip(selected, read_results))
        for response in responses:
            for item in response["results"]:
                key = urldefrag(item.get("url", ""))[0].rstrip("/")
                result = reads.get(key, {"status": "not_selected"})
                if key in sufficient:
                    result = {"status": "not_selected", "reason": "search_content_available"}
                if key in available:
                    item["raw_content"] = available[key]
                item["page_read"] = {key: value for key, value in result.items() if key != "markdown"}
                if result["status"] == "succeeded":
                    item["raw_content"] = result["markdown"]
