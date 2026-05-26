"""
Web tools: search, scraping, browser automation, screenshots
"""

import requests
from typing import Optional, Dict, Any
from urllib.parse import quote_plus
from . import battlefield_tool


@battlefield_tool(
    name="web_search",
    description="Search the web using DuckDuckGo",
    category="web",
    parameters={
        "query": {"type": "string", "required": True, "description": "Search query"},
        "num_results": {"type": "number", "required": False, "description": "Number of results (default: 5)"}
    }
)
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web"""
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for i, result in enumerate(ddgs.text(query, max_results=num_results)):
                results.append(f"{i+1}. {result['title']}")
                results.append(f"   URL: {result['href']}")
                results.append(f"   {result['body']}\n")

        if not results:
            return f"✗ No results found for: {query}"

        return f"✓ Search results for '{query}':\n\n" + "\n".join(results)

    except ImportError:
        return "✗ duckduckgo_search not installed. Run: pip install duckduckgo-search"
    except Exception as e:
        return f"✗ Search error: {str(e)}"


@battlefield_tool(
    name="fetch_url",
    description="Fetch content from a URL",
    category="web",
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to fetch"},
        "method": {"type": "string", "required": False, "description": "HTTP method (default: GET)"},
        "headers": {"type": "object", "required": False, "description": "HTTP headers"}
    }
)
def fetch_url(url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None) -> str:
    """Fetch content from a URL"""
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            timeout=10
        )

        output = []
        output.append(f"✓ {method} {url}")
        output.append(f"Status: {response.status_code}")
        output.append(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
        output.append(f"\n{response.text[:2000]}")

        if len(response.text) > 2000:
            output.append(f"\n... (truncated, total: {len(response.text)} chars)")

        return "\n".join(output)

    except Exception as e:
        return f"✗ Error fetching {url}: {str(e)}"


@battlefield_tool(
    name="scrape_page",
    description="Scrape and parse HTML from a web page",
    category="web",
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to scrape"},
        "selector": {"type": "string", "required": False, "description": "CSS selector to extract"}
    }
)
def scrape_page(url: str, selector: Optional[str] = None) -> str:
    """Scrape a web page"""
    try:
        from bs4 import BeautifulSoup

        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        if selector:
            elements = soup.select(selector)
            if not elements:
                return f"✗ No elements found for selector: {selector}"

            results = [f"✓ Found {len(elements)} elements for '{selector}':\n"]
            for i, elem in enumerate(elements[:10]):
                results.append(f"{i+1}. {elem.get_text(strip=True)[:200]}")

            return "\n".join(results)
        else:
            text = soup.get_text(separator='\n', strip=True)
            return f"✓ Scraped {url}:\n\n{text[:3000]}"

    except ImportError:
        return "✗ beautifulsoup4 not installed. Run: pip install beautifulsoup4"
    except Exception as e:
        return f"✗ Scraping error: {str(e)}"


@battlefield_tool(
    name="browser_screenshot",
    description="Take a screenshot of a web page using headless browser",
    category="web",
    requires_confirmation=True,
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to screenshot"},
        "output_path": {"type": "string", "required": True, "description": "Output file path (.png)"},
        "full_page": {"type": "boolean", "required": False, "description": "Capture full page (default: False)"}
    }
)
async def browser_screenshot(url: str, output_path: str, full_page: bool = False) -> str:
    """Take a screenshot of a web page"""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)
            await page.screenshot(path=output_path, full_page=full_page)
            await browser.close()

        return f"✓ Screenshot saved to {output_path}"

    except ImportError:
        return "✗ playwright not installed. Run: pip install playwright && playwright install"
    except Exception as e:
        return f"✗ Screenshot error: {str(e)}"


@battlefield_tool(
    name="browser_execute",
    description="Execute JavaScript in a headless browser and return result",
    category="web",
    requires_confirmation=True,
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to visit"},
        "script": {"type": "string", "required": True, "description": "JavaScript code to execute"}
    }
)
async def browser_execute(url: str, script: str) -> str:
    """Execute JavaScript in a browser"""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)
            result = await page.evaluate(script)
            await browser.close()

        return f"✓ Script result:\n{result}"

    except ImportError:
        return "✗ playwright not installed. Run: pip install playwright && playwright install"
    except Exception as e:
        return f"✗ Execution error: {str(e)}"


@battlefield_tool(
    name="download_file",
    description="Download a file from a URL",
    category="web",
    parameters={
        "url": {"type": "string", "required": True, "description": "URL to download"},
        "output_path": {"type": "string", "required": True, "description": "Output file path"}
    }
)
def download_file(url: str, output_path: str) -> str:
    """Download a file"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size = len(response.content)
        return f"✓ Downloaded {size} bytes to {output_path}"

    except Exception as e:
        return f"✗ Download error: {str(e)}"
