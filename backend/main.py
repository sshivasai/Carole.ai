"""
# backend/main.py

This is the main entrypoint for the FastAPI backend of Carole.ai.

Responsibilities:
1. Initialize the FastAPI application with lifespan events.
2. Configure WebSocket endpoints for the EventBus (frontend <-> backend real-time communication).
3. Initialize the database connection pool (SQLite + aiosqlite).
4. Register HTTP API routes for Team Management, Agent Configuration, and Approvals.
5. Startup background workers (AutoDream memory consolidation worker).
6. Register built-in tools and load plugin tools from the /plugins/ directory.
"""

import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
import dotenv
import os
dotenv.load_dotenv()

from core.memory.database import init_db, async_session
from core.chat.event_bus import event_bus
from core.chat.message_router import message_router
from core.memory.auto_dream import dream_worker
from core.tools.tool_executor import register_builtin_tools
from core.tools.tool_registry import ToolRegistry
from core.api.crud_routes import router as crud_router
from core.api.cost_routes import router as cost_router
from core.api.auth_routes import router as auth_router
from core.api.google_auth_routes import router as google_auth_router
from core.api.file_routes import router as file_router
from core.api.terminal_ws import router as terminal_router
from core.api.git_routes import router as git_router
from core.api.search_routes import router as search_router
from core.api.plugin_routes import router as plugin_router
from core.api.skill_routes import router as skill_router
from core.api.model_routes import router as model_router
from core.api.scratchpad_routes import router as scratchpad_router

import logging
import importlib
from typing import Optional, List
from core.auth.auth_middleware import require_auth

# Rate limiting (Finding #7)
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    _limiter = Limiter(key_func=get_remote_address)
    _SLOWAPI_AVAILABLE = True
except ImportError:
    _SLOWAPI_AVAILABLE = False
    _limiter = None
    logging.getLogger("carole").warning(
        "slowapi not installed — rate limiting disabled. Run: pip install slowapi"
    )

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("carole")

