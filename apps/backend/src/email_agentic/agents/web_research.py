import asyncio
from urllib.parse import urldefrag

from email_agentic.platform.errors import ProviderFailure, ToolDenied


class WebResearchAgent:
    def __init__(self, tools, read_pages=0):
        self.tools = tools
        self.read_pages = read_pages

    async def run(self, run, context):
        company = f'"{run["company_name"]}"'
        domain = run["domain"]
        # Only confirmed company identity enters public search, never email or meeting context.
        queries = [
            ("identity", f"{company} site:{domain} company legal entity annual report employees revenue", False),
            ("products", f"{company} site:{domain} products platforms technology solutions", False),
            ("deployments", f"{company} case study customer deployment results implementation", False),
            ("partners", f"{company} strategic partnership technology partner agreement", False),
            ("news", f"{company} {domain} announcements business technology investment", True),
        ]
        # Leave capacity for the calendar request in the parallel collection branch.
        slots = asyncio.Semaphore(3)

        async def search(area, query, news):
            async with slots:
                try:
                    response = await self.tools.execute(
                        "web.search", {"query": query, "news": news}, context
                    )
                except ProviderFailure as exc:
                    return {
                        "research_area": area,
                        "status": "failed",
                        "error_code": exc.category,
                        "results": [],
                    }
                return {**response, "research_area": area, "status": "succeeded"}

        responses = await asyncio.gather(*(search(*query) for query in queries))
        if all(response["status"] == "failed" for response in responses):
            raise ProviderFailure("tavily", category="all_searches_failed")
        await self.read_sources(responses, context)
        return responses

    async def read_sources(self, responses, context):
        if not self.read_pages:
            return
        # Round-robin by search rank preserves coverage across research topics.
        selected = {}
        max_results = max((len(response["results"]) for response in responses), default=0)
        for rank in range(max_results):
            for response in responses:
                if rank >= len(response["results"]):
                    continue
                item = response["results"][rank]
                url = urldefrag(item.get("url", ""))[0].rstrip("/")
                if url and url not in selected and len(selected) < self.read_pages:
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
                    return {"status": "succeeded", "markdown": data["markdown"][:12000]}
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
                item["page_read"] = {key: value for key, value in result.items() if key != "markdown"}
                if result["status"] == "succeeded":
                    item["raw_content"] = result["markdown"]
