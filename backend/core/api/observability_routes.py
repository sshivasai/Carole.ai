"""
# backend/core/api/observability_routes.py

FastAPI API router for OpenLLMetry observability and telemetry.
Provides endpoints for the Carole.ai frontend Observability panel.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from core.observability.openllmetry_tracer import (
    get_recent_traces,
    get_observability_stats,
    clear_traces,
)
from opentelemetry import trace
import time

router = APIRouter(prefix="/api/observability", tags=["Observability"])


class ObservabilityStats(BaseModel):
    total_spans: int
    total_prompt_tokens: int
    total_completion_tokens: int
    avg_latency_ms: float
    error_count: int
    models_used: List[str]
    status: str


@router.get("/traces")
async def get_traces(
    limit: int = Query(50, ge=1, le=200),
    agent: Optional[str] = Query(None, description="Filter by agent name"),
):
    """Returns the most recent OpenLLMetry spans and agent traces."""
    traces = get_recent_traces(limit=limit, filter_agent=agent)
    return {"traces": traces, "count": len(traces)}


@router.get("/stats", response_model=ObservabilityStats)
async def get_stats():
    """Returns aggregate observability metrics (tokens, latency, error count, models)."""
    return get_observability_stats()


@router.post("/clear")
async def clear_telemetry():
    """Clears the in-memory telemetry trace buffer."""
    clear_traces()
    return {"status": "cleared"}


@router.post("/emit-sample")
async def emit_sample_trace():
    """
    Emits a sample multi-agent swarm trace for testing and verification in the UI.
    Simulates Archer (Lead Orchestrator) dispatching a coder subagent and Judge AI verification.
    """
    tracer = trace.get_tracer("carole.ai.swarm", "1.0.0")

    with tracer.start_as_current_span("Goal: Full-Stack Auth & Observability Integration") as root:
        root.set_attribute("agent.name", "Swarm Coordinator")
        root.set_attribute("llm.prompt", "Deploy OpenLLMetry and configure real-time telemetry streaming.")
        time.sleep(0.05)

        with tracer.start_as_current_span("Agent: Archer (Lead Orchestrator)") as archer:
            archer.set_attribute("agent.name", "Archer")
            archer.set_attribute("agent.role", "Lead Orchestrator")
            archer.set_attribute("agent.model", "claude-sonnet-4")
            archer.set_attribute("llm.usage.prompt_tokens", 1420)
            archer.set_attribute("llm.usage.completion_tokens", 380)
            time.sleep(0.05)

        with tracer.start_as_current_span("Subagent: Sub-Coder (Worker)") as coder:
            coder.set_attribute("agent.name", "Sub-PythonDev_8777")
            coder.set_attribute("agent.role", "Coder")
            coder.set_attribute("agent.model", "gpt-4o-mini")
            coder.set_attribute("tool.call", "replace_file_content")
            coder.set_attribute("llm.usage.prompt_tokens", 2150)
            coder.set_attribute("llm.usage.completion_tokens", 520)
            time.sleep(0.05)

        with tracer.start_as_current_span("Security: Judge AI Gate") as judge:
            judge.set_attribute("agent.name", "Judge AI")
            judge.set_attribute("agent.role", "Security Interceptor")
            judge.set_attribute("agent.model", "gemini-2.0-flash")
            judge.set_attribute("tool.call", "pytest --cov=core")
            judge.set_attribute("llm.usage.prompt_tokens", 850)
            judge.set_attribute("llm.usage.completion_tokens", 120)
            time.sleep(0.03)

    return {"status": "success", "message": "Sample agent swarm trace emitted successfully."}
