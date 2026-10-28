class MemoryAgent:
    def __init__(self, tools):
        self.tools = tools

    async def run(self, run, context):
        return await self.tools.execute("memory.retrieve", {"domain": run["domain"]}, context)