# --- Lifespan context manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    from core.auth.auth_service import validate_auth_config
    validate_auth_config()

    logger.info("🚀 [Lifespan] Initializing Database Connection Pool...")
    try:
        await init_db()
        logger.info("✓ [Lifespan] Database initialized successfully!")
    except Exception as e:
        logger.error("✗ [Lifespan] Error initializing database: %s", e)

    # Register built-in tools with the dynamic ToolRegistry
    logger.info("🔧 [Lifespan] Registering built-in tools...")
    register_builtin_tools()

    # Load plugin tools from ~/.carole/plugins and backend/plugins
    from core.config import PLUGINS_DIR
    import os
    import shutil
    
    repo_plugins_dir = os.path.join(os.path.dirname(__file__), "plugins")
    
    # Copy example_tool.py if it doesn't exist in the user's plugin dir
    example_tool_src = os.path.join(repo_plugins_dir, "example_tool.py")
    example_tool_dst = PLUGINS_DIR / "example_tool.py"
    if os.path.exists(example_tool_src) and not example_tool_dst.exists():
        try:
            shutil.copy2(example_tool_src, example_tool_dst)
            logger.info("🔌 [Lifespan] Copied example_tool.py to user plugins directory.")
        except Exception as e:
            logger.error("✗ [Lifespan] Failed to copy example_tool.py: %s", e)

    # Load user plugins
    logger.info("🔌 [Lifespan] Loading user plugins from %s...", PLUGINS_DIR)
    ToolRegistry.load_plugin_directory(str(PLUGINS_DIR))
    
    # Load built-in repository plugins
    if os.path.exists(repo_plugins_dir):
        logger.info("🔌 [Lifespan] Loading repository plugins from %s...", repo_plugins_dir)
        ToolRegistry.load_plugin_directory(repo_plugins_dir)

    # Restore persistent MCP servers from the database
    logger.info("🔌 [Lifespan] Restoring persistent MCP servers...")
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager
    from sqlalchemy import select
    
    try:
        async with async_session() as db:
            result = await db.execute(select(McpServer))
            mcp_servers = result.scalars().all()
            for server in mcp_servers:
                logger.info("  -> Reconnecting MCP server: %s", server.server_name)
                asyncio.create_task(
                    mcp_manager.connect_stdio_server(
                        server_name=server.server_name,
                        command=server.command,
                        args=server.args,
                        team_id=str(server.team_id) if server.team_id else None,
                        agent_id=str(server.agent_id) if server.agent_id else None,
                        env_vars=server.env_vars
                    )
                )
    except Exception as e:
        logger.error("✗ [Lifespan] Failed to restore MCP servers: %s", e)

    # Auto-boot Global MCP Servers
    # These are available to ALL agents without any UI configuration.
    import json
    from core.config import GLOBAL_MCPS, DISABLED_GLOBAL_MCPS_FILE
    
    disabled_mcps = []
    if DISABLED_GLOBAL_MCPS_FILE.exists():
        try:
            with open(DISABLED_GLOBAL_MCPS_FILE, "r") as f:
                disabled_mcps = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read disabled global MCPs config: {e}")

    for mcp in GLOBAL_MCPS:
        if mcp["server_name"] in disabled_mcps:
            logger.info(f"⏸️ [Lifespan] Global MCP server '{mcp['server_name']}' is disabled. Skipping.")
            continue
            
        logger.info(f"🌐 [Lifespan] Starting global {mcp['server_name']} MCP server...")
        asyncio.create_task(
            mcp_manager.connect_stdio_server(
                server_name=mcp["server_name"],
                command=mcp["command"],
                args=mcp["args"],
                team_id=None,
                agent_id=None,
            ),
            name=f"{mcp['server_name']}_mcp_server",
        )

    # Start background Dream Worker
    # FIX B1: Store strong reference in app.state so asyncio cannot garbage-collect the task.
    logger.info("🚀 [Lifespan] Starting Background 'Dream' Worker...")
    dream_task = asyncio.create_task(dream_worker.start(), name="dream_worker")

    # FIX B4: Periodic EventBus topic sweeper — cleans up inactive topics every 5 min.
    # Prevents the event bus subscriber dict from growing unbounded over a long server uptime.
    async def _topic_sweeper():
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            try:
                swept = await event_bus.clean_inactive_topics()
                if swept:
                    logger.debug("🧹 [TopicSweeper] Cleaned %d inactive topics.", swept)
            except Exception as sweep_err:
                logger.warning("Topic sweeper error: %s", sweep_err)

    sweeper_task = asyncio.create_task(_topic_sweeper(), name="topic_sweeper")

    # Store all background task references in app.state
    app.state.background_tasks = [dream_task, sweeper_task]

    yield  # Server is now running

    # --- SHUTDOWN ---
    logger.info("🛑 [Lifespan] Cleaning up resources...")
    dream_worker.stop()

    # Cancel and await all background tasks gracefully
    for bg_task in getattr(app.state, "background_tasks", []):
        if not bg_task.done():
            bg_task.cancel()
    _bg_tasks = getattr(app.state, "background_tasks", [])
    if _bg_tasks:
        await asyncio.gather(*_bg_tasks, return_exceptions=True)
        logger.info("✓ [Lifespan] All background tasks stopped.")

    # Close browser contexts
    try:
        from core.tools.browser_pool import close_all
        await close_all()
    except Exception as e:
        logger.warning("Browser pool cleanup error: %s", e)

    # Close MCP Manager connections
    try:
        from core.tools.mcp_client import mcp_manager
        await mcp_manager.shutdown()
    except Exception as e:
        logger.warning("MCP Manager cleanup error: %s", e)

    # Close shared LLM router httpx connection pool (FIX H3)
    try:
        from core.llm.multi_model_router import llm_router
        await llm_router.aclose()
        logger.info("✓ [Lifespan] LLM router HTTP client closed.")
    except Exception as e:
        logger.warning("LLM router cleanup error: %s", e)

    # Close Database connection pool
    try:
        from core.memory.database import engine
        await engine.dispose()
    except Exception as e:
        logger.warning("Database dispose error: %s", e)


app = FastAPI(title="Carole.ai Backend", version="0.2.0", lifespan=lifespan)

# ── Rate Limiting (Finding #7) ────────────────────────────────────────────────
if _SLOWAPI_AVAILABLE:
    app.state.limiter = _limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("✓ Rate limiting enabled (slowapi)")

