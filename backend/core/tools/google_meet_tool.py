"""
# backend/core/tools/google_meet_tool.py

DOM-based Google Meet workflow (zero-cost Captions + Native Chat).
Uses Playwright to navigate, inject a MutationObserver for captions, and automate the chat box.
"""

from core.chat.event_bus import event_bus
from core.tools.browser_tool import browser_tool
import asyncio

class GoogleMeetTool:
    async def join_google_meet(self, url: str, agent_id: str, agent_name: str, team_id: str) -> str:
        """
        Navigates to the Google Meet URL and injects a MutationObserver to listen for captions.
        """
        try:
            from core.tools.browser_pool import get_page
            # First navigate using the browser pool/tool
            nav_result = await browser_tool.navigate(url, agent_id, agent_name, team_id)
            page = await get_page(agent_id)

            # Define the Python callback for the binding
            async def handle_meet_caption(source, text: str):
                if text and text.strip():
                    await event_bus.publish(f"team:{team_id}", {
                        "type": "message",
                        "sender_id": "google_meet",
                        "sender_name": "Meeting Transcript",
                        "is_meeting_transcript": True,
                        "text": text.strip()
                    })

            # Expose the binding so JS can call window.onMeetCaption(text)
            # Use try-except in case it's already bound from a previous join
            try:
                await page.expose_binding("onMeetCaption", handle_meet_caption)
            except Exception as e:
                # If it's already exposed, it will throw an error. We can ignore it.
                pass

            # Inject the MutationObserver
            # Note: Google Meet selectors may change! 
            # '.VfPpkd-vQzf8d' is a known generic/best-effort class for captions.
            script = """
            () => {
                if (window.__meetObserver) {
                    window.__meetObserver.disconnect();
                }
                const observer = new MutationObserver((mutations) => {
                    for (const mutation of mutations) {
                        if (mutation.type === 'childList') {
                            for (const node of mutation.addedNodes) {
                                if (node.nodeType === 1) { // ELEMENT_NODE
                                    if (node.matches && node.matches('.VfPpkd-vQzf8d')) {
                                        window.onMeetCaption(node.innerText);
                                    } else if (node.querySelectorAll) {
                                        const captions = node.querySelectorAll('.VfPpkd-vQzf8d');
                                        captions.forEach(c => window.onMeetCaption(c.innerText));
                                    }
                                }
                            }
                        }
                    }
                });
                observer.observe(document.body, { childList: true, subtree: true });
                window.__meetObserver = observer;
            }
            """
            await page.evaluate(script)

            return f"Successfully joined Google Meet at {url}. Caption observer injected.\nBrowser output: {nav_result}"

        except Exception as e:
            return f"Error joining Google Meet: {str(e)}"


    async def send_google_meet_chat(self, text: str, agent_id: str) -> str:
        """
        Sends a message to the Google Meet chat by automating the UI.
        """
        try:
            from core.tools.browser_pool import get_page
            page = await get_page(agent_id)

            # Attempt to click the chat button if chat isn't open
            # Typically aria-label="Chat with everyone" or similar
            try:
                # This selector might need adjusting. 
                # Wait for a short time, if it fails, maybe chat is already open.
                chat_btn = page.locator('button[aria-label*="chat" i], button[aria-label*="Chat" i]').first
                if await chat_btn.is_visible(timeout=2000):
                    await chat_btn.click(timeout=2000)
            except Exception:
                pass # Chat might already be open or button not found

            # Wait a moment for chat panel to open
            await asyncio.sleep(1)

            # Find the chat textarea
            # It's usually a textarea in the chat panel. We use a best-effort generic selector.
            chat_input = page.locator('textarea[name="chatTextInput"], textarea[aria-label*="chat" i], textarea').last
            
            await chat_input.fill(text, timeout=5000)
            await chat_input.press("Enter", timeout=5000)

            return f"Sent chat message: '{text}'"

        except Exception as e:
            return f"Error sending Google Meet chat: {str(e)}"

# Singleton
google_meet_tool = GoogleMeetTool()
