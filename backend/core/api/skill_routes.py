import logging
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.database import get_db
from core.auth.auth_middleware import require_auth
from core.skills.skill_manager import SkillManager

logger = logging.getLogger("carole.skill_routes")
router = APIRouter()

class SkillCreateReq(BaseModel):
    team_id: str
    name: str
    description: Optional[str] = ""
    system_prompt_addendum: Optional[str] = ""
    tools: Optional[List[str]] = []
    mcp_servers: Optional[List[str]] = []

class SkillUpdateReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt_addendum: Optional[str] = None
    tools: Optional[List[str]] = None
    mcp_servers: Optional[List[str]] = None
    is_active: Optional[bool] = None

class SkillRes(BaseModel):
    id: str
    team_id: str
    name: str
    description: Optional[str]
    system_prompt_addendum: Optional[str]
    tools: List[str]
    mcp_servers: List[str]
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

@router.get("/{team_id}", response_model=List[SkillRes])
async def list_skills(
    team_id: str,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    try:
        skills = await SkillManager.get_team_skills(db, team_id, active_only=active_only)
        # Convert to Pydantic objects or dicts
        res = []
        for s in skills:
            res.append({
                "id": str(s.id),
                "team_id": str(s.team_id),
                "name": s.name,
                "description": s.description,
                "system_prompt_addendum": s.system_prompt_addendum,
                "tools": s.tools or [],
                "mcp_servers": s.mcp_servers or [],
                "is_active": s.is_active
            })
        return res
    except Exception as e:
        logger.exception("Failed to list skills")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=SkillRes)
async def create_skill(
    req: SkillCreateReq,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    try:
        new_skill = await SkillManager.create_skill(
            db=db,
            team_id=req.team_id,
            name=req.name,
            description=req.description,
            system_prompt_addendum=req.system_prompt_addendum,
            tools=req.tools,
            mcp_servers=req.mcp_servers
        )
        return {
            "id": str(new_skill.id),
            "team_id": str(new_skill.team_id),
            "name": new_skill.name,
            "description": new_skill.description,
            "system_prompt_addendum": new_skill.system_prompt_addendum,
            "tools": new_skill.tools or [],
            "mcp_servers": new_skill.mcp_servers or [],
            "is_active": new_skill.is_active
        }
    except Exception as e:
        logger.exception("Failed to create skill")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{skill_id}", response_model=SkillRes)
async def update_skill(
    skill_id: str,
    req: SkillUpdateReq,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    try:
        updated = await SkillManager.update_skill(
            db=db,
            skill_id=skill_id,
            name=req.name,
            description=req.description,
            system_prompt_addendum=req.system_prompt_addendum,
            tools=req.tools,
            mcp_servers=req.mcp_servers,
            is_active=req.is_active
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        return {
            "id": str(updated.id),
            "team_id": str(updated.team_id),
            "name": updated.name,
            "description": updated.description,
            "system_prompt_addendum": updated.system_prompt_addendum,
            "tools": updated.tools or [],
            "mcp_servers": updated.mcp_servers or [],
            "is_active": updated.is_active
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to update skill")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    try:
        success = await SkillManager.delete_skill(db, skill_id)
        if not success:
            raise HTTPException(status_code=404, detail="Skill not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete skill")
        raise HTTPException(status_code=500, detail=str(e))
