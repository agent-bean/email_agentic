class EmailAgent:
    def __init__(self, tools):
        self.tools = tools

    async def read(self, context):
        return await self.tools.execute("email.read", {}, context)

    async def publish(self, action_id, context):
        return await self.tools.execute("email.send", {"action_id": str(action_id)}, context)
