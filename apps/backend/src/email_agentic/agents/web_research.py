import asyncio
import unicodedata
from urllib.parse import urldefrag

from markdown_it import MarkdownIt

from email_agentic.platform.errors import ProviderFailure, ToolDenied


def article_body(markdown, title):
    """Separate a page prefix only when a Markdown heading identifies this article."""
    def normalized(value):
        return " ".join("".join(
            char if char.isalnum() else " "
            for char in unicodedata.normalize("NFKC", value).casefold()
        ).split())

    # Bound parsing work without truncating the retained source. A title beyond
    # this opening remains unknown; do not match an incomplete final line.
    if len(title or "") > 1024:
        return markdown, {"status": "unknown"}
    opening = markdown[:65536]
    if len(markdown) > len(opening):
        opening = opening[:opening.rfind("\n") + 1]
    target = normalized(title or "")
    if target:
        tokens = MarkdownIt("commonmark").parse(opening)
        lines = opening.splitlines(keepends=True)
        matches = []
        for index, token in enumerate(tokens[:-1]):
            if token.type != "heading_open" or token.map is None:
                continue
            inline = tokens[index + 1]
            heading = "".join(
                child.content for child in (inline.children or [])
                if child.type in {"text", "code_inline"}
            )
            if normalized(heading) == target:
                matches.append((token.tag, token.map[0], heading))
        # Prefer the document title over a navigation subsection with the same
        # text. Ambiguous lower-level matches do not establish a boundary.
        primary = [match for match in matches if match[0] == "h1"]
        candidates = primary or (matches if len(matches) == 1 else [])
        if candidates:
            _, start, heading = candidates[0]
            offset = sum(len(line) for line in lines[:start])
            body = markdown[offset:]
            return body, {
                "status": "title_heading_matched", "heading": heading,
                "opening": body[:1000], "excluded_prefix": markdown[:offset],
            }
    return markdown, {"status": "unknown"}


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
        parsed = {}

        async def identify(content, title):
            key = (content, title)
            if key not in parsed:
                parsed[key] = await asyncio.to_thread(article_body, content, title)
            return parsed[key]

        available = {}
        for response in responses:
            for item in response["results"]:
                key = urldefrag(item.get("url", ""))[0].rstrip("/")
                content = item.get("raw_content") or ""
                body, article_context = await identify(content, item.get("title", ""))
                # A longer boilerplate copy must not displace an identified article.
                candidate = (body, article_context)
                current = available.get(key, ("", {"status": "unknown"}))
                def score(entry):
                    return (entry[1]["status"] == "title_heading_matched", len(entry[0]))
                if key and score(candidate) > score(current):
                    available[key] = candidate
        sufficient = {key for key, (content, _) in available.items() if len(content.strip()) >= 6000}
        selected = {}
        titles = {}
        max_results = max((len(response["results"]) for response in responses), default=0)
        for rank in range(max_results):
            for response in responses:
                if rank >= len(response["results"]):
                    continue
                item = response["results"][rank]
                url = urldefrag(item.get("url", ""))[0].rstrip("/")
                if url and url not in sufficient and url not in selected and len(selected) < self.read_pages:
                    selected[url] = item["url"]
                    titles[url] = available.get(url, ("", {}))[1].get("heading", item.get("title", ""))

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
                    body, article_context = await identify(
                        data["markdown"], titles.get(urldefrag(url)[0].rstrip("/"), "")
                    )
                    result = {
                        "status": "succeeded", "markdown": body[:12000], "article_context": article_context,
                    }
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
                item["page_read"] = {
                    key: value for key, value in result.items() if key not in {"markdown", "article_context"}
                }
                if key in available:
                    item["raw_content"], item["article_context"] = available[key]
                if result["status"] == "succeeded":
                    if (item.get("article_context", {}).get("status") == "title_heading_matched"
                            and result["article_context"]["status"] == "unknown"):
                        # An unscoped page response cannot reintroduce navigation
                        # over an already identified article from the same URL.
                        item["unscoped_page_content"] = result["markdown"]
                        item["page_read"]["content_selection"] = "search_article_body"
                    else:
                        item["raw_content"] = result["markdown"]
                        item["article_context"] = result["article_context"]
