import logging
from pathlib import Path
import re
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.database import get_db
from core.auth.auth_middleware import require_auth
from core.skills.skill_manager import SkillManager

from core.api.crud_routes import _assert_team_access
from core.memory.models import Skill
from sqlalchemy import select
import uuid

logger = logging.getLogger("carole.skill_routes")
router = APIRouter()

async def _assert_skill_access(db: AsyncSession, skill_id: str, user_id: str) -> Skill:
    try:
        s_uuid = uuid.UUID(skill_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid skill_id")
    stmt = select(Skill).where(Skill.id == s_uuid)
    res = await db.execute(stmt)
    skill = res.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await _assert_team_access(db, str(skill.team_id), user_id)
    return skill

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

class DiscoveredSkillRes(BaseModel):
    name: str
    description: str = ""
    tools: List[str] = []
    dependencies: List[str] = []
    is_active: bool = True
    author: str = ""
    version: str = "1.0.0"
    source: str = "project"
    skill_dir: Optional[str] = None
    skill_file: Optional[str] = None
    instructions: str = ""
    scripts: List[str] = []
    references: List[str] = []

class DiscoveredSkillCreateReq(BaseModel):
    name: str
    content: str
    target_location: Optional[str] = "project"
    workspace_path: Optional[str] = None
    team_id: Optional[str] = None

class SkillToggleReq(BaseModel):
    name: str
    is_active: bool
    workspace_path: Optional[str] = None
    team_id: Optional[str] = None


async def _resolve_workspace(db, user_context, workspace_path=None, team_id=None):
    if team_id:
        team = await _assert_team_access(db, team_id, user_context["sub"])
        from core.tools.file_tools import file_tools
        root = await file_tools.get_workspace_root(str(team.project_id), db=db)
        if workspace_path and Path(workspace_path).resolve() != root.resolve():
            raise HTTPException(status_code=400, detail="Workspace must match the selected team")
        return root
    return Path(workspace_path) if workspace_path else None

@router.get("/discovered", response_model=List[DiscoveredSkillRes])
async def list_discovered_skills(
    workspace_path: Optional[str] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """
    Discovers all skills from the filesystem (.agents/skills/, .carole/skills/, ~/.carole/skills/)
    and optionally from the database for the given team.
    """
    from pathlib import Path
    w_path = Path(workspace_path) if workspace_path else None
    clean_team_id = None
    if team_id and str(team_id).strip().lower() not in ("undefined", "null", "none", ""):
        try:
            uuid.UUID(str(team_id).strip())
            clean_team_id = str(team_id).strip()
        except (ValueError, TypeError, AttributeError):
            clean_team_id = None

    w_path = await _resolve_workspace(db, user_context, workspace_path, clean_team_id)
    discovered = await SkillManager.discover_all_skills(
        workspace_root=w_path,
        team_id=clean_team_id,
        db=db
    )
    return [s.to_dict() for s in discovered]

@router.post("/discovered", response_model=DiscoveredSkillRes)
async def create_discovered_skill(
    req: DiscoveredSkillCreateReq,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """
    Creates or updates a SKILL.md file in .agents/skills/<name>/ or ~/.carole/skills/<name>/.
    Immediately hot-loads the skill into the active catalog.
    """
    try:
        from pathlib import Path
        w_path = await _resolve_workspace(db, user_context, req.workspace_path, req.team_id)
        skill_def = SkillManager.save_skill_package(
            name=req.name,
            content=req.content,
            target=req.target_location or "project",
            workspace_root=w_path
        )
        return skill_def.to_dict()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to save discovered skill")
        raise HTTPException(status_code=500, detail=f"Failed to save skill: {e}")

@router.post("/discovered/upload", response_model=DiscoveredSkillRes)
async def upload_discovered_skill(
    file: UploadFile = File(...),
    target_location: str = Form("project"),
    skill_name: Optional[str] = Form(None),
    workspace_path: Optional[str] = Form(None),
    team_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """
    Uploads a .md skill file and saves it as <target_location>/skills/<skill_name>/SKILL.md.
    """
    try:
        if not (file.filename or "").lower().endswith((".md", ".txt", ".markdown")):
            raise HTTPException(status_code=400, detail="Only markdown (.md) files are accepted.")

        raw_bytes = await file.read(1024 * 1024 + 1)
        if len(raw_bytes) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Skills must be at most 1 MiB")
        content = raw_bytes.decode("utf-8", errors="replace")

        # Determine skill name
        inferred_name = skill_name
        if not inferred_name:
            stem = Path(file.filename).stem
            if stem.lower() not in ("skill", "skills", "readme"):
                inferred_name = stem
            else:
                match = re.search(r"name:\s*([a-zA-Z0-9_-]+)", content)
                if match:
                    inferred_name = match.group(1)
                else:
                    inferred_name = "uploaded-skill"

        w_path = await _resolve_workspace(db, user_context, workspace_path, team_id)
        skill_def = SkillManager.save_skill_package(
            name=inferred_name,
            content=content,
            target=target_location or "project",
            workspace_root=w_path
        )
        return skill_def.to_dict()
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to upload discovered skill")
        raise HTTPException(status_code=500, detail=f"Failed to upload skill: {e}")

@router.get("/discovered/{skill_name}/content")
async def get_discovered_skill_content(
    skill_name: str,
    workspace_path: Optional[str] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """Returns raw text content of a discovered SKILL.md file."""
    from pathlib import Path
    w_path = await _resolve_workspace(db, user_context, workspace_path, team_id)
    info = SkillManager.get_skill_content(skill_name, workspace_root=w_path)
    if not info:
        raise HTTPException(status_code=404, detail="Skill content not found.")
    return info

@router.delete("/discovered/{skill_name}")
async def delete_discovered_skill(
    skill_name: str,
    workspace_path: Optional[str] = None,
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """Deletes a discovered skill package from the filesystem."""
    from pathlib import Path
    w_path = await _resolve_workspace(db, user_context, workspace_path, team_id)
    deleted = SkillManager.delete_filesystem_skill(skill_name, workspace_root=w_path)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found or already deleted.")
    return {"status": "ok", "deleted": skill_name}

@router.post("/toggle")
async def toggle_skill(
    req: SkillToggleReq,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    """Persist active state in the selected filesystem package or team skill."""
    w_path = await _resolve_workspace(db, user_context, req.workspace_path, req.team_id)
    if SkillManager.get_skill_content(req.name, w_path):
        SkillManager.toggle_skill_state(req.name, req.is_active, w_path)
    elif req.team_id:
        skills = await SkillManager.get_team_skills(db, req.team_id, active_only=False)
        skill = next((s for s in skills if s.name == req.name), None)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        await SkillManager.update_skill(db, str(skill.id), is_active=req.is_active)
    else:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "ok", "name": req.name, "is_active": req.is_active}

@router.get("/{team_id}", response_model=List[SkillRes])
async def list_skills(
    team_id: str,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    await _assert_team_access(db, team_id, user_context["sub"])
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
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to list skills")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("", response_model=SkillRes)
async def create_skill(
    req: SkillCreateReq,
    db: AsyncSession = Depends(get_db),
    user_context: dict = Depends(require_auth)
):
    await _assert_team_access(db, req.team_id, user_context["sub"])
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
    except HTTPException:
        raise
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
    await _assert_skill_access(db, skill_id, user_context["sub"])
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
    await _assert_skill_access(db, skill_id, user_context["sub"])
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
