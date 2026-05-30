"""
# backend/main.py

This is the main entrypoint for the FastAPI backend of Carole.ai.

Responsibilities:
1. Initialize the FastAPI application.
2. Configure WebSocket endpoints for the EventBus (frontend <-> backend real-time communication).
3. Initialize the database connection pool (PostgreSQL + pgvector).
4. Register HTTP API routes for Team Management, Agent Configuration, etc.
5. Startup background workers (e.g., the 'Dream' memory consolidation worker).
"""

import json
import asyncio
from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
import uvicorn
import dotenv
import os

from core.memory.database import init_db
from core.chat.event_bus import event_bus

dotenv.load_dotenv()

# Define the lifespan context manager (for FastAPI v0.100+)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    print("🚀 [Lifespan] Initializing Database Connection Pool...")
    try:
        await init_db()
        print("✓ [Lifespan] Database and pgvector initialized successfully!")
    except Exception as e:
        print(f"✗ [Lifespan] Error initializing database: {str(e)}")
    
    print("🚀 [Lifespan] Starting Background 'Dream' Worker...")
    # TODO: run_background_task(dream_worker())
    
    yield # yields control to the running FastAPI server
    
    # --- SHUTDOWN PHASE ---
    print("🛑 [Lifespan] Cleaning up resources...")
    pass

app = FastAPI(title="Carole.ai Backend", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"message": "Carole.ai Backend is Running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.websocket("/ws/chat/{team_id}")
async def websocket_endpoint(websocket: WebSocket, team_id: str):
    """
    WebSocket endpoint representing the real-time EventBus gateway for a Team.
    
    - Binds the WebSocket connection to the Pub/Sub 'team:{team_id}' topic.
    - Concurrently listens to client inputs (and publishes them to the EventBus).
    - Concurrently listens to EventBus events (and streams them back to the client UI).
    - Cleans up subscriptions automatically on disconnect to prevent memory leaks.
    """
    await websocket.accept()
    topic = f"team:{team_id}"
    
    # Subscribe to the event queue for this team channel
    event_queue = await event_bus.subscribe(topic)
    
    async def receive_from_client():
        try:
            while True:
                data = await websocket.receive_text()
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {"text": data, "sender_id": "human"}
                
                # Publish the client's payload directly to the EventBus
                await event_bus.publish(topic, payload)
        except Exception:
            pass  # Client disconnected
            
    async def send_to_client():
        try:
            while True:
                # Read from the subscriber asyncio queue
                event = await event_queue.get()
                # Stream the event down to the websocket client
                await websocket.send_text(json.dumps(event))
                event_queue.task_done()
        except Exception:
            pass  # Client disconnected

    try:
        # Run receiving and sending processes concurrently
        await asyncio.gather(
            receive_from_client(),
            send_to_client()
        )
    finally:
        # Clean up queue subscription to prevent memory leaks when client leaves
        await event_bus.unsubscribe(topic, event_queue)

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", 8000)), reload=True)
