from datetime import datetime, UTC, timedelta


class CalendarAgent:
    def __init__(self, tools):
        self.tools = tools

    async def run(self, run, context):
        now = datetime.now(UTC)
        return await self.tools.execute(
            "calendar.list", {"start": now.isoformat(), "end": (now + timedelta(days=7)).isoformat()}, context
        )
