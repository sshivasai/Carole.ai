"""
# backend/scripts/run_browser_automation.py

Standalone Playwright browser automation runner following the playwright-automation skill.
Automates end-to-end interactions against the Carole.ai real-time test bench.

Usage:
  python backend/scripts/run_browser_automation.py            # Runs in HEADED mode (visible window)
  python backend/scripts/run_browser_automation.py --headless # Runs in HEADLESS background mode
"""

import argparse
import http.server
import os
import socket
import sys
import threading
import time
from functools import partial

# Ensure UTF-8 output encoding across Windows consoles
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from playwright.sync_api import sync_playwright, expect

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures")


def start_test_server():
    """Starts an ephemeral background HTTP server serving the interactive test bench."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=FIXTURES_DIR)
    httpd = http.server.HTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/browser_test_bench.html"
    return httpd, url


def run_automation(headed: bool = True):
    print("=" * 65)
    print("🚀 Carole.ai Playwright Automation Runner")
    print(f"   Mode: {'HEADED (Visible Window)' if headed else 'HEADLESS (Background)'}")
    print("=" * 65)

    httpd, url = start_test_server()
    print(f"📡 Test server started at: {url}\n")

    with sync_playwright() as p:
        print("🌐 Launching Chromium browser...")
        browser = p.chromium.launch(
            headless=not headed,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,900",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            # 1. Navigation
            print("1️⃣ Navigating to test bench...")
            page.goto(url)
            expect(page).to_have_title("Carole.ai Browser Automation Test Bench")
            print("   ✓ Page loaded successfully.")
            if headed:
                time.sleep(0.5)

            # 2. Form Filling with robust role/label locators
            print("\n2️⃣ Filling User Registration Form...")
            page.get_by_label("Full Name").fill("Ada Lovelace")
            if headed:
                time.sleep(0.3)

            page.get_by_label("Email Address").fill("ada@carole.ai")
            if headed:
                time.sleep(0.3)

            page.get_by_label("Role / Specialization").select_option("Architect")
            if headed:
                time.sleep(0.3)

            page.get_by_label("I agree to terms and conditions").check()
            if headed:
                time.sleep(0.3)

            page.get_by_role("button", name="Register User").click()
            expect(page.locator("#form_success_alert")).to_be_visible()
            user_id = page.locator("#registered_user_id").inner_text()
            print(f"   ✓ Form submitted successfully! Assigned User ID: {user_id}")
            if headed:
                time.sleep(0.5)

            # 3. Dynamic Async Loading
            print("\n3️⃣ Testing Dynamic Async AJAX Loader...")
            page.get_by_role("button", name="Fetch Secret Token").click()
            expect(page.locator("#async_result")).to_be_visible(timeout=5000)
            token = page.locator("#token_val").inner_text()
            print(f"   ✓ Async content loaded! Secret Token: {token}")
            if headed:
                time.sleep(0.5)

            # 4. JavaScript Dialog Handling
            print("\n4️⃣ Testing JavaScript Dialogs...")
            page.once("dialog", lambda d: d.accept())
            page.get_by_role("button", name="Trigger Confirm").click()
            expect(page.locator("#confirm_result_text")).to_contain_text("✓ User Confirmed")
            print("   ✓ Confirm dialog intercepted and accepted cleanly.")
            if headed:
                time.sleep(0.5)

            # 5. Human-in-the-Loop (HIL) Security Challenge Takeover
            print("\n5️⃣ Testing Human-in-the-Loop (HIL) Bot Challenge...")
            page.get_by_role("button", name="Trigger Bot Challenge Modal").click()
            expect(page.locator("#challenge_modal")).to_be_visible()
            print("   ℹ️ Bot verification challenge opened.")
            if headed:
                time.sleep(0.5)

            page.locator("#challenge_input").fill("849201")
            page.get_by_role("button", name="Verify & Continue").click()
            expect(page.locator("#challenge_completed_alert")).to_be_visible()
            print("   ✓ Security challenge resolved and session verified.")
            if headed:
                time.sleep(0.5)

            # 6. Coordinate Canvas Clicking
            print("\n6️⃣ Testing Coordinate Canvas Clicking...")
            btn = page.locator("#coord_target_btn")
            btn.scroll_into_view_if_needed()
            box = btn.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                expect(page.locator("#coords_result")).to_be_visible()
                print(f"   ✓ Dispatched click at exact coordinates ({int(box['x'])}, {int(box['y'])}).")
            if headed:
                time.sleep(0.5)

            # 7. File Download Interception
            print("\n7️⃣ Testing File Download Interception...")
            with page.expect_download() as download_info:
                page.get_by_role("button", name="Download Test Export (.json)").click()
            download = download_info.value
            print(f"   ✓ Intercepted download: {download.suggested_filename}")
            if headed:
                time.sleep(1.0)

            print("\n" + "=" * 65)
            print("🎉 ALL PLAYWRIGHT AUTOMATION STEPS COMPLETED SUCCESSFULLY!")
            print("=" * 65)

        except Exception as e:
            print(f"\n❌ Automation failed with error: {e}", file=sys.stderr)
            raise
        finally:
            print("\n🧹 Cleaning up browser resources...")
            context.close()
            browser.close()
            httpd.shutdown()
            print("✓ Cleanup complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Carole.ai Playwright Automation")
    parser.add_argument("--headless", action="store_true", help="Run in headless background mode")
    args = parser.parse_args()

    run_automation(headed=not args.headless)
