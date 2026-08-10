"""
# backend/core/tools/web_tools.py

This module contains standard web interactions for agents to research the internet.

Responsibilities:
1. Provide `web_search` using a configurable search API (Tavily, SerpAPI, or Google Custom Search).
2. Provide `web_fetch` to retrieve and extract text content from a URL.
3. Both tools are critical for the confidence-based research loop in the ReACT agent.
"""

import httpx
from core.llm.config_manager import load_config, get_key


class WebTools:
    def __init__(self):
        self._load_keys()

    def _load_keys(self):
        """Loads API keys from ~/.carole/config.json with env var fallback."""
        cfg = load_config()
        self.tavily_key = get_key(cfg, "tavily", "TAVILY_API_KEY")

    def reload_config(self):
        """Hot-reload keys after settings are saved."""
        self._load_keys()

    async def web_search(self, query: str, max_results: int = 5) -> str:
        """
        Performs a web search using the Tavily API.
        Returns formatted search results with titles, URLs, and content snippets.
        """
        if not self.tavily_key:
            return (
                "[WebSearch Error: TAVILY_API_KEY is not configured.]\n"
                "Please set the TAVILY_API_KEY environment variable to enable web search."
            )

        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
            "include_answer": True,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers=headers,
                    json=payload
                )
                if response.status_code != 200:
                    return f"[WebSearch API Error {response.status_code}: {response.text}]"

                data = response.json()

                # Format results
                output_lines = []
                answer = data.get("answer", "")
                if answer:
                    output_lines.append(f"AI Answer: {answer}\n")

                results = data.get("results", [])
                for i, result in enumerate(results, 1):
                    title = result.get("title", "No Title")
                    url = result.get("url", "")
                    content = result.get("content", "")[:300]
                    output_lines.append(f"[{i}] {title}\n    URL: {url}\n    {content}\n")

                return "\n".join(output_lines) if output_lines else "No results found."
            except Exception as e:
                return f"[WebSearch Connection Error: {str(e)}]"

    async def web_fetch(self, url: str) -> str:
        """
        Fetches the text content of a web page.
        Strips HTML and returns plain text (limited to first 5000 chars to fit context).
        """
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers={"User-Agent": "CaroleAI/1.0"})
                if response.status_code != 200:
                    return f"[WebFetch Error {response.status_code} for {url}]"

                content_type = response.headers.get("content-type", "")
                text = response.text

                # Convert HTML to readable text using markdownify to preserve links
                if "html" in content_type:
                    try:
                        import markdownify
                        text = markdownify.markdownify(text, heading_style="ATX", strip=["script", "style", "nav", "footer", "header"])
                    except ImportError:
                        # Fallback to regex if markdownify not installed
                        import re
                        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
                        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"\s+", " ", text).strip()

                # Truncate to prevent context window overflow (using Claude Code's generous 100k limit)
                MAX_MARKDOWN_LENGTH = 100000
                if len(text) > MAX_MARKDOWN_LENGTH:
                    text = text[:MAX_MARKDOWN_LENGTH] + "\n\n[Content truncated due to length...]"

                return f"Source: {url}\n\n{text}"
            except Exception as e:
                return f"[WebFetch Connection Error: {str(e)}]"

    async def http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict = None,
        body: dict = None,
        timeout: float = 30.0,
    ) -> str:
        """
        Make an arbitrary HTTP request and return the response.
        Useful for testing REST APIs, triggering webhooks, or calling internal services.

        Args:
            url: The full URL to request.
            method: HTTP method (GET, POST, PUT, PATCH, DELETE). Default: GET.
            headers: Optional dict of request headers.
            body: Optional dict to send as JSON body (auto-sets Content-Type: application/json).
            timeout: Request timeout in seconds. Default: 30.
        """
        method = method.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            return f"Error: Unsupported HTTP method '{method}'. Use GET, POST, PUT, PATCH, DELETE, HEAD, or OPTIONS."

        request_headers = {"User-Agent": "CaroleAI/1.0"}
        if headers:
            request_headers.update(headers)
        if body and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            try:
                kwargs = {"headers": request_headers}
                if body:
                    kwargs["json"] = body
                response = await client.request(method, url, **kwargs)

                # Try to parse JSON response for readability
                content_type = response.headers.get("content-type", "")
                try:
                    if "json" in content_type:
                        import json
                        body_text = json.dumps(response.json(), indent=2)
                    else:
                        body_text = response.text[:5000]
                        if len(response.text) > 5000:
                            body_text += "\n[Response truncated to 5000 chars]"
                except Exception:
                    body_text = response.text[:5000]

                return (
                    f"HTTP {method} {url}\n"
                    f"Status: {response.status_code} {response.reason_phrase}\n"
                    f"Headers: {dict(response.headers)}\n\n"
                    f"Body:\n{body_text}"
                )
            except httpx.TimeoutException:
                return f"[HTTP Request Timeout: {url} did not respond within {timeout}s]"
            except Exception as e:
                return f"[HTTP Request Error: {str(e)}]"


# Singleton
web_tools = WebTools()
