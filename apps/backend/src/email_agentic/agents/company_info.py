class CompanyInfoAgent:
    def __init__(self, tools):
        self.tools = tools

    async def run(self, run, context):
        return await self.tools.execute("company.lookup", {"domain": run["domain"]}, context)
