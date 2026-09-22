from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, Integer
from pydantic import BaseModel
from typing import Optional
import uuid

from core.memory.database import get_db
from core.memory.models import Project, TokenUsage, Team
from core.auth.auth_middleware import require_auth

router = APIRouter(prefix="/api/cost", tags=["Cost"])

class CostStats(BaseModel):
    total_spend_usd: float
    budget_limit_usd: Optional[float]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    unknown_cost_calls: int = 0

class BudgetUpdate(BaseModel):
    project_id: str
    budget_limit_usd: Optional[float]

@router.get("/stats", response_model=CostStats)
async def get_cost_stats(
    project_id: str,
    db=Depends(get_db),
    user=Depends(require_auth)
):
    try:
        proj_uuid = uuid.UUID(project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    # Verify project belongs to user
    result = await db.execute(select(Project).where(Project.id == proj_uuid, Project.owner_id == uuid.UUID(user["sub"])))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get sum of tokens from TokenUsage (columns stored as strings → cast to Integer for SUM)
    stmt = select(
        func.sum(func.cast(TokenUsage.prompt_tokens, Integer)).label("prompt"),
        func.sum(func.cast(TokenUsage.completion_tokens, Integer)).label("completion"),
        func.sum(func.cast(TokenUsage.total_tokens, Integer)).label("total")
    ).where(TokenUsage.project_id == proj_uuid)

    usage_result = await db.execute(stmt)
    usage = usage_result.one()

    return CostStats(
        total_spend_usd=float(project.total_spend_usd) if project.total_spend_usd else 0.0,
        budget_limit_usd=float(project.budget_limit_usd) if project.budget_limit_usd else None,
        total_prompt_tokens=usage.prompt or 0,
        total_completion_tokens=usage.completion or 0,
        total_tokens=usage.total or 0,
        unknown_cost_calls=await db.scalar(select(func.count(TokenUsage.id)).where(
            TokenUsage.project_id == proj_uuid, TokenUsage.estimated_cost_usd.is_(None))) or 0,
    )


@router.get("/requests")
async def latest_requests(team_id: str, db=Depends(get_db), user=Depends(require_auth)):
    try:
        tid = uuid.UUID(team_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid team ID")
    owned = await db.scalar(select(Team.id).join(Project, Project.id == Team.project_id).where(
        Team.id == tid, Project.owner_id == uuid.UUID(user["sub"])))
    if owned is None:
        raise HTTPException(status_code=404, detail="Team not found")
    ranked = select(TokenUsage.id, func.row_number().over(
        partition_by=TokenUsage.agent_id, order_by=(TokenUsage.created_at.desc(), TokenUsage.id.desc())
    ).label("rank")).where(TokenUsage.team_id == tid, TokenUsage.agent_id.is_not(None)).subquery()
    rows = (await db.scalars(select(TokenUsage).join(ranked, ranked.c.id == TokenUsage.id)
                            .where(ranked.c.rank == 1))).all()
    return [{**(row.accounting or {}), "agent_id": str(row.agent_id), "agent_name": row.agent_name,
             "call_id": row.call_id, "run_id": row.run_id, "model": row.model,
             "prompt_tokens": row.prompt_tokens, "completion_tokens": row.completion_tokens,
             "total_tokens": row.total_tokens, "purpose": row.purpose,
             "recorded_at": row.created_at.isoformat()} for row in rows]

@router.post("/budget")
async def update_budget(
    payload: BudgetUpdate,
    db=Depends(get_db),
    user=Depends(require_auth)
):
    try:
        proj_uuid = uuid.UUID(payload.project_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID")

    result = await db.execute(select(Project).where(Project.id == proj_uuid, Project.owner_id == uuid.UUID(user["sub"])))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.budget_limit_usd = str(payload.budget_limit_usd) if payload.budget_limit_usd is not None else None
    await db.commit()

    return {"status": "success", "budget_limit_usd": project.budget_limit_usd}
