"""
# backend/main.py

This is the main entrypoint for the FastAPI backend of Carole.ai.

Responsibilities:
1. Initialize the FastAPI application with lifespan events.
2. Configure WebSocket endpoints for the EventBus (frontend <-> backend real-time communication).
3. Initialize the database connection pool (PostgreSQL + pgvector).
4. Register HTTP API routes for Team Management, Agent Configuration, and Approvals.
5. Startup background workers (AutoDream memory consolidation worker).
6. Register built-in tools and load plugin tools from the /plugins/ directory.
"""

import json
import asyncio
from pathlib import Path
from fastapi import FastAPI, WebSocket, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
import uvicorn
import dotenv
import os

from core.memory.database import init_db, get_db, async_session
from core.chat.event_bus import event_bus
from core.chat.message_router import message_router
from core.memory.auto_dream import dream_worker
from core.tools.tool_executor import register_builtin_tools
from core.tools.tool_registry import ToolRegistry
from core.api.crud_routes import router as crud_router

dotenv.load_dotenv()


# --- Lifespan context manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    print("🚀 [Lifespan] Initializing Database Connection Pool...")
    try:
        await init_db()
        print("✓ [Lifespan] Database and pgvector initialized successfully!")
    except Exception as e:
        print(f"✗ [Lifespan] Error initializing database: {str(e)}")

    # Register built-in tools with the dynamic ToolRegistry
    print("🔧 [Lifespan] Registering built-in tools...")
    register_builtin_tools()

    # Load plugin tools from the /plugins/ directory
    plugins_dir = str(Path(__file__).parent / "plugins")
    print(f"🔌 [Lifespan] Loading plugins from {plugins_dir}...")
    ToolRegistry.load_plugin_directory(plugins_dir)

    # Start background Dream Worker
    print("🚀 [Lifespan] Starting Background 'Dream' Worker...")
    dream_task = asyncio.create_task(dream_worker.start())

    yield  # Server is now running

    # --- SHUTDOWN ---
    print("🛑 [Lifespan] Cleaning up resources...")
    dream_worker.stop()
    dream_task.cancel()


app = FastAPI(title="Carole.ai Backend", version="0.2.0", lifespan=lifespan)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register CRUD API routes
app.include_router(crud_router)


# ============================================================
# Health & Root
# ============================================================

@app.get("/")
def read_root():
    return {"message": "Carole.ai Backend is Running", "version": "0.2.0"}


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.2.0",
        "tools_registered": len(ToolRegistry.list_names()),
    }


# ============================================================
# WebSocket Real-Time Chat Gateway
# ============================================================

@app.websocket("/ws/chat/{team_id}")
async def websocket_endpoint(websocket: WebSocket, team_id: str):
    """
    WebSocket endpoint representing the real-time EventBus gateway for a Team.
    Binds to Pub/Sub topic 'team:{team_id}' and bridges client <-> EventBus.
    """
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

                # Route the message through our MessageRouter (persists + triggers agents)
                text = payload.get("text", data if isinstance(data, str) else "")
                sender_id = payload.get("sender_id", "human")
                await message_router.route_message(text, sender_id, team_id)
        except Exception:
            pass  # Client disconnected

    async def send_to_client():
        try:
            while True:
                event = await event_queue.get()
                await websocket.send_text(json.dumps(event, default=str))
                event_queue.task_done()
        except Exception:
            pass  # Client disconnected

    try:
        await asyncio.gather(receive_from_client(), send_to_client())
    finally:
        await event_bus.unsubscribe(topic, event_queue)


# ============================================================
# Human-In-The-Loop Approval API
# ============================================================

class ApprovalDecision(BaseModel):
    approved: bool


@app.post("/api/tools/approve/{tx_id}")
async def approve_tool_execution(tx_id: str, decision: ApprovalDecision):
    """
    Resolves a pending human-in-the-loop approval request.
    Called by the frontend when the user clicks Approve or Deny.
    """
    from core.tools.tool_executor import pending_approvals, approval_results

    if tx_id not in pending_approvals:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found or already resolved.")

    # Store the decision and release the blocked agent coroutine
    approval_results[tx_id] = decision.approved
    pending_approvals[tx_id].set()

    action = "APPROVED" if decision.approved else "DENIED"
    return {"status": "ok", "tx_id": tx_id, "action": action}


# ============================================================
# Agent Question Answer API
# ============================================================

class QuestionAnswer(BaseModel):
    answer: str


@app.post("/api/agent/answer/{question_id}")
async def answer_agent_question(question_id: str, body: QuestionAnswer):
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


@app.post("/api/tools/register")
async def register_tool_runtime(body: ToolRegisterRequest):
    """Register a tool at runtime (metadata only — handler must be loaded via plugin)."""
    from core.tools.tool_registry import ToolSpec
    # For runtime registration without a handler, create a placeholder
    existing = ToolRegistry.get(body.name)
    if existing:
        return {"status": "already_registered", "name": body.name}

    spec = ToolSpec(
        name=body.name,
        description=body.description,
        category=body.category,
        parameters=body.parameters,
        permission_default=body.permission_default,
        handler=_placeholder_handler,
    )
    ToolRegistry.register(spec)
    return {"status": "registered", "name": body.name}


async def _placeholder_handler(args: dict, team_id: str) -> str:
    return "Error: This tool was registered at runtime without a handler. Load the plugin first."


# ============================================================
# Startup
# ============================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)), reload=True)
