from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, Integer
from pydantic import BaseModel
from typing import Optional
import uuid

from core.memory.database import get_db
from core.memory.models import Project, TokenUsage
from core.auth.auth_middleware import require_auth

router = APIRouter(prefix="/api/cost", tags=["Cost"])

class CostStats(BaseModel):
    total_spend_usd: float
    budget_limit_usd: Optional[float]
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int

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
        total_tokens=usage.total or 0
    )

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
