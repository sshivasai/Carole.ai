"""
# backend/core/tools/web_tools.py

This module contains standard web interactions for agents to research the internet.

Responsibilities:
1. Provide `web_search` using a configurable search API (Tavily, SerpAPI, or Google Custom Search).
2. Provide `web_fetch` to retrieve and extract text content from a URL.
3. Both tools are critical for the confidence-based research loop in the ReACT agent.
"""

import os
import httpx
from typing import List, Dict, Any


class WebTools:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")

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

                # Basic HTML tag stripping for readability
                if "html" in content_type:
                    import re
                    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
                    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text).strip()

                # Truncate to prevent context window overflow
                if len(text) > 5000:
                    text = text[:5000] + "\n... [Truncated]"

                return f"Source: {url}\n\n{text}"
            except Exception as e:
                return f"[WebFetch Connection Error: {str(e)}]"


# Singleton
web_tools = WebTools()
