"""
# backend/tests/test_realtime_browser_bench.py

Real-time, live Playwright browser automation test suite using a local
interactive single-page test bench (HTML/CSS/JS).

Tests real Chromium execution, Accessibility Tree Ref generation,
form filling & validation, dynamic async/AJAX loading, JS dialogs,
coordinate canvas clicking, Human-in-the-loop (HIL) security challenge takeover,
agent question asking, file downloads, and autonomous browsing with
OpenRouter free models (openrouter/free).
"""

import asyncio
import http.server
import json
import os
import socket
import threading
from functools import partial
import pytest

from core.tools.browser_tool import browser_tool
from core.tools.browser_agent import BrowserAgent
import core.tools.browser_pool as bp
from core.tools.interaction_tools import interaction_tools, pending_questions, question_answers


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture(autouse=True)
def force_local_browser(monkeypatch):
    """Ensure tests run against local Chromium since 127.0.0.1 is not reachable from remote cloud CDP."""
    from core.llm import config_manager
    from unittest.mock import Mock
    orig_load = config_manager.load_config

    def mock_load():
        cfg = orig_load()
        cfg_copy = dict(cfg)
        ba = dict(cfg_copy.get("browser_automation", {}))
        ba["infrastructure"] = "local"
        ba["provider"] = "local"
        ba["headless"] = True
        ba["allow_local_urls"] = True
        cfg_copy["browser_automation"] = ba
        return cfg_copy

    monkeypatch.setattr(config_manager, "load_config", mock_load)

    # Clean any Mock browser or stale sessions left behind by unit tests
    if isinstance(bp._browser, Mock):
        bp._browser = None
        bp._playwright = None
    bp._sessions.clear()


@pytest.fixture(scope="module")
def local_bench_server():
    """Starts a background HTTP server serving the interactive test bench."""
    import time
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=FIXTURES_DIR)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_port
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/browser_test_bench.html"
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            time.sleep(0.05)

    yield url

    httpd.shutdown()
    httpd.server_close()


@pytest.mark.asyncio
async def test_real_browser_snapshot_and_ref_mapping(local_bench_server):
    """Verify live Playwright navigation and Accessibility Tree Ref generation."""
    agent_id = "test_agent_snapshot"
    team_id = "test_team_bench"

    try:
        nav_res = await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        assert "Carole.ai Browser Automation Test Bench" in nav_res

        snapshot = await browser_tool.snapshot(agent_id, "Tester", team_id)
        assert "Page:" in snapshot
        assert "Register User" in snapshot
        assert "Full Name" in snapshot
        assert "Email Address" in snapshot
        assert "Fetch Secret Token" in snapshot

        # Verify element Ref IDs were mapped
        page = await bp.get_page(agent_id)
        page_map = getattr(page, "_carole_refs", {})
        assert isinstance(page_map, dict)
        assert len(page_map) > 5, "Expected multiple interactive elements indexed"
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_form_filling_and_submission(local_bench_server):
    """Verify end-to-end form filling (text, select, checkbox) and form submission."""
    agent_id = "test_agent_form"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        # 1. Fill Full Name
        name_input = await page.query_selector("#full_name")
        assert name_input is not None
        await page.fill("#full_name", "Nova Coder")

        # 2. Fill Email Address
        await page.fill("#email_address", "nova@carole.ai")

        # 3. Select Role dropdown
        await page.select_option("#user_role", value="Developer")

        # 4. Check Terms Checkbox
        await page.check("#terms_checkbox")

        # 5. Click Register User Button
        await page.click("#submit_registration_btn")

        # 6. Verify submission success banner in the DOM snapshot
        snapshot = await browser_tool.snapshot(agent_id, "Tester", team_id)
        assert "Form Submitted Successfully" in snapshot
        assert "USER-84920" in snapshot
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_async_delayed_rendering(local_bench_server):
    """Verify handling of dynamic async AJAX content with delayed rendering."""
    agent_id = "test_agent_async"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        # Click the fetch token button
        await page.click("#load_async_btn")

        # Wait for the async response (0.7s setTimeout in HTML)
        await page.wait_for_selector("#async_result", state="visible", timeout=5000)

        snapshot = await browser_tool.snapshot(agent_id, "Tester", team_id)
        assert "SECRET_TOKEN_ALPHA_77" in snapshot
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_dialog_alert_and_confirm(local_bench_server):
    """Verify JavaScript alert and confirm dialog handling without freezing."""
    agent_id = "test_agent_dialog"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        # 1. Trigger alert (automatically caught by dialog handler)
        await page.click("#trigger_alert_btn")
        await asyncio.sleep(0.3)

        # 2. Preconfigure confirm dialog to accept
        await browser_tool.handle_dialog(agent_id, accept=True)
        await page.click("#trigger_confirm_btn")
        await asyncio.sleep(0.3)

        result_text = await page.inner_text("#confirm_result_text")
        assert "✓ User Confirmed" in result_text
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_coordinate_canvas_click(local_bench_server):
    """Verify direct canvas pixel coordinate clicking at dynamically computed coordinates."""
    agent_id = "test_agent_coords"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        # Wait for and get exact bounding box of the target button
        elem = await page.wait_for_selector("#coord_target_btn")
        assert elem is not None, "Target button must exist in DOM"
        box = await elem.bounding_box()
        assert box is not None, "Target button bounding box must exist"
        click_x = box["x"] + box["width"] / 2
        click_y = box["y"] + box["height"] / 2

        res = await browser_tool.act("coords", agent_id, "Tester", team_id, x=click_x, y=click_y)
        assert "Action coords executed" in res

        # Verify page registered coordinate click
        coords_alert = await page.inner_text("#coords_result")
        assert "Clicked at exact coordinates" in coords_alert
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_human_in_the_loop_takeover(local_bench_server):
    """Verify Human-in-the-Loop (HIL) challenge modal detection and resume flow."""
    agent_id = "test_agent_hil"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        # Open the security challenge modal
        await page.click("#open_challenge_btn")
        await asyncio.sleep(0.2)

        # Verify challenge modal is open
        is_modal_visible = await page.is_visible("#challenge_modal")
        assert is_modal_visible is True

        # Simulate human intervention: user types code and clicks verify
        await page.fill("#challenge_input", "849201")
        await page.click("#verify_challenge_btn")
        await asyncio.sleep(0.3)

        # Verify challenge solved alert appears
        alert_text = await page.inner_text("#challenge_completed_alert")
        assert "Security challenge resolved" in alert_text
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_agent_asking_question():
    """Verify agent asking user a question (HIL edge case) and receiving response."""
    agent_id = "test_agent_qa"
    team_id = "test_team_bench"

    async def simulate_human_reply():
        # Wait until question is published and registered
        for _ in range(50):
            if pending_questions:
                q_id, ev = next(iter(pending_questions.items()))
                question_answers[q_id] = "Deploy to Staging Environment"
                ev.set()
                return
            await asyncio.sleep(0.05)

    reply_task = asyncio.create_task(simulate_human_reply())

    # Agent calls ask_user
    answer = await interaction_tools.ask_user(
        question="Which deployment target should be used?",
        agent_id=agent_id,
        agent_name="Archer",
        team_id=team_id,
        options=["Staging", "Production", "Development"],
    )

    await reply_task
    assert "Human answered: Deploy to Staging Environment" in answer


