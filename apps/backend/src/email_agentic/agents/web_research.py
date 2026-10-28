import asyncio

from email_agentic.platform.errors import ProviderFailure


class WebResearchAgent:
    def __init__(self, tools):
        self.tools = tools

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
        return responses
