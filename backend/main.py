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

from fastapi import FastAPI, WebSocket
from contextlib import asynccontextmanager
import uvicorn
import dotenv
import os



dotenv.load_dotenv()

app = FastAPI(title="Carole.ai Backend")


# 1. Define the lifespan context manager (for FastAPI v0.100+)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE (Before Server Starts Running) ---
    print("🚀 [Lifespan] Initializing Database Connection Pool...")
    # db_engine = await initialize_database()
    
    print("🚀 [Lifespan] Starting Background 'Dream' Worker...")
    # run_background_task(dream_worker())
    
    yield # This yields control to the running FastAPI server
    
    # --- SHUTDOWN PHASE (When Server is Stopping) ---
    print("🛑 [Lifespan] Cleaning up resources...")
    # await db_engine.close()
    pass





@app.get("/")
def read_root():
    return {"message": "Carole.ai Backend is Running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    # TODO: Connect to EventBus for real-time streaming
    pass

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST"), port=int(os.getenv("PORT")), reload=True)


