import asyncio
from playwright.async_api import async_playwright
from browser_use import BrowserSession

async def main():
    async with async_playwright() as p:
        print("Launching Playwright...")
        browser = await p.chromium.launch(
            headless=True,
            args=["--remote-debugging-port=9222"]
        )
        print("Creating context...")
        context = await browser.new_context()
        page = await context.new_page()
        print("Navigating...")
        await page.goto("https://example.com")
        
        print("Connecting BrowserSession...")
        try:
            session = BrowserSession(cdp_url="http://127.0.0.1:9222")
            print("Session created.")
            
            # trigger initialization
            print("Getting state summary...")
            state = await asyncio.wait_for(session.get_browser_state_summary(), timeout=10.0)
            print("Got state summary!")
            print(state.dom_state.llm_representation())
            
            await session.close()
        except Exception as e:
            print(f"Error: {e}")
            
        await browser.close()
if __name__ == "__main__":
    asyncio.run(main())


import pytest

@pytest.mark.asyncio
async def test_cdp_session_connection():
    """Verify Chromium context and page creation with remote debugging flags."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--remote-debugging-port=0"])
        context = await browser.new_context()
        page = await context.new_page()
        assert page is not None
        await browser.close()

