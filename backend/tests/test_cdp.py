import asyncio
from playwright.async_api import async_playwright
from browser_use import BrowserSession

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--remote-debugging-port=9222"]
        )
        page = await browser.new_page()
        await page.goto("https://example.com")
        
        print("Connected to Playwright.")
        
        session = BrowserSession(cdp_url="http://127.0.0.1:9222")
        
        print("Connected to BrowserUse.")
        
        state = await session.get_browser_state_summary()
        print("Got State:")
        print(state.dom_state.llm_representation())
        
        await browser.close()
        await session.close()
if __name__ == "__main__":
    asyncio.run(main())


import pytest

@pytest.mark.asyncio
async def test_cdp_remote_debugging_port():
    """Verify Chromium launches and connects with CDP port."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--remote-debugging-port=0"])
        assert browser.is_connected()
        await browser.close()

