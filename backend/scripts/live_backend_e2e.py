"""Exercise signup -> HTTP setup -> WebSocket -> real free LLM -> file tools.

All application data and code under test are disposable. The transport rejects
non-OpenRouter hosts, paid models, and provider-side fallback model lists.
Run: python scripts/live_backend_e2e.py --model openrouter/free
"""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def get_key(backend):
    key = os.getenv("OPENROUTER_API_KEY", "")
    config_file = Path(os.getenv("CAROLE_HOME_DIR", str(Path.home() / ".carole"))) / "config.json"
    if config_file.exists():
        key = json.loads(config_file.read_text(encoding="utf-8")).get("api_keys", {}).get("openrouter") or key
    if not key:
        from dotenv import dotenv_values
        for path in (backend / ".env", backend.parent / ".env"):
            if path.exists():
                key = dotenv_values(path).get("OPENROUTER_API_KEY") or key
    return key


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="openrouter/free")
    parser.add_argument("--report", default="audit/live-backend-e2e.json")
    parser.add_argument("--scenario", choices=("addition", "pagination"), default="addition")
    args = parser.parse_args()
    if args.model != "openrouter/free" and not args.model.endswith(":free"):
        parser.error("Only openrouter/free or explicit :free models are permitted")
    backend = Path(__file__).resolve().parents[1]
    report_path = (backend / args.report).resolve()
    key = get_key(backend)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"requested_model": args.model, "scenario": args.scenario, "status": "running", "provider_requests": [], "checks": {}}
    if not key:
        report.update(status="blocked", reason="No OpenRouter key configured")
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Live test blocked: no OpenRouter key configured.")
        return 2
    with tempfile.TemporaryDirectory(prefix="carole-live-e2e-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()
        home = root / "carole"
        home.mkdir()
        source_name, test_name = "calculator.py", "test_calculator.py"
        source = "def add(a, b):\n    return a - b\n"
        test_source = """import unittest
from calculator import add
class AdditionTest(unittest.TestCase):
    def test_positive(self): self.assertEqual(add(2, 3), 5)
    def test_negative(self): self.assertEqual(add(-2, -3), -5)
    def test_identity(self): self.assertEqual(add(0, 9), 9)
    def test_decimal(self): self.assertAlmostEqual(add(1.25, 2.5), 3.75)
if __name__ == '__main__': unittest.main()
"""
        task = "Fix the addition bug"
        if args.scenario == "pagination":
            source_name, test_name = "catalog.py", "test_catalog.py"
            source = "def list_items(items, page=1, page_size=2):\n    rows = items[(page-1)*page_size:page*page_size]\n    return [row for row in rows if not row.get('private', False)]\n"
            test_source = '''import unittest
from catalog import list_items
class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.items = [{'id': 0, 'private': True}, {'id': 1}, {'id': 2}, {'id': 3, 'private': True}, {'id': 4}]
    def test_full_first_page(self): self.assertEqual([r['id'] for r in list_items(self.items)], [1, 2])
    def test_next_page(self): self.assertEqual([r['id'] for r in list_items(self.items, 2)], [4])
    def test_empty_page(self): self.assertEqual(list_items(self.items, 3), [])
    def test_input_unchanged(self):
        import copy
        before = copy.deepcopy(self.items)
        list_items(self.items)
        self.assertEqual(self.items, before)
    def test_page_validation(self):
        for page in (0, -1, 1.5, True):
            with self.subTest(page=page), self.assertRaises(ValueError): list_items(self.items, page)
    def test_size_validation(self):
        for size in (0, -1, 1.5, True):
            with self.subTest(size=size), self.assertRaises(ValueError): list_items(self.items, page_size=size)
if __name__ == '__main__': unittest.main()
'''
            task = "Fix public-item pagination and validate that page and page_size are positive integers (booleans are invalid). Preserve input order and never mutate caller data"
        (workspace / source_name).write_text(source, encoding="utf-8")
        (workspace / test_name).write_text(test_source, encoding="utf-8")
        env = {"CAROLE_HOME_DIR": str(home), "DATABASE_URL": f"sqlite+aiosqlite:///{(root / 'live.db').as_posix()}",
               "WORKSPACE_ROOT": str(workspace), "ENV": "test", "ENVIRONMENT": "test",
               "JWT_SECRET": "disposable-e2e-auth-secret-never-used-in-production", "FORCE_DB_RECREATE": "false",
               "PYTHON_DOTENV_DISABLED": "1", "ENABLE_OPENLLMETRY": "false", "OPENROUTER_API_KEY": key,
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "BROWSER_USE_CONFIG_DIR": str(root / "browser"),
               "ANONYMIZED_TELEMETRY": "false", "BROWSER_USE_CLOUD_SYNC": "false"}
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY", "NVIDIA_API_KEY", "TAVILY_API_KEY"):
            env[name] = ""
        config = {"api_keys": {"openrouter": key},
                  "default_models": {name: args.model for name in ("DEFAULT_FAST_MODEL", "DEFAULT_SMART_MODEL", "DEFAULT_CODER_MODEL", "DEFAULT_JUDGE_MODEL")},
                  "agent_settings": {"MAX_LOOPS": 8},
                  "access_control": {"enable_judge": False, "judge_fallback": "allow", "categories": {category: "allow" for category in ("view", "edit", "create", "execute", "git")}}}
        (home / "config.json").write_text(json.dumps(config), encoding="utf-8")
        sys.path.insert(0, str(backend))
        with patch.dict(os.environ, env), patch.object(Path, "home", return_value=root):
            import httpx
            import core.config
            core.config.GLOBAL_MCPS = []
            core.config.MAX_LOOPS = 8
            core.config.MAX_BUDGET_TOKENS = 100000
            from main import app
            from core.llm.multi_model_router import llm_router
            from fastapi.testclient import TestClient

            class FreeOnlyTransport(httpx.AsyncBaseTransport):
                def __init__(self):
                    self.real = httpx.AsyncHTTPTransport()

                async def handle_async_request(self, request):
                    if request.url.host != "openrouter.ai" or request.method != "POST":
                        raise RuntimeError("Live E2E blocked a request outside OpenRouter")
                    payload = json.loads(request.content)
                    model = payload.get("model", "")
                    if model != "openrouter/free" and not model.endswith(":free"):
                        raise RuntimeError("Live E2E blocked a paid model")
                    if payload.get("models") or payload.get("route") == "fallback":
                        raise RuntimeError("Live E2E blocked provider-side model fallback")
                    if len(report["provider_requests"]) >= 12:
                        raise RuntimeError("Live E2E request budget exhausted")
                    if "max_tokens" in payload:
                        payload["max_tokens"] = min(payload["max_tokens"], 2048)
                    record = {"model": model, "path": request.url.path, "max_tokens": payload.get("max_tokens")}
                    report["provider_requests"].append(record)
                    outgoing = httpx.Request(request.method, request.url, headers={name: value for name, value in request.headers.items() if name.lower() != "content-length"}, json=payload, extensions=request.extensions)
                    response = await self.real.handle_async_request(outgoing)
                    record["http_status"] = response.status_code
                    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                    return response

                async def aclose(self):
                    await self.real.aclose()

            llm_router._http_client = httpx.AsyncClient(transport=FreeOnlyTransport(), timeout=45)
            # Ticket URLs and Authorization headers never enter the evidence report.
            logging.getLogger("httpx").setLevel(logging.WARNING)
            try:
                with TestClient(app) as client:
                    def post(path, body, headers=None):
                        response = client.post(path, json=body, headers=headers)
                        if response.status_code != 200:
                            raise AssertionError(f"{path} returned HTTP {response.status_code}")
                        return response.json()
                    account = post("/api/auth/signup", {"email": "e2e@example.com", "password": "Disposable123!", "first_name": "E2E", "last_name": "User"})
                    headers = {"Authorization": "Bearer " + account["token"]}
                    project = post("/api/projects", {"name": "Live reliability test", "custom_workspace_path": str(workspace)}, headers)
                    team = post("/api/teams", {"name": "E2E", "project_id": project["id"]}, headers)
                    agent = post("/api/agents", {"name": "Verifier", "role": "developer", "team_id": team["id"], "model": args.model,
                        "system_prompt": "You are a coding agent. Use tools to inspect, fix, and test code. Report only verified outcomes.",
                        "tool_permissions": {"read_file": "allow", "edit_file": "allow", "execute_command": "allow", "write_file": "allow"}}, headers)
                    report["checks"]["authenticated_setup"] = True
                    ticket = post("/api/auth/ws-ticket", {}, headers)["ticket"]
                    event_types, tool_names, finals = [], [], []
                    with client.websocket_connect(f"/ws/chat/{team['id']}?ticket={ticket}") as ws:
                        deadline = time.monotonic() + 240
                        async def receive_bounded():
                            import anyio
                            with anyio.fail_after(max(0.1, deadline - time.monotonic())):
                                packet = await ws._send_rx.receive()
                                ws._raise_on_close(packet)
                                return json.loads(packet["text"])
                        try:
                            command = f'"{sys.executable}" -m unittest {test_name} -v'
                            prompt = f"@Verifier {task} in {source_name}. Read {source_name} and {test_name}, edit only {source_name}, then run {command}. Do not modify tests. Use read_file, edit_file and execute_command. Finish with the actual test outcome. No plan approval is needed for this disposable fixture."
                            ws.send_json({"text": prompt})
                            while True:
                                event = client.portal.call(receive_bounded)
                                if event.get("type") in ("tool_start", "tool_end", "agent_error", "message"):
                                    report.setdefault("events", []).append({key: event.get(key) for key in ("type", "tool_name", "is_error", "text", "observation", "is_intermediate")})
                                    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
                                kind = event.get("type")
                                event_types.append(kind)
                                if kind == "tool_start":
                                    tool_names.append(event.get("tool_name"))
                                if kind == "message" and event.get("sender_id") == agent["id"] and not event.get("is_intermediate"):
                                    finals.append(event.get("text", ""))
                                if kind == "agent_status" and event.get("sender_id") == agent["id"] and event.get("status") == "idle":
                                    break
                        finally:
                            from core.chat.message_router import message_router
                            client.portal.call(message_router.cancel_agent, agent["id"], True)
                    report["event_types"] = sorted(set(event_types))
                    report["tools_used"] = tool_names
                    report["checks"]["native_tools_executed"] = "read_file" in tool_names and "edit_file" in tool_names
                    report["checks"]["tests_unchanged"] = (workspace / test_name).read_text(encoding="utf-8") == test_source
                    verification = subprocess.run([sys.executable, "-m", "unittest", test_name, "-v"], cwd=workspace, capture_output=True, text=True, timeout=30)
                    report["checks"]["independent_test_execution"] = verification.returncode == 0
                    report["verification"] = verification.stderr.replace(str(workspace), "<fixture>")
                    messages_response = client.get(f"/api/messages/{team['id']}", headers=headers)
                    if messages_response.status_code != 200:
                        raise AssertionError("Could not reload persisted conversation")
                    stored = messages_response.json()
                    report["checks"]["final_message_persisted"] = bool(finals) and any(row.get("text") == finals[-1] for row in stored)
                    report["status"] = "passed" if all(report["checks"].values()) else "failed"
            except Exception as exc:
                report.update(status="failed", exception_type=type(exc).__name__)
            finally:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Live E2E: {report['status']}; report: {report_path}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
