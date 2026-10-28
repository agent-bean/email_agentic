from email_agentic.integrations.http import json_request


class Tavily:
    def __init__(self, client, key):
        self.client, self.key = client, key

    async def search(self, query, news=False):
        if not self.key:
            from email_agentic.platform.errors import ProviderFailure

            raise ProviderFailure("tavily")
        body = {
            "query": query,
            "max_results": 15,
            "include_raw_content": True,
            "include_answer": False,
            "include_usage": True,
            "topic": "news" if news else "general",
        }
        if news:
            body.update(time_range="month", include_published_date=True)
        return await json_request(
            self.client,
            "tavily",
            "POST",
            "https://api.tavily.com/search",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body,
        )
