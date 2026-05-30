"""
# backend/main.py

This is the main entrypoint for the FastAPI backend of Carole.ai.

Responsibilities:
1. Initialize the FastAPI application with lifespan events.
2. Configure WebSocket endpoints for the EventBus (frontend <-> backend real-time communication).
3. Initialize the database connection pool (PostgreSQL + pgvector).
4. Register HTTP API routes for Team Management, Agent Configuration, and Approvals.
5. Startup background workers (AutoDream memory consolidation worker).
"""

import json
import asyncio
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

    # Start background Dream Worker
    print("🚀 [Lifespan] Starting Background 'Dream' Worker...")
    dream_task = asyncio.create_task(dream_worker.start())

    yield  # Server is now running

    # --- SHUTDOWN ---
    print("🛑 [Lifespan] Cleaning up resources...")
    dream_worker.stop()
    dream_task.cancel()


app = FastAPI(title="Carole.ai Backend", version="0.1.0", lifespan=lifespan)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health & Root
# ============================================================

@app.get("/")
def read_root():
    return {"message": "Carole.ai Backend is Running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}


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
                await websocket.send_text(json.dumps(event))
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
# Startup
# ============================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)), reload=True)