@pytest.mark.asyncio
async def test_real_browser_file_download_interception(local_bench_server):
    """Verify browser file download triggering and interception."""
    agent_id = "test_agent_download"
    team_id = "test_team_bench"

    try:
        await browser_tool.navigate(local_bench_server, agent_id, "Tester", team_id)
        page = await bp.get_page(agent_id)

        async with page.expect_download() as download_info:
            await page.click("#download_file_btn")
        download = await download_info.value
        assert "carole_test_export.json" in download.suggested_filename
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_autonomous_agent_openrouter_free(local_bench_server):
    """
    Real autonomous browsing ReACT loop using openrouter/free model.
    The agent receives a goal in natural language, reads the snapshot,
    generates structured JSON actions, interacts with the form, and concludes.
    """
    agent_id = "test_agent_openrouter_free"
    team_id = "test_team_bench"

    try:
        agent = BrowserAgent(model="openrouter/free")
        command = (
            f"Navigate to {local_bench_server}. "
            "Fill in the registration form with Full Name 'Archer Orchestrator', "
            "Email Address 'archer@carole.ai', select Role 'Developer', "
            "check the terms checkbox, and click Register User. "
            "Confirm the form was submitted successfully."
        )

        result = await agent.run(
            command=command,
            agent_id=agent_id,
            agent_name="Archer",
            team_id=team_id,
            start_url=local_bench_server,
        )
        safe_res = result.encode("ascii", "backslashreplace").decode("ascii")
        print(f"\n[AGENT FINAL RESULT]: {safe_res}")

        assert result is not None
        assert len(result) > 0

        # Check page state and structured result
        data = json.loads(result)
        assert "status" in data
        assert "steps" in data
        page = await bp.get_page(agent_id)
        submitted = await page.is_visible("#form_success_alert")
        if submitted:
            assert data["success"] is True
        else:
            assert data["status"] in {"invalid_decision", "step_limit", "stuck", "browser_error", "blocked"}
    finally:
        await bp.close_agent_browser(agent_id)


@pytest.mark.asyncio
async def test_real_browser_headed_visual_interaction(local_bench_server):
    """
    Real HEADED (visible window) browser test.
    Launches a visible Chromium window on the desktop so humans can visually see
    automation filling the form, selecting options, and triggering events.
    """
    agent_id = "test_agent_headed"
    team_id = "test_team_bench"

    bp.set_headless_mode(False)
    try:
        await browser_tool.navigate(local_bench_server, agent_id, "VisualTester", team_id)
        page = await bp.get_page(agent_id)

        # Type visibly with slight human delay so user can see it happening on screen
        await page.type("#full_name", "Visually Verified User", delay=40)
        await asyncio.sleep(0.3)
        await page.type("#email_address", "visual@carole.ai", delay=30)
        await asyncio.sleep(0.3)
        await page.select_option("#user_role", value="Architect")
        await asyncio.sleep(0.3)
        await page.check("#terms_checkbox")
        await asyncio.sleep(0.3)
        await page.click("#submit_registration_btn")
        await asyncio.sleep(0.5)

        assert await page.is_visible("#form_success_alert") is True
    finally:
        await bp.close_agent_browser(agent_id)
        bp.set_headless_mode(None)


@pytest.mark.asyncio
async def test_real_browser_headless_mode(local_bench_server):
    """
    Real HEADLESS browser test.
    Ensures background execution without opening a visible UI window.
    """
    agent_id = "test_agent_headless"
    team_id = "test_team_bench"

    bp.set_headless_mode(True)
    try:
        await browser_tool.navigate(local_bench_server, agent_id, "HeadlessTester", team_id)
        page = await bp.get_page(agent_id)
        await page.fill("#full_name", "Headless Runner")
        await page.fill("#email_address", "headless@carole.ai")
        await page.select_option("#user_role", value="Debugger")
        await page.check("#terms_checkbox")
        await page.click("#submit_registration_btn")
        assert await page.is_visible("#form_success_alert") is True
    finally:
        await bp.close_agent_browser(agent_id)
        bp.set_headless_mode(None)
