from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel, Field
import uuid

from core.memory.database import get_db
from core.auth.auth_middleware import require_auth
from core.api.crud_routes import _assert_team_access
from core.memory.models import ScheduledTask

router = APIRouter(prefix="/api/cron", tags=["cron"])

class ScheduledTaskCreate(BaseModel):
    name: str = Field(..., max_length=100)
    agent_id: str
    cron_expression: str = Field(..., max_length=100)
    prompt: str

class ScheduledTaskUpdate(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    prompt: str | None = None
    is_active: bool | None = None

@router.get("/{team_id}")
async def list_scheduled_tasks(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.team_id == uuid.UUID(team_id))
        .order_by(ScheduledTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return tasks

@router.post("/{team_id}")
async def create_scheduled_task(
    team_id: str,
    body: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    
    new_task = ScheduledTask(
        team_id=uuid.UUID(team_id),
        agent_id=uuid.UUID(body.agent_id),
        name=body.name,
        cron_expression=body.cron_expression,
        prompt=body.prompt,
        is_active=True
    )
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task

@router.put("/{task_id}")
async def update_scheduled_task(
    task_id: str,
    body: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    # Retrieve task
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await _assert_team_access(db, str(task.team_id), user["sub"])
    
    if body.name is not None:
        task.name = body.name
    if body.cron_expression is not None:
        task.cron_expression = body.cron_expression
    if body.prompt is not None:
        task.prompt = body.prompt
    if body.is_active is not None:
        task.is_active = body.is_active
        
    await db.commit()
    await db.refresh(task)
    return task

@router.delete("/{task_id}")
async def delete_scheduled_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    result = await db.execute(select(ScheduledTask).where(ScheduledTask.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await _assert_team_access(db, str(task.team_id), user["sub"])
    
    await db.delete(task)
    await db.commit()
    return {"status": "success"}
