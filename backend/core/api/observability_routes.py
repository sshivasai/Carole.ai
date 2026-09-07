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
from core.auth.auth_middleware import require_auth
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
    user: dict = Depends(require_auth),
):
    """Returns the most recent OpenLLMetry spans and agent traces."""
    traces = get_recent_traces(limit=limit, filter_agent=agent)
    return {"traces": traces, "count": len(traces)}


@router.get("/stats", response_model=ObservabilityStats)
async def get_stats(user: dict = Depends(require_auth)):
    """Returns aggregate observability metrics (tokens, latency, error count, models)."""
    return get_observability_stats()


@router.post("/clear")
async def clear_telemetry(user: dict = Depends(require_auth)):
    """Clears the in-memory telemetry trace buffer."""
    clear_traces()
    return {"status": "cleared"}


@router.post("/emit-sample")
async def emit_sample_trace(user: dict = Depends(require_auth)):
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


@router.get("/dag")
async def get_workflow_dag(
    team_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth)
):
    """
    Returns the real-time Multi-Agent workflow DAG (nodes & edges)
    showing parent coordinators, worker subagents, model assignments, and status.
    """
    import uuid
    from sqlalchemy import select
    from core.memory.database import async_session
    from core.memory.models import Agent

    nodes = []
    edges = []

    async with async_session() as db:
        stmt = select(Agent)
        if team_id and str(team_id).strip().lower() not in ("undefined", "null", "none", ""):
            try:
                t_uuid = uuid.UUID(str(team_id).strip())
                stmt = stmt.where(Agent.team_id == t_uuid)
            except (ValueError, TypeError, AttributeError):
                pass
        res = await db.execute(stmt)
        agents = res.scalars().all()

        for a in agents:
            is_coord = (
                a.role in ("Lead Orchestrator", "Coordinator", "Orchestrator")
                or "orchestrat" in (a.role or "").lower()
                or (a.name or "").lower() == "archer"
            )
            nodes.append({
                "id": str(a.id),
                "name": a.name,
                "role": a.role,
                "model": a.model,
                "status": "active" if is_coord else "idle",
                "is_coordinator": is_coord,
                "parent_id": None
            })

        coordinator = next((n for n in nodes if n["is_coordinator"]), None)
        if coordinator:
            for n in nodes:
                if n["id"] != coordinator["id"]:
                    edges.append({
                        "id": f"{coordinator['id']}->{n['id']}",
                        "source": coordinator["id"],
                        "target": n["id"],
                        "type": "delegation"
                    })

    return {"nodes": nodes, "edges": edges}


@router.get("/code-graph")
async def get_code_graph_topology(
    project_id: Optional[str] = Query(None),
    refresh: bool = Query(False, description="Re-scan and re-index project files from disk"),
    user: dict = Depends(require_auth)
):
    """
    Returns AST code graph topology (files, classes, functions, import edges).
    """
    from core.knowledge.code_graph import code_graph
    from pathlib import Path

    clean_project_id = None
    if project_id and str(project_id).strip().lower() not in ("undefined", "null", "none", ""):
        clean_project_id = str(project_id).strip()

    if refresh:
        await code_graph.build_graph(clean_project_id)

    g = await code_graph.get_graph(clean_project_id)
    nodes = []
    edges = []

    pid = clean_project_id or "default"
    file_chunks = code_graph.file_chunks.get(pid, {})

    for node_id in g.nodes():
        node_data = g.nodes[node_id]
        chunks = file_chunks.get(node_id, [])
        sym_names = [c.name for c in chunks] if chunks else node_data.get("symbols", [])
        nodes.append({
            "id": node_id,
            "label": Path(node_id).name,
            "path": node_id,
            "type": node_data.get("type", "file"),
            "symbols": sym_names
        })

    for u, v in g.edges():
        edge_data = g.get_edge_data(u, v) or {}
        edges.append({
            "source": u,
            "target": v,
            "type": edge_data.get("type", "import")
        })

    return {"nodes": nodes, "edges": edges}


@router.post("/code-graph/reindex")
async def reindex_code_graph(
    project_id: Optional[str] = Query(None),
    user: dict = Depends(require_auth)
):
    """
    Re-scans project directory from disk and completely rebuilds the AST Code Knowledge Graph.
    Prunes any deleted or stale files.
    """
    from core.knowledge.code_graph import code_graph

    clean_project_id = None
    if project_id and str(project_id).strip().lower() not in ("undefined", "null", "none", ""):
        clean_project_id = str(project_id).strip()

    await code_graph.build_graph(clean_project_id)
    g = await code_graph.get_graph(clean_project_id)
    return {
        "status": "success",
        "message": "Repository code knowledge graph rescanned and synchronized with disk.",
        "node_count": len(g.nodes),
        "edge_count": len(g.edges)
    }

