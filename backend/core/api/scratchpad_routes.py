"""
# backend/core/api/scratchpad_routes.py

REST API for agent scratchpads.  Thin transport layer over
`ScratchpadStore` — all persistence, locking, and realtime broadcast lives in
`core/memory/scratchpad.py`.

Endpoints (all prefixed with /api):
    GET    /scratchpad/{team_id}             -> list every pad (team + each agent)
    GET    /scratchpad/{team_id}/{target}    -> read one pad (target=team|personal)
    POST   /scratchpad/{team_id}             -> append (mode='append') or overwrite (mode='overwrite')
    PUT    /scratchpad/{team_id}             -> update / full-replace a pad
    DELETE /scratchpad/{team_id}             -> clear/remove a pad
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.auth_middleware import require_auth
from core.memory.database import get_db
from core.memory.models import Agent
from core.memory.scratchpad import scratchpad_store
from core.api.crud_routes import _assert_team_access

router = APIRouter(prefix="/api", tags=["scratchpad"])


class ScratchpadWriteBody(BaseModel):
    content: str
    target: str = "personal"   # 'personal' | 'team'
    mode: str = "append"       # 'append' | 'overwrite'
    agent_name: str = "Agent"
    agent_id: Optional[str] = None
    author: Optional[str] = None  # name stamped in append header (defaults to agent_name)


async def _agent_roster(team_id: str, db: AsyncSession) -> List[dict]:
    try:
        team_uuid = uuid.UUID(team_id)
    except (ValueError, AttributeError):
        return []
    result = await db.execute(
        select(Agent).where(Agent.team_id == team_uuid).order_by(Agent.created_at)
    )
    return [
        {"id": str(a.id), "name": a.name}
        for a in result.scalars().all()
    ]


@router.get("/scratchpad/{team_id}")
async def list_scratchpads(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """List the team pad plus one personal pad per agent (empty pads included)."""
    await _assert_team_access(db, team_id, user["sub"])
    agents = await _agent_roster(team_id, db)
    return await scratchpad_store.list_pads(team_id, agents)


@router.get("/scratchpad/{team_id}/{target}")
async def read_scratchpad(
    team_id: str,
    target: str,
    agent_name: str = Query("", description="Required when target != 'team'"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    if target not in ("team", "personal"):
        raise HTTPException(status_code=400, detail="target must be 'team' or 'personal'")
    if target == "personal" and not agent_name:
        raise HTTPException(status_code=400, detail="agent_name is required for personal pads")
    return await scratchpad_store.read(team_id, target, agent_name)


@router.post("/scratchpad/{team_id}")
async def write_scratchpad(
    team_id: str,
    body: ScratchpadWriteBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    return await scratchpad_store.write(
        team_id, body.target, body.agent_name, body.content,
        mode=body.mode, agent_id=body.agent_id or "", author=body.author,
    )


@router.put("/scratchpad/{team_id}")
async def update_scratchpad(
    team_id: str,
    body: ScratchpadWriteBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    return await scratchpad_store.update(
        team_id, body.target, body.agent_name, body.content,
        agent_id=body.agent_id or "", author=body.author,
    )


@router.delete("/scratchpad/{team_id}")
async def delete_scratchpad(
    team_id: str,
    target: str = Query("personal"),
    agent_name: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user["sub"])
    if target not in ("team", "personal"):
        raise HTTPException(status_code=400, detail="target must be 'team' or 'personal'")
    if target == "personal" and not agent_name:
        raise HTTPException(status_code=400, detail="agent_name is required for personal pads")
    return await scratchpad_store.delete(team_id, target, agent_name)