# ── Security Headers Middleware (Finding #9) ──────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds essential security response headers to every HTTP response."""
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── CORS (Finding #14 — tightened from any port to specific ports) ────────────
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
)
ALLOWED_ORIGINS: List[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # Tightened: only allow the specific ports the frontend runs on (Finding #14)
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):(3000|3001)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(crud_router)
app.include_router(scratchpad_router)
app.include_router(cost_router)
app.include_router(auth_router)
app.include_router(google_auth_router)
app.include_router(file_router)
app.include_router(terminal_router)
app.include_router(git_router)
app.include_router(search_router)
app.include_router(plugin_router)
app.include_router(skill_router, prefix="/api/skills")
app.include_router(model_router)


# ============================================================
# Health & Root
# ============================================================

@app.get("/")
def read_root():
    return {"message": "Carole.ai Backend is Running", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    # Finding #9 — Do not expose internal configuration (allowed_origins) to callers
    return {
        "status": "healthy",
        "version": "0.2.0",
        "tools_registered": len(ToolRegistry.list_names()),
    }


@app.get("/api/ws/status/{team_id}")
async def ws_status(team_id: str):
    """Returns the number of active WebSocket subscribers on a team topic.
    Useful for debugging disconnection or missed-message issues."""
    topic = f"team:{team_id}"
    history = event_bus.get_history(topic)
    subscriber_count = len(event_bus._subscribers.get(topic, set()))
    return {
        "topic": topic,
        "active_subscribers": subscriber_count,
        "buffered_events": len(history),
    }


# ============================================================
# WebSocket Real-Time Chat Gateway
# ============================================================

@app.websocket("/ws/chat/{team_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    team_id: str,
    token: str = Query(default=""),
):
    """
    WebSocket endpoint representing the real-time EventBus gateway for a Team.
    Binds to Pub/Sub topic 'team:{team_id}' and bridges client <-> EventBus.

    Finding #4 — Requires a valid JWT via ?token=<jwt> query param.
    Browsers cannot set custom headers on WebSocket upgrades.
    """
    from core.auth.auth_service import _decode_jwt
    payload = _decode_jwt(token) if token else None
    if not payload:
        await websocket.close(code=4001)
        logger.warning("Chat WS rejected — missing or invalid token for team %s", team_id)
        return

    await websocket.accept()
    topic = f"team:{team_id}"
    event_queue = await event_bus.subscribe(topic)

    async def receive_from_client():
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {"text": data, "sender_id": "human"}

                # Handle heartbeat pings
                if payload.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    continue

                # Basic validation to avoid injection/spoofing
                text = payload.get("text", data if isinstance(data, str) else "")
                sender_id = payload.get("sender_id", "human")
                sender_name = payload.get("sender_name")
                attachments = payload.get("attachments")

                if not isinstance(text, str) or len(text) == 0 or len(text) > 10000:
                    logger.warning("Dropping invalid websocket message for team %s: text invalid", team_id)
                    continue
                if not isinstance(sender_id, str) or len(sender_id) > 100:
                    logger.warning("Dropping invalid websocket message for team %s: sender_id invalid", team_id)
                    continue
                # Sanitize attachments: must be a list of small dicts. Caps the
                # count and per-attachment text size to prevent abuse. File-ref
                # attachments (@file:path) carry only a path string, so they're tiny.
                clean_attachments: list = []
                if isinstance(attachments, list):
                    for att in attachments[:50]:
                        if isinstance(att, dict):
                            clean_attachments.append(att)

                # Route the message through our MessageRouter (persists + triggers agents)
                try:
                    await message_router.route_message(
                        text.strip(), sender_id.strip(), team_id, sender_name,
                        attachments=clean_attachments or None,
                    )
                except Exception as e:
                    logger.error("Failed to route message for team %s: %s", team_id, e)
        except (asyncio.CancelledError, WebSocketDisconnect):
            logger.info("WebSocket receive task ended for team %s", team_id)
        except Exception as e:
            logger.exception("Unexpected error in receive_from_client for team %s: %s", team_id, e)

    async def send_to_client():
        try:
            while True:
                event = await event_queue.get()
                try:
                    await websocket.send_text(json.dumps(event, default=str))
                except (WebSocketDisconnect, RuntimeError):
                    # Client disconnected — stop sending; finally block will unsubscribe
                    logger.info("WebSocket send failed (client disconnected) for team %s", team_id)
                    break
                finally:
                    event_queue.task_done()
        except asyncio.CancelledError:
            logger.info("WebSocket send task cancelled for team %s", team_id)
        except Exception as e:
            logger.exception("Unexpected error in send_to_client for team %s: %s", team_id, e)

    task1 = asyncio.create_task(receive_from_client())
    task2 = asyncio.create_task(send_to_client())

    try:
        done, pending = await asyncio.wait([task1, task2], return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
    finally:
        await event_bus.unsubscribe(topic, event_queue)


# ============================================================
# Human-In-The-Loop Approval API
# ============================================================

class ApprovalDecision(BaseModel):
    approved: bool


@app.post("/api/tools/approve/{tx_id}")
async def approve_tool_execution(tx_id: str, decision: ApprovalDecision, user: dict = Depends(require_auth)):
    """
    Resolves a pending human-in-the-loop approval request.
    Called by the frontend when the user clicks Approve or Deny.
    """
    from core.tools.tool_executor import pending_approvals, approval_results

    if tx_id not in pending_approvals:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found or already resolved.")

    # Store the decision and signal the waiting agent coroutine
    approval_results[tx_id] = decision.approved
    pending_approvals[tx_id].set()

    action = "APPROVED" if decision.approved else "DENIED"
    logger.info("Human %s approval '%s' for tx_id=%s", action.lower(), tx_id, user.get("email", "unknown"))
    return {"status": "ok", "tx_id": tx_id, "action": action}


# ============================================================
# Agent Question Answer API
# ============================================================

class QuestionAnswer(BaseModel):
    answer: str


@app.post("/api/agent/answer/{question_id}")
async def answer_agent_question(question_id: str, body: QuestionAnswer, user: dict = Depends(require_auth)):
    """
    Resolves a pending ask_user question from an agent.
    Called by the frontend when the user types an answer.
    """
    from core.tools.interaction_tools import pending_questions, question_answers

    if question_id not in pending_questions:
        raise HTTPException(status_code=404, detail=f"Question '{question_id}' not found or already answered.")

    question_answers[question_id] = body.answer
    pending_questions[question_id].set()

    return {"status": "ok", "question_id": question_id}


# ============================================================
# Dynamic Tool Registration (runtime hot-reload)
# ============================================================

class ToolRegisterRequest(BaseModel):
    name: str
    description: str
    category: str = "custom"
    permission_default: str = "safe"
    parameters: dict = {}
    handler_module: Optional[str] = None
    handler_fn: Optional[str] = None


@app.post("/api/tools/register")
async def register_tool_runtime(body: ToolRegisterRequest, user: dict = Depends(require_auth)):
    """Register a tool at runtime. Requires authenticated user and a handler reference."""
    from core.tools.tool_registry import ToolSpec

    existing = ToolRegistry.get(body.name)
    if existing:
        return {"status": "already_registered", "name": body.name}

    # Require a handler reference for runtime registration to avoid placeholder-only tools
    if not (body.handler_module and body.handler_fn):
        raise HTTPException(status_code=400, detail="handler_module and handler_fn are required for runtime registration")

    # Finding #10 — Restrict imports to safe plugin namespaces to prevent arbitrary
    # module loading (e.g., loading 'os' and calling 'os.system').
    _ALLOWED_MODULE_PREFIXES = ("core.plugins.", "plugins.")
    if not any(body.handler_module.startswith(p) for p in _ALLOWED_MODULE_PREFIXES):
        logger.warning(
            "User %s attempted to register a handler from disallowed module: %s",
            user.get("email"), body.handler_module
        )
        raise HTTPException(
            status_code=400,
            detail="handler_module must be within the 'core.plugins' or 'plugins' namespace."
        )

    try:
        module = importlib.import_module(body.handler_module)
        handler = getattr(module, body.handler_fn)
        if not callable(handler):
            raise AttributeError("handler is not callable")
    except Exception as e:
        logger.exception("Failed to load handler for tool %s: %s", body.name, e)
        raise HTTPException(status_code=400, detail=f"Failed to load handler: {e}")

    spec = ToolSpec(
        name=body.name,
        description=body.description,
        category=body.category,
        parameters=body.parameters,
        permission_default=body.permission_default,
        handler=handler,
    )

    ToolRegistry.register(spec)
    logger.info("User %s registered tool %s", user.get("email"), body.name)
    return {"status": "registered", "name": body.name}



# ============================================================
# Startup
# ============================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)), reload=True)
