import asyncio


class WebResearchAgent:
    def __init__(self, tools):
        self.tools = tools

    async def run(self, run, context):
        queries = [
            (f"{run['company_name']} {run['domain']} company products services partners", False),
            (f"{run['company_name']} {run['domain']} news", True),
        ]
        return await asyncio.gather(
            *(self.tools.execute("web.search", {"query": q, "news": news}, context) for q, news in queries)
        )
