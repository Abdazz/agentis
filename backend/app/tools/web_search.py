import httpx
from app.tools.base import BaseTool, SessionContext, ToolResult
from app.config import settings


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for information. Returns ranked results with titles, URLs, and snippets."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query":       {"type": "string"},
            "num_results": {"type": "integer", "default": 10, "maximum": 20},
            "language":    {"type": "string", "enum": ["en", "fr"], "default": "en"},
            "time_range":  {"type": "string", "enum": ["day", "week", "month", "year"]},
        },
        "required": ["query"],
    }

    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        query = params["query"]
        num_results = min(int(params.get("num_results", 10)), 20)
        language = params.get("language", "en")
        time_range = params.get("time_range")

        backend = settings.search_backend

        if backend == "brave":
            return await self._brave_search(query, num_results, language, time_range)
        elif backend == "searxng":
            return await self._searxng_search(query, num_results, language)
        else:
            return ToolResult(ok=False, error=f"Unknown search backend: {backend}", retryable=False)

    async def _brave_search(self, query, num_results, language, time_range) -> ToolResult:
        if not settings.brave_api_key:
            return ToolResult(ok=True, data={"results": []})

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": settings.brave_api_key,
        }
        req_params: dict = {"q": query, "count": num_results, "search_lang": language}
        if time_range:
            req_params["freshness"] = time_range

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers=headers,
                    params=req_params,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=str(e), retryable=True)

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "published_at": r.get("page_age"),
            }
            for r in data.get("results", [])
        ]
        return ToolResult(ok=True, data={"results": results})

    async def _searxng_search(self, query, num_results, language) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{settings.searxng_url}/search",
                    params={"q": query, "format": "json", "language": language, "count": num_results},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as e:
            return ToolResult(ok=False, error=str(e), retryable=True)

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
                "published_at": r.get("publishedDate"),
            }
            for r in data.get("results", [])[:num_results]
        ]
        return ToolResult(ok=True, data={"results": results})
