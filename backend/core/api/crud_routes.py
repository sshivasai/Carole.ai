"""
# backend/core/api/crud_routes.py

REST API routes for managing Projects, Teams, Agents, Tasks, and Messages.
Also provides a /api/seed endpoint for bootstrapping a demo environment.
"""

import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Union, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.memory.models import User, Project, Team, Agent, Message, Task, FileBackup, TaskComment, PlanInlineComment, CompactionEvent
from core.tools.tool_registry import ToolRegistry
from core.config import DEFAULT_FAST_MODEL
from core.auth.auth_middleware import require_auth

router = APIRouter(prefix="/api", tags=["crud"])

async def _get_human_name(db: AsyncSession, team_id: Optional[uuid.UUID] = None) -> str:
    user_name = None
    if team_id:
        stmt_team = select(Team).where(Team.id == team_id)
        team_obj = (await db.execute(stmt_team)).scalar_one_or_none()
        if team_obj:
            stmt_proj = select(Project).where(Project.id == team_obj.project_id)
            proj_obj = (await db.execute(stmt_proj)).scalar_one_or_none()
            if proj_obj and proj_obj.owner_id:
                stmt_user = select(User).where(User.id == proj_obj.owner_id)
                user_obj = (await db.execute(stmt_user)).scalar_one_or_none()
                if user_obj:
                    user_name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip()
                    if not user_name and user_obj.email:
                        user_name = user_obj.email.split("@")[0]

    if not user_name:
        stmt_user = select(User).limit(1)
        user_obj = (await db.execute(stmt_user)).scalar_one_or_none()
        if user_obj:
            user_name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip()
            if not user_name and user_obj.email:
                user_name = user_obj.email.split("@")[0]

    if not user_name:
        return "admin"

    if "(admin)" in user_name.lower():
        return user_name
        
    if user_name.lower() == "admin":
        return "admin"
        
    return f"{user_name}(admin)"


async def _assert_team_access(db: AsyncSession, team_id: str, user_id: str) -> Team:
    """
    Ownership check. Raises 400 on invalid format, 404 if team not found, 403 if user is not owner.
    """
    try:
        team = (await db.execute(
            select(Team).where(Team.id == uuid.UUID(team_id))
        )).scalar_one_or_none()
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid team_id format.")

    if not team:
        raise HTTPException(status_code=404, detail="Team not found.")

    project = (await db.execute(
        select(Project).where(Project.id == team.project_id)
    )).scalar_one_or_none()

    if not project or str(project.owner_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return team


async def _assert_project_access(db: AsyncSession, project_id: str, user_id: str) -> Project:
    """
    Ownership check. Raises 400 on invalid format, 404 if project not found, 403 if user is not owner.
    """
    try:
        p_uuid = uuid.UUID(project_id)
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid project_id format.")

    project = (await db.execute(
        select(Project).where(Project.id == p_uuid)
    )).scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    if str(project.owner_id) != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return project


async def _assert_agent_access(db: AsyncSession, agent_id: str, user_id: str) -> Agent:
    """
    Ownership check for Agent. Raises 400 on bad UUID, 404 if not found, 403 if caller does not own parent team.
    """
    try:
        a_uuid = uuid.UUID(agent_id)
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid agent_id format.")

    agent = (await db.execute(
        select(Agent).where(Agent.id == a_uuid)
    )).scalar_one_or_none()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found.")

    await _assert_team_access(db, str(agent.team_id), user_id)
    return agent


async def _assert_task_access(db: AsyncSession, task_id: str, user_id: str) -> Task:
    """
    Ownership check for Task. Raises 400 on bad UUID, 404 if not found, 403 if caller does not own parent team.
    """
    try:
        t_uuid = uuid.UUID(task_id)
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid task_id format.")

    task = (await db.execute(
        select(Task).where(Task.id == t_uuid)
    )).scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    if task.team_id:
        await _assert_team_access(db, str(task.team_id), user_id)
    return task


async def _assert_message_access(db: AsyncSession, message_id: str, user_id: str) -> Message:
    """
    Ownership check for Message. Raises 400 on bad UUID, 404 if not found, 403 if caller does not own parent team.
    """
    try:
        m_uuid = uuid.UUID(message_id)
    except (ValueError, Exception):
        raise HTTPException(status_code=400, detail="Invalid message_id format.")

    msg = await db.get(Message, m_uuid)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found.")

    if msg.team_id:
        await _assert_team_access(db, str(msg.team_id), user_id)
    return msg


# ============================================================
# Pydantic Schemas
# ============================================================

class UserCreate(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str  # No default — callers must explicitly provide a password (Finding #17)

class LearningCreate(BaseModel):
    project_id: str
    task_summary: str
    lesson_rule: str
    team_id: Optional[str] = None

class LearningUpdate(BaseModel):
    task_summary: Optional[str] = None
    lesson_rule: Optional[str] = None
    project_id: Optional[str] = None
    team_id: Optional[str] = None

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)  # Finding #13
    owner_id: Optional[str] = None
    custom_workspace_path: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    custom_workspace_path: Optional[str] = None

class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)  # Finding #13
    project_id: str

class AgentCreate(BaseModel):
    team_id: str
    name: str
    role: str
    model: str = DEFAULT_FAST_MODEL
    fallback_model: Optional[str] = None
    reasoning_effort: str = "none"  # none | low | medium | high
    system_prompt: str = ""
    personality: str = "professional"  # professional, casual, witty, mentor
    tool_permissions: dict = {}
    custom_instructions: Optional[str] = None
    skills: Optional[List[str]] = None
    auto_approve_plans: bool = False

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    reasoning_effort: Optional[str] = None  # none | low | medium | high
    system_prompt: Optional[str] = None
    personality: Optional[str] = None
    tool_permissions: Optional[dict] = None
    custom_instructions: Optional[str] = None
    skills: Optional[List[str]] = None
    # Implementation plan auto-approval for this agent
    auto_approve_plans: Optional[bool] = None

class TaskCreate(BaseModel):
    team_id: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assigned_agent_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    blocked_by_task_id: Optional[str] = None
    depends_on: Optional[List[str]] = None
    created_by: str = "human"

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    blocked_by_task_id: Optional[str] = None
    depends_on: Optional[List[str]] = None

class TaskCommentCreate(BaseModel):
    author_id: str
    author_name: str
    text: str


class McpServerCreate(BaseModel):
    team_id: str
    server_name: str
    command: str
    args: Union[List[str], str] = []  # Accepts either List[str] or raw string arguments
    agent_id: Optional[str] = None
    env_vars: Optional[dict] = None

# ============================================================
# Users / Tenants
# ============================================================

@router.post("/users")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # Finding #2 — authentication required
    from core.auth.auth_service import _hash_password
    new_user = User(
        email=body.email,
        hashed_password=_hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        is_verified=True,
    )
    db.add(new_user)
    await db.commit()
    return {"id": str(new_user.id), "email": new_user.email, "first_name": new_user.first_name, "last_name": new_user.last_name}

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # Finding #2 — authentication required
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [{"id": str(u.id), "email": u.email, "first_name": u.first_name, "last_name": u.last_name} for u in result.scalars().all()]


# ============================================================
# Projects
# ============================================================

@router.post("/projects")
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # If owner_id is provided, make sure it is valid; otherwise use authenticated caller
    owner_uuid = None
    if body.owner_id:
        try:
            owner_uuid = uuid.UUID(body.owner_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid owner_id format.")
    elif user and "sub" in user:
        try:
            owner_uuid = uuid.UUID(user["sub"])
        except Exception:
            owner_uuid = None
    if not owner_uuid:
        # fallback to first user
        users_result = await db.execute(select(User).limit(1))
        first_user = users_result.scalar_one_or_none()
        if first_user:
            owner_uuid = first_user.id
        else:
            owner_uuid = uuid.uuid4()
    
    custom_path = None
    if body.custom_workspace_path and body.custom_workspace_path.strip():
        resolved_custom = Path(body.custom_workspace_path.strip()).resolve()
        resolved_custom.mkdir(parents=True, exist_ok=True)
        custom_path = str(resolved_custom)

    project = Project(name=body.name, owner_id=owner_uuid, custom_workspace_path=custom_path)
    db.add(project)
    await db.flush()

    # Provision project workspace folder using exactly the slugified name
    import re
    from core.config import CAROLE_HOME_DIR
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', project.name).strip('-')
    if not slug:
        slug = str(project.id)[:8]
    workspace_dir = CAROLE_HOME_DIR / "workspaces" / slug
    workspace_dir.mkdir(parents=True, exist_ok=True)

    return {"id": str(project.id), "name": project.name, "custom_workspace_path": project.custom_workspace_path}

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "owner_id": str(p.owner_id),
            "custom_workspace_path": getattr(p, "custom_workspace_path", None),
        }
        for p in result.scalars().all()
    ]

@router.put("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    project = await _assert_project_access(db, project_id, user["sub"])
    from core.tools.file_tools import file_tools

    if body.custom_workspace_path is not None:
        if body.custom_workspace_path.strip():
            resolved_custom = Path(body.custom_workspace_path.strip()).resolve()
            resolved_custom.mkdir(parents=True, exist_ok=True)
            project.custom_workspace_path = str(resolved_custom)
        else:
            project.custom_workspace_path = None
        file_tools._project_workspace_cache.pop(project_id, None)
        file_tools._team_workspace_cache.clear()

    if body.name is not None and body.name != project.name:
        project.name = body.name
        file_tools._project_workspace_cache.pop(project_id, None)
        file_tools._team_workspace_cache.clear()

        # Rename workspace folder if it exists
        if not project.custom_workspace_path:
            import re
            old_dir = await file_tools.get_workspace_root(project_id)
            if old_dir.exists() and old_dir.name != "workspaces":
                new_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', body.name).strip('-')
                if not new_slug:
                    new_slug = str(project.id)[:8]
                new_dir = old_dir.parent / new_slug
                if old_dir != new_dir and not new_dir.exists():
                    old_dir.rename(new_dir)
                
    await db.flush()
    return {"status": "updated", "id": project_id, "custom_workspace_path": getattr(project, "custom_workspace_path", None)}


# ============================================================
# Learnings (Knowledge base)
# ============================================================

@router.post("/learnings")
async def create_learning(body: LearningCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.llm.multi_model_router import llm_router
    from core.memory.models import Learning
    from core.memory.lancedb_client import lancedb_client

    combined_text = f"Task: {body.task_summary} | Rule: {body.lesson_rule}"
    embedding = await llm_router.generate_embeddings(combined_text)
    
    learning = Learning(
        project_id=uuid.UUID(body.project_id),
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        task_summary=body.task_summary,
        lesson_rule=body.lesson_rule,
    )
    db.add(learning)
    await db.commit()
    await db.refresh(learning)
    
    await lancedb_client.insert_learning(
        learning_id=str(learning.id),
        project_id=body.project_id,
        team_id=body.team_id,
        task_summary=body.task_summary,
        lesson_rule=body.lesson_rule,
        vector=embedding
    )
    
    if body.team_id:
        from core.chat.message_router import message_router
        await message_router.route_message(
            text=f"[LEARNING_ADD] New team lesson learned: {body.lesson_rule}",
            sender_id="system",
            team_id=body.team_id,
            sender_name="System",
            attachments=[]
        )
    
    return {"id": str(learning.id), "task_summary": learning.task_summary, "lesson_rule": learning.lesson_rule}

@router.get("/learnings")
async def list_learnings(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import Learning
    from sqlalchemy import or_
    import uuid

    if not project_id or project_id in ("undefined", "null", ""):
        return []

    try:
        p_uuid = uuid.UUID(project_id)
    except (ValueError, TypeError):
        return []

    stmt = select(Learning).where(
        or_(
            Learning.project_id == p_uuid,
            Learning.project_id.is_(None)
        )
    ).order_by(Learning.created_at.desc())
    result = await db.execute(stmt)
    return [
        {
            "id": str(l.id),
            "task_summary": l.task_summary,
            "lesson_rule": l.lesson_rule,
            "project_id": str(l.project_id) if l.project_id else None,
            "team_id": str(l.team_id) if l.team_id else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in result.scalars().all()
    ]

@router.put("/learnings/{learning_id}")
async def update_learning(learning_id: str, body: LearningUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import Learning
    from core.memory.lancedb_client import lancedb_client
    from core.llm.multi_model_router import llm_router
    
    stmt = select(Learning).where(Learning.id == uuid.UUID(learning_id))
    result = await db.execute(stmt)
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(status_code=404, detail="Learning not found")
        
    text_changed = False
    if body.task_summary is not None and body.task_summary != learning.task_summary:
        learning.task_summary = body.task_summary
        text_changed = True
    if body.lesson_rule is not None and body.lesson_rule != learning.lesson_rule:
        learning.lesson_rule = body.lesson_rule
        text_changed = True
    if body.project_id == "null":
        learning.project_id = None
        await lancedb_client.update_project_id(learning_id, None)

    await db.commit()

    if text_changed:
        try:
            combined_text = f"Task: {learning.task_summary} | Rule: {learning.lesson_rule}"
            new_embedding = await llm_router.generate_embeddings(combined_text)
            await lancedb_client.delete_learning(learning_id)
            await lancedb_client.insert_learning(
                learning_id=learning_id,
                project_id=str(learning.project_id) if learning.project_id else "",
                team_id=str(learning.team_id) if learning.team_id else None,
                task_summary=learning.task_summary,
                lesson_rule=learning.lesson_rule,
                vector=new_embedding,
            )
        except Exception as e:
            logger.warning("LanceDB re-embedding failed during update_learning: %s", e)

    return {"status": "updated", "id": learning_id}

@router.delete("/learnings/{learning_id}")
async def delete_learning(learning_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import Learning
    from core.memory.lancedb_client import lancedb_client
    await db.execute(delete(Learning).where(Learning.id == uuid.UUID(learning_id)))
    await db.commit()
    try:
        await lancedb_client.delete_learning(learning_id)
    except Exception as e:
        logger.warning("LanceDB delete failed for %s: %s", learning_id, e)
    return {"status": "deleted", "id": learning_id}


# ============================================================
# Memory Dream Engine Telemetry & On-Demand Trigger
# ============================================================

class DreamRunRequest(BaseModel):
    team_id: Optional[str] = None


@router.post("/memory/dream/run")
async def trigger_dream_cycle(body: Optional[DreamRunRequest] = None, user: dict = Depends(require_auth)):
    """Triggers an immediate on-demand memory dream consolidation cycle."""
    from core.memory.auto_dream import dream_worker
    team_id = body.team_id if body else None
    result = await dream_worker.run_once(team_id=team_id)
    return result


@router.get("/memory/dream/status")
async def get_dream_status(user: dict = Depends(require_auth)):
    """Returns real-time operational telemetry for the Auto-Dream consolidation engine."""
    from core.memory.auto_dream import dream_worker
    return dream_worker.get_status()



# ============================================================
# Teams
# ============================================================

@router.post("/teams")
async def create_team(body: TeamCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_project_access(db, body.project_id, user["sub"])
    team = Team(name=body.name, project_id=uuid.UUID(body.project_id))
    db.add(team)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "project_id": str(team.project_id)}


@router.get("/teams/{project_id}")
async def list_teams(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_project_access(db, project_id, user["sub"])
    result = await db.execute(
        select(Team).where(Team.project_id == uuid.UUID(project_id)).order_by(Team.created_at.desc())
    )
    return [{"id": str(t.id), "name": t.name} for t in result.scalars().all()]


# ============================================================
# Agents
# ============================================================

@router.post("/agents")
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_team_access(db, body.team_id, user["sub"])
    prompt = body.system_prompt or _default_system_prompt(body.name, body.role, body.personality)
    
    if body.custom_instructions:
        prompt += f"\n\nSPECIAL CUSTOM INSTRUCTIONS:\n{body.custom_instructions}"
        
    if body.skills and len(body.skills) > 0:
        skills_text = "\n".join(f"- {s}" for s in body.skills)
        prompt += f"\n\nSPECIALIZED SKILLS & TOOLKITS:\n{skills_text}"

    agent = Agent(
        team_id=uuid.UUID(body.team_id),
        name=body.name,
        role=body.role,
        model=body.model,
        fallback_model=body.fallback_model or None,
        reasoning_effort=body.reasoning_effort or "none",
        system_prompt=prompt,
        personality=body.personality,
        custom_instructions=body.custom_instructions,
        skills=body.skills or [],
        tool_permissions=body.tool_permissions,
        auto_approve_plans=body.auto_approve_plans or False,
    )
    db.add(agent)
    await db.commit()

    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{agent.team_id}", {
        "type": "agent_created",
        "agent": {
            "id": str(agent.id), "name": agent.name, "role": agent.role,
            "model": agent.model, "fallback_model": agent.fallback_model,
            "reasoning_effort": agent.reasoning_effort or "none",
            "team_id": str(agent.team_id),
            "personality": agent.personality, "skills": agent.skills or [],
            "custom_instructions": agent.custom_instructions,
            "tool_permissions": agent.tool_permissions,
        }
    })

    from core.chat.message_router import message_router
    human_name = await _get_human_name(db, agent.team_id)
    await message_router.route_message(
        text=f"[AGENT_ADD] New agent @{agent.name} joined the team (Added by {human_name})",
        sender_id="system",
        team_id=str(agent.team_id),
        sender_name="System",
        attachments=[]
    )

    return {
        "id": str(agent.id), "name": agent.name, "role": agent.role,
        "model": agent.model, "fallback_model": agent.fallback_model,
        "reasoning_effort": agent.reasoning_effort,
        "team_id": str(agent.team_id),
        "personality": agent.personality, "skills": agent.skills,
        "custom_instructions": agent.custom_instructions,
        "auto_approve_plans": agent.auto_approve_plans,
    }

@router.get("/agents/{team_id}")
async def list_agents(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # Finding #8 — ownership check
    await _assert_team_access(db, team_id, user["sub"])
    result = await db.execute(
        select(Agent).where(Agent.team_id == uuid.UUID(team_id)).order_by(Agent.created_at)
    )
    return [
        {
            "id": str(a.id), "name": a.name, "role": a.role,
            "model": a.model, "fallback_model": a.fallback_model,
            "reasoning_effort": a.reasoning_effort or "none",
            "tool_permissions": a.tool_permissions,
            "personality": a.personality, "skills": a.skills or [],
            "custom_instructions": a.custom_instructions,
        }
        for a in result.scalars().all()
    ]

@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    agent = await _assert_agent_access(db, agent_id, user["sub"])
    if body.name is not None:
        agent.name = body.name
    if body.role is not None:
        agent.role = body.role
    if body.model is not None:
        agent.model = body.model
    if body.fallback_model is not None:
        # Allow clearing the fallback by sending empty string
        agent.fallback_model = body.fallback_model.strip() or None
    if body.reasoning_effort is not None:
        agent.reasoning_effort = body.reasoning_effort
    if body.tool_permissions is not None:
        agent.tool_permissions = body.tool_permissions
    if body.personality is not None:
        agent.personality = body.personality
    if body.custom_instructions is not None:
        agent.custom_instructions = body.custom_instructions
    if body.skills is not None:
        agent.skills = body.skills
    if body.auto_approve_plans is not None:
        agent.auto_approve_plans = body.auto_approve_plans
    # Rebuild system prompt if role/name/personality/skills/instructions changed
    rebuild = any(x is not None for x in [body.system_prompt, body.name, body.role, body.personality, body.skills, body.custom_instructions])
    if rebuild:
        if body.system_prompt is not None:
            agent.system_prompt = body.system_prompt
        else:
            prompt = _default_system_prompt(agent.name, agent.role, agent.personality or "professional")
            if agent.custom_instructions:
                prompt += f"\n\nSPECIAL CUSTOM INSTRUCTIONS:\n{agent.custom_instructions}"
            if agent.skills and len(agent.skills) > 0:
                skills_text = "\n".join(f"- {s}" for s in agent.skills)
                prompt += f"\n\nSPECIALIZED SKILLS & TOOLKITS:\n{skills_text}"
            agent.system_prompt = prompt
    await db.commit()

    from core.chat.event_bus import event_bus
    agent_payload = {
        "id": str(agent.id), "name": agent.name, "role": agent.role,
        "model": agent.model, "fallback_model": agent.fallback_model,
        "reasoning_effort": agent.reasoning_effort or "none",
        "team_id": str(agent.team_id),
        "personality": agent.personality, "skills": agent.skills or [],
        "custom_instructions": agent.custom_instructions,
        "tool_permissions": agent.tool_permissions,
    }
    await event_bus.publish(f"team:{agent.team_id}", {
        "type": "agent_updated",
        "agent": agent_payload,
    })

    from core.chat.message_router import message_router
    human_name = await _get_human_name(db, agent.team_id)
    await message_router.route_message(
        text=f"[AGENT_UPDATE] @{agent.name}'s configuration was updated by {human_name}",
        sender_id="system",
        team_id=str(agent.team_id),
        sender_name="System",
        attachments=[]
    )

    return {
        "id": str(agent.id), "name": agent.name, "role": agent.role,
        "model": agent.model, "fallback_model": agent.fallback_model,
        "reasoning_effort": agent.reasoning_effort,
        "team_id": str(agent.team_id),
        "personality": agent.personality, "skills": agent.skills,
        "custom_instructions": agent.custom_instructions,
        "tool_permissions": agent.tool_permissions,
        "auto_approve_plans": agent.auto_approve_plans,
    }

@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    agent = await _assert_agent_access(db, agent_id, user["sub"])
    team_id_str = str(agent.team_id)
    await db.execute(delete(Agent).where(Agent.id == agent.id))
    await db.commit()
    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{team_id_str}", {
        "type": "agent_deleted",
        "agent_id": str(agent_id),
    })
    from core.chat.message_router import message_router
    human_name = await _get_human_name(db, agent.team_id)
    await message_router.route_message(
        text=f"[AGENT_REMOVE] @{agent.name} was removed from the team by {human_name}",
        sender_id="system",
        team_id=team_id_str,
        sender_name="System",
        attachments=[]
    )
    return {"status": "deleted", "id": agent_id}


@router.post("/agents/{agent_id}/clone")
async def clone_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Clone an existing agent within the same team.

    Duplicates the agent's name, role, model, system_prompt, skills,
    tool_permissions, and personality. The new agent is appended with ' (Copy)'.
    """
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify the requesting user owns this agent's team
    await _assert_team_access(db, str(source.team_id), user["sub"])

    new_agent = Agent(
        id=uuid.uuid4(),
        team_id=source.team_id,
        name=f"{source.name} (Copy)",
        role=source.role,
        model=source.model,
        fallback_model=source.fallback_model,
        reasoning_effort=source.reasoning_effort,
        system_prompt=source.system_prompt,
        personality=source.personality,
        skills=list(source.skills) if source.skills else [],
        tool_permissions=dict(source.tool_permissions) if source.tool_permissions else {},
        custom_instructions=source.custom_instructions,
    )
    db.add(new_agent)
    await db.commit()
    await db.refresh(new_agent)
    return {
        "id": str(new_agent.id),
        "name": new_agent.name,
        "role": new_agent.role,
        "model": new_agent.model,
        "team_id": str(new_agent.team_id),
    }


# ============================================================
# Delete endpoints for Projects, Teams, Users
# ============================================================

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, delete_content: bool = False, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_project_access(db, project_id, user["sub"])
    if delete_content:
        import shutil
        from core.tools.file_tools import file_tools
        try:
            workspace_dir = await file_tools.get_workspace_root(project_id)
            if workspace_dir.exists() and workspace_dir.name != "workspaces":
                shutil.rmtree(str(workspace_dir))
        except Exception as e:
            import logging
            logging.getLogger("carole.crud").warning("Failed to delete project folder: %s", e)

    await db.execute(delete(Project).where(Project.id == uuid.UUID(project_id)))
    return {"status": "deleted", "id": project_id}

@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, delete_content: bool = False, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_team_access(db, team_id, user["sub"])
    if delete_content:
        import shutil
        from core.tools.file_tools import file_tools
        try:
            # Use get_team_carole_dir to resolve the correct path:
            # workspaces/<project_slug>/.carole/<team_slug>
            team_carole_dir = await file_tools.get_team_carole_dir(team_id, db=db)
            if team_carole_dir.exists():
                shutil.rmtree(str(team_carole_dir))
        except Exception as e:
            import logging
            logging.getLogger("carole.crud").warning("Failed to delete team folder: %s", e)

    await db.execute(delete(Team).where(Team.id == uuid.UUID(team_id)))
    return {"status": "deleted", "id": team_id}

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # Verify caller can only delete their own account (IDOR protection)
    if user.get("sub") != user_id:
        raise HTTPException(status_code=403, detail="You can only delete your own account.")
    await db.execute(delete(User).where(User.id == uuid.UUID(user_id)))
    return {"status": "deleted", "id": user_id}


# ============================================================
# Single-entity GET endpoints
# ============================================================

@router.get("/projects/single/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    p = await _assert_project_access(db, project_id, user["sub"])
    return {
        "id": str(p.id),
        "name": p.name,
        "owner_id": str(p.owner_id),
        "custom_workspace_path": getattr(p, "custom_workspace_path", None),
    }

@router.get("/teams/single/{team_id}")
async def get_team(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    t = await _assert_team_access(db, team_id, user["sub"])
    return {"id": str(t.id), "name": t.name, "project_id": str(t.project_id)}


# ============================================================
# Implementation Plan & Todo Routes
# ============================================================

class PlanReviewBody(BaseModel):
    feedback: Optional[str] = None  # rejection reason or revision notes

class PlanInlineCommentCreate(BaseModel):
    line_index: int
    text: str

class PlanEditBody(BaseModel):
    plan_markdown: str

class TodoUpdateBody(BaseModel):
    todos: Optional[List[dict]] = None   # full replacement list
    toggle_id: Optional[str] = None      # single item toggle


@router.get("/tasks/{task_id}/plan")
async def get_task_plan(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Return the implementation plan, status, feedback, todos, and inline comments for a task."""
    task = await _assert_task_access(db, task_id, user["sub"])

    comments = (await db.execute(
        select(PlanInlineComment)
        .where(PlanInlineComment.task_id == task.id)
        .order_by(PlanInlineComment.line_index.asc(), PlanInlineComment.created_at.asc())
    )).scalars().all()

    return {
        "task_id": str(task.id),
        "title": task.title,
        "plan_file_path": task.plan_file_path,
        "implementation_plan": task.implementation_plan,
        "plan_status": task.plan_status,
        "plan_feedback": task.plan_feedback,
        "todo_list": task.todo_list or [],
        "inline_comments": [
            {
                "id": str(c.id),
                "line_index": c.line_index,
                "author_id": c.author_id,
                "author_name": c.author_name,
                "text": c.text,
                "resolved": c.resolved,
                "created_at": c.created_at.isoformat() + "Z" if c.created_at else None,
            }
            for c in comments
        ]
    }


@router.post("/tasks/{task_id}/plan/approve")
async def approve_task_plan(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Approve an implementation plan — allows the agent to begin execution."""
    task = await _assert_task_access(db, task_id, user["sub"])
    task.plan_status = "approved"
    task.plan_feedback = None
    if task.status in ("blocked", "todo"):
        task.status = "in_progress"
    await db.commit()

    # Notify the agent via event bus so its ReAct loop can resume
    from core.chat.event_bus import event_bus
    human_name = await _get_human_name(db, task.team_id)
    team_id_str = str(task.team_id)
    await event_bus.publish(f"team:{team_id_str}", {
        "type": "plan_approved",
        "task_id": str(task.id),
        "task_title": task.title,
        "approved_by": human_name,
    })

    # Route a chat message so the agent sees the approval
    from core.chat.message_router import message_router
    approval_msg = f"[PLAN_APPROVED] {human_name} approved the implementation plan for task '{task.title}'. You may now begin execution."
    await message_router.route_message(
        text=approval_msg,
        sender_id="system",
        team_id=team_id_str,
        sender_name="System",
        attachments=[]
    )

    # Wake assigned agent
    if task.assigned_agent_id:
        agent_stmt = select(Agent).where(Agent.id == task.assigned_agent_id)
        assigned_agent = (await db.execute(agent_stmt)).scalar_one_or_none()
        if assigned_agent:
            await message_router._enqueue_agent(assigned_agent, approval_msg, db)

    return {"status": "approved", "task_id": task_id}


@router.post("/tasks/{task_id}/plan/reject")
async def reject_task_plan(
    task_id: str,
    body: PlanReviewBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Reject a plan with optional feedback, asking the agent to revise."""
    task = await _assert_task_access(db, task_id, user["sub"])
    task.plan_status = "revision_requested"
    task.plan_feedback = body.feedback
    await db.commit()

    from core.chat.event_bus import event_bus
    human_name = await _get_human_name(db, task.team_id)
    team_id_str = str(task.team_id)
    await event_bus.publish(f"team:{team_id_str}", {
        "type": "plan_rejected",
        "task_id": str(task.id),
        "task_title": task.title,
        "feedback": body.feedback,
    })

    from core.chat.message_router import message_router
    feedback_text = f" Feedback: {body.feedback}" if body.feedback else ""
    reject_msg = f"[PLAN_REJECTED] {human_name} requested revisions to the plan for task '{task.title}'.{feedback_text} Please update your implementation plan and re-submit with request_plan_approval."
    await message_router.route_message(
        text=reject_msg,
        sender_id="system",
        team_id=team_id_str,
        sender_name="System",
        attachments=[]
    )

    # Wake assigned agent to address revisions
    if task.assigned_agent_id:
        agent_stmt = select(Agent).where(Agent.id == task.assigned_agent_id)
        assigned_agent = (await db.execute(agent_stmt)).scalar_one_or_none()
        if assigned_agent:
            await message_router._enqueue_agent(assigned_agent, reject_msg, db)

    return {"status": "revision_requested", "task_id": task_id}


@router.post("/tasks/{task_id}/plan/comment")
async def add_plan_inline_comment(
    task_id: str,
    body: PlanInlineCommentCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Add an inline comment anchored to a specific line in the implementation plan."""
    task = await _assert_task_access(db, task_id, user["sub"])

    human_name = await _get_human_name(db, task.team_id)
    comment = PlanInlineComment(
        task_id=task.id,
        line_index=body.line_index,
        author_id=str(user["sub"]),
        author_name=human_name,
        text=body.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    # Notify the team so the agent can see the comment
    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{task.team_id}", {
        "type": "plan_comment_added",
        "task_id": str(task.id),
        "comment": {
            "id": str(comment.id),
            "line_index": comment.line_index,
            "author_name": comment.author_name,
            "text": comment.text,
        }
    })
    return {
        "id": str(comment.id),
        "line_index": comment.line_index,
        "author_name": comment.author_name,
        "text": comment.text,
        "resolved": comment.resolved,
    }


@router.patch("/tasks/{task_id}/plan")
async def edit_task_plan(
    task_id: str,
    body: PlanEditBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Edit the plan markdown directly (admin inline edit). Resets status to awaiting_approval."""
    task = await _assert_task_access(db, task_id, user["sub"])

    task.implementation_plan = body.plan_markdown
    task.plan_status = "awaiting_approval"

    # Also overwrite the disk file if path exists
    if task.plan_file_path:
        try:
            from pathlib import Path
            Path(task.plan_file_path).write_text(body.plan_markdown, encoding="utf-8")
        except Exception:
            pass

    await db.commit()
    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{task.team_id}", {
        "type": "task_update",
        "action": "plan_edited",
        "task": {"id": str(task.id), "title": task.title, "plan_status": task.plan_status}
    })
    return {"status": "updated", "plan_status": task.plan_status}


@router.patch("/tasks/{task_id}/todos")
async def update_task_todos_api(
    task_id: str,
    body: TodoUpdateBody,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Update the interactive todo checklist for a task (admin-triggered toggle or full reset)."""
    task = await _assert_task_access(db, task_id, user["sub"])

    from core.tools.task_tools import task_tools
    result_msg = await task_tools.update_task_todos(
        task_id=task_id,
        team_id=str(task.team_id),
        todos=body.todos,
        toggle_id=body.toggle_id,
    )
    return {"status": "ok", "message": result_msg, "todo_list": task.todo_list}


# ============================================================
# Messages
# ============================================================

@router.get("/messages/{team_id}")
async def list_messages(
    team_id: str,
    limit: int = 100,
    before: Optional[str] = None,  # cursor: return messages older than this message id
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """List messages for a team with optional cursor-based pagination.

    Use the `before` param (a message id) to load older messages beyond the
    initial page — enables the "Load older messages" button in the UI.
    """
    # Finding #8 — verify the authenticated user owns this team
    await _assert_team_access(db, team_id, user["sub"])
    # Clamp limit to prevent large data dumps
    limit = min(limit, 500)
    from sqlalchemy import nulls_last

    query = select(Message).where(Message.team_id == uuid.UUID(team_id))

    # Cursor pagination: if 'before' is provided, only return messages created
    # before that message's created_at timestamp (older messages).
    if before:
        try:
            cursor_msg = (await db.execute(
                select(Message).where(Message.id == uuid.UUID(before))
            )).scalar_one_or_none()
            if cursor_msg and cursor_msg.created_at:
                query = query.where(Message.created_at < cursor_msg.created_at)
        except (ValueError, Exception):
            pass  # Invalid cursor — just return latest page

    result = await db.execute(
        query
        .order_by(Message.created_at.desc(), nulls_last(Message.sequence.desc()))
        .limit(limit)
    )
    messages = result.scalars().all()
    # messages were ordered desc, so we reverse them for chronological UI presentation
    messages.reverse()
    return [
        {
            "id": str(m.id), "sender_id": m.sender_id,
            "sender_name": getattr(m, "sender_name", None),
            "recipient_id": m.recipient_id, "text": m.text,
            "is_private": getattr(m, "is_private", False),
            "created_at": (m.created_at.isoformat() + "Z") if m.created_at and "+" not in m.created_at.isoformat() and not m.created_at.isoformat().endswith("Z") else (m.created_at.isoformat() if m.created_at else None),
            "reasoning": getattr(m, "reasoning_text", None),
            "attachments": getattr(m, "attachments", []) or [],
            "is_intermediate": getattr(m, "is_intermediate", False),
        }
        for m in messages
    ]


@router.get("/teams/{team_id}/export")
async def export_messages(
    team_id: str,
    format: str = "json",
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Export all messages for a team as JSON or Markdown.

    Useful for archiving conversation history or creating fine-tuning datasets.
    Supported formats: json | markdown
    """
    await _assert_team_access(db, team_id, user["sub"])
    from sqlalchemy import nulls_last
    from fastapi.responses import PlainTextResponse
    import json as _json

    result = await db.execute(
        select(Message)
        .where(Message.team_id == uuid.UUID(team_id))
        .where(Message.is_intermediate == False)  # noqa: E712
        .order_by(Message.created_at.asc(), nulls_last(Message.sequence.asc()))
    )
    msgs = result.scalars().all()

    if format == "markdown":
        lines = ["# Conversation Export\n"]
        for m in msgs:
            ts = m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else ""
            sender = getattr(m, "sender_name", None) or m.sender_id or "Unknown"
            lines.append(f"### {sender} ({ts})\n")
            lines.append((m.text or "") + "\n\n")
        return PlainTextResponse(
            content="".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="export-{team_id[:8]}.md"'}
        )
    else:
        payload = [
            {
                "id": str(m.id),
                "sender_name": getattr(m, "sender_name", None),
                "text": m.text,
                "created_at": m.created_at.isoformat() + "Z" if m.created_at else None,
                "attachments": getattr(m, "attachments", []) or [],
            }
            for m in msgs
        ]
        return PlainTextResponse(
            content=_json.dumps(payload, indent=2, default=str),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="export-{team_id[:8]}.json"'}
        )


@router.get("/messages/search/{team_id}")
async def search_messages(team_id: str, q: str = "", limit: int = 20, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Full-text search over persisted messages for a team."""
    # Finding #8 — ownership check
    await _assert_team_access(db, team_id, user["sub"])
    # Finding #5 — enforce minimum length and escape LIKE metacharacters to prevent wildcard DoS
    if not q.strip() or len(q.strip()) < 2:
        return []
    limit = min(limit, 50)  # cap to prevent large result dumps
    # Escape % and _ so they are treated as literals, not SQL wildcards
    q_escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = await db.execute(
        select(Message)
        .where(Message.team_id == uuid.UUID(team_id))
        .where(Message.text.ilike(f"%{q_escaped}%", escape="\\"))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id), "sender_id": m.sender_id,
            "sender_name": getattr(m, "sender_name", None),
            "text": m.text,
            "created_at": (m.created_at.isoformat() + "Z") if m.created_at else None,
            "reasoning": getattr(m, "reasoning_text", None),
            "attachments": getattr(m, "attachments", []) or [],
            "is_intermediate": getattr(m, "is_intermediate", False),
        }
        for m in messages
    ]


# ─── Scratchpad endpoints live in core/api/scratchpad_routes.py ──────────────



import os
from core.config import CAROLE_HOME_DIR as _CAROLE_HOME_DIR

# Fallback upload directory — only used if team_id is not provided or resolution fails.
_UPLOAD_DIR = str(_CAROLE_HOME_DIR / "uploads")
os.makedirs(_UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...), team_id: Optional[str] = None, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Handles file uploads for multimodal chat support, organizing them by workspace."""
    import uuid
    import os
    from core.config import CAROLE_HOME_DIR
    import os as _os
    
    # Validate file size (50 MB max)
    MAX_SIZE = 50 * 1024 * 1024
    
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    
    # Validate file extension against safe allowlist to prevent arbitrary code/XSS uploads
    ALLOWED_UPLOAD_EXTS = {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg",
        ".pdf", ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
        ".mp3", ".wav", ".ogg", ".webm", ".m4a", ".mp4",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz"
    }
    if ext and ext not in ALLOWED_UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"File extension '{ext}' is not allowed for security reasons."
        )

    filename = f"{file_id}{ext}"
    
    upload_dir = _UPLOAD_DIR  # fallback
    url_path = f"/api/uploads/{filename}"
    
    if team_id:
        team = await _assert_team_access(db, team_id, user["sub"])
        stmt = select(Project).where(Project.id == team.project_id)
        res = await db.execute(stmt)
        project = res.scalar_one_or_none()
        if project:
            import re
            proj_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', project.name).strip('-')
            team_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', team.name).strip('-')
            from core.tools.file_tools import file_tools
            team_carole_dir = await file_tools.get_team_carole_dir(team_id)
            upload_dir = str(team_carole_dir / "Chat_Media")
            os.makedirs(upload_dir, exist_ok=True)
            url_path = f"/api/media/{proj_slug}/{team_slug}/{filename}"
                
    file_path = os.path.join(upload_dir, filename)
    
    # Async-safe chunked write
    import aiofiles
    total = 0
    try:
        async with aiofiles.open(file_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1 MB chunks
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SIZE:
                    await out.close()
                    os.unlink(file_path)
                    raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")
                await out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")
    
    # Derive the base URL dynamically from request host if PUBLIC_API_URL is not set
    base_url = os.getenv("PUBLIC_API_URL")
    if not base_url or "localhost:8001" in base_url or "127.0.0.1:8001" in base_url:
        base_url = str(request.base_url).rstrip("/")

        
    return {
        "id": file_id,
        "url": f"{base_url}{url_path}",
        "name": file.filename,
        "type": file.content_type,
        "local_path": file_path
    }

from fastapi.responses import FileResponse
import re as _re_slug

@router.get("/media/{project_slug}/{team_slug}/{filename}")
async def get_chat_media(project_slug: str, team_slug: str, filename: str):
    """Serves chat media files from the workspace directory."""
    from core.config import CAROLE_HOME_DIR
    
    # Path traversal protection
    for part in (filename, project_slug, team_slug):
        if ".." in part or "/" in part or "\\" in part:
            raise HTTPException(status_code=400, detail="Invalid path component")
        
    file_path = CAROLE_HOME_DIR / "workspaces" / project_slug / ".carole" / team_slug / "Chat_Media" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(path=file_path)

# Serve from the fallback uploads dir too
@router.get("/uploads/{filename}")
async def get_upload_file(filename: str):
    """Serves files from the fallback uploads directory."""
    from core.config import CAROLE_HOME_DIR
    
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    file_path = CAROLE_HOME_DIR / "uploads" / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path)

class MessageEdit(BaseModel):
    text: str


@router.put("/messages/{message_id}")
async def edit_message(message_id: str, body: MessageEdit, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Edit a single message's text only. No deletion, no rollback."""
    msg = await _assert_message_access(db, message_id, user["sub"])
    msg.text = body.text.strip()
    await db.commit()
    return {"ok": True, "id": message_id, "text": msg.text}


@router.delete("/messages/{message_id}")
async def delete_message(message_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Delete a single message only. No rollback, no cascade to later messages."""
    msg = await _assert_message_access(db, message_id, user["sub"])
    team_id = str(msg.team_id)
    await db.delete(msg)
    await db.commit()

    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{team_id}", {
        "type": "message_deleted",
        "message_id": message_id,
    })
    return {"ok": True}


@router.delete("/teams/{team_id}/messages")
async def clear_team_chat(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Delete all messages for a team permanently and cascade to memory & compactions."""
    from sqlalchemy import delete, update
    import shutil
    from core.tools.file_tools import file_tools
    from core.memory.models import Learning, EntityMemory, GraphTriple, CompactionEvent, FileBackup
    from core.memory.lancedb_client import lancedb_client
    
    await _assert_team_access(db, team_id, user["sub"])
    team_uuid = uuid.UUID(team_id)

    # 1. Unlink message_id on FileBackup records to ensure foreign key safety
    try:
        await db.execute(
            update(FileBackup)
            .where(FileBackup.team_id == team_uuid)
            .values(message_id=None)
        )
    except Exception as e:
        import logging as _log
        _log.getLogger("carole.chat").warning(f"Failed to unlink file backups before clearing messages: {e}")

    # 2. Delete DB Messages
    stmt = delete(Message).where(Message.team_id == team_uuid)
    await db.execute(stmt)

    # 3. Cascade delete CompactionEvents, Learnings, EntityMemory, and GraphTriples for this team
    try:
        await db.execute(delete(CompactionEvent).where(CompactionEvent.team_id == team_uuid))
        await db.execute(delete(Learning).where(Learning.team_id == team_uuid))
        await db.execute(delete(EntityMemory).where(EntityMemory.team_id == team_uuid))
        await db.execute(delete(GraphTriple).where(GraphTriple.team_id == team_uuid))
        # Purge from LanceDB vector store as well
        await lancedb_client.delete_by_team(str(team_uuid))
    except Exception as mem_err:
        import logging as _log
        _log.getLogger("carole.chat").warning(f"Failed to clear memories for team {team_id}: {mem_err}")

    await db.commit()

    # 4. Delete Chat Media from Disk
    try:
        team_carole_dir = await file_tools.get_team_carole_dir(team_id)
        chat_media_dir = team_carole_dir / "Chat_Media"
        if chat_media_dir.exists():
            shutil.rmtree(chat_media_dir)
    except Exception as e:
        import logging as _log
        _log.getLogger("carole.upload").warning(f"Failed to clear Chat_Media for team {team_id}: {e}")

    from core.chat.event_bus import event_bus
    await event_bus.publish(f"team:{team_id}", {
        "type": "chat_cleared"
    })
    return {"ok": True}


@router.delete("/messages/{message_id}/rollback")
async def rollback_from_message(message_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Rollback: checkpoint restoration.
    1. Delete target message AND all messages that came after it in the same team.
    2. Replay FileBackup records to restore workspace files and unlink newly created files.
    3. Delete Tasks created >= pivot_time, delete their plan files and comments; reset modified tasks.
    4. Delete Learnings, EntityMemories, GraphTriples, and CompactionEvents created >= pivot_time.
    5. Delete associated vectors from LanceDB.
    6. Broadcast file_change, task_deleted, task_update, and message_rewind events.
    """
    from fastapi import HTTPException
    from sqlalchemy import delete as sa_delete, select, update, or_
    from pathlib import Path
    import shutil
    import logging as _rlog
    _rollback_log = _rlog.getLogger("carole.rollback")
    from core.memory.models import (
        FileBackup, Task, TaskComment, PlanInlineComment,
        Learning, EntityMemory, GraphTriple, CompactionEvent
    )
    from core.memory.lancedb_client import lancedb_client
    from core.chat.event_bus import event_bus

    msg = await _assert_message_access(db, message_id, user["sub"])

    team_id_uuid = msg.team_id
    team_id_str = str(team_id_uuid)
    pivot_time = msg.created_at

    # 1. Find all messages >= pivot time (inclusive of this message)
    later_msgs = (await db.execute(
        select(Message)
        .where(Message.team_id == team_id_uuid)
        .where(Message.created_at >= pivot_time)
        .order_by(Message.created_at.desc())  # newest first for rollback order
    )).scalars().all()

    later_ids = [m.id for m in later_msgs]

    # 2. Collect file backups for those messages/team within the rollback window.
    backup_query = select(FileBackup).where(
        or_(
            FileBackup.message_id.in_(later_ids),
            (FileBackup.team_id == team_id_uuid) & (FileBackup.created_at >= pivot_time)
        ) if later_ids else ((FileBackup.team_id == team_id_uuid) & (FileBackup.created_at >= pivot_time))
    ).order_by(FileBackup.created_at.asc())

    backups = (await db.execute(backup_query)).scalars().all()

    # 3. Restore files (oldest snapshot per path is the original state)
    restored: list = []
    deleted_files: list = []
    seen_paths = set()
    for bk in backups:
        if bk.file_path in seen_paths:
            continue
        seen_paths.add(bk.file_path)
        p = Path(bk.file_path)
        try:
            if bk.backup_file_name is None:
                # File was newly created — delete it
                if p.exists():
                    p.unlink()
                deleted_files.append(bk.file_path)
            else:
                # File was modified — restore original from copy-on-write buffer
                from core.tools.file_tools import file_tools
                team_carole_dir = await file_tools.get_team_carole_dir(team_id_str, db=db)
                history_dir = team_carole_dir / "file-history"
                backup_path = history_dir / bk.backup_file_name
                
                if backup_path.exists():
                    p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_path, p)
                    restored.append(bk.file_path)
                else:
                    _rollback_log.error("Missing backup file for rollback: %s", backup_path)
        except Exception as e:
            _rollback_log.warning("Rollback failed for %s: %s", bk.file_path, e)

    # 4. Delete FileBackup records for rolled-back changes
    backup_ids = [bk.id for bk in backups]
    if backup_ids:
        await db.execute(
            sa_delete(FileBackup).where(FileBackup.id.in_(backup_ids))
        )

    # 5. Rollback Tasks created during or after pivot_time
    deleted_task_ids = []
    newly_created_tasks = (await db.execute(
        select(Task)
        .where(Task.team_id == team_id_uuid)
        .where(Task.created_at >= pivot_time)
    )).scalars().all()

    for t in newly_created_tasks:
        task_id_str = str(t.id)
        deleted_task_ids.append(task_id_str)
        # Remove plan file if generated
        if t.plan_file_path:
            try:
                plan_p = Path(t.plan_file_path)
                if plan_p.exists():
                    plan_p.unlink()
            except Exception as pe:
                _rollback_log.warning("Failed to delete plan file %s: %s", t.plan_file_path, pe)

        # Delete comments and inline plan comments
        await db.execute(sa_delete(TaskComment).where(TaskComment.task_id == t.id))
        await db.execute(sa_delete(PlanInlineComment).where(PlanInlineComment.task_id == t.id))
        await db.delete(t)

    # Reset tasks that were created before pivot_time but updated after pivot_time
    modified_older_tasks = (await db.execute(
        select(Task)
        .where(Task.team_id == team_id_uuid)
        .where(Task.created_at < pivot_time)
        .where(Task.updated_at >= pivot_time)
    )).scalars().all()

    for ot in modified_older_tasks:
        ot.status = "todo"
        ot.plan_status = "draft"
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "task_update",
            "task_id": str(ot.id),
            "status": "todo",
            "plan_status": "draft",
        })

    # 6. Delete Learnings, EntityMemories, GraphTriples, and CompactionEvents
    rolled_back_learnings = (await db.execute(
        select(Learning)
        .where(Learning.team_id == team_id_uuid)
        .where(Learning.created_at >= pivot_time)
    )).scalars().all()
    learning_ids_to_purge = [str(l.id) for l in rolled_back_learnings]

    if learning_ids_to_purge:
        await lancedb_client.delete_learnings_batch(learning_ids_to_purge)
        await db.execute(
            sa_delete(Learning).where(Learning.id.in_([l.id for l in rolled_back_learnings]))
        )

    await db.execute(
        sa_delete(EntityMemory)
        .where(EntityMemory.team_id == team_id_uuid)
        .where(EntityMemory.created_at >= pivot_time)
    )
    await db.execute(
        sa_delete(GraphTriple)
        .where(GraphTriple.team_id == team_id_uuid)
        .where(GraphTriple.created_at >= pivot_time)
    )
    await db.execute(
        sa_delete(CompactionEvent)
        .where(CompactionEvent.team_id == team_id_uuid)
        .where(CompactionEvent.created_at >= pivot_time)
    )

    # 7. Delete the messages themselves
    for m in later_msgs:
        await db.delete(m)
    await db.commit()

    # 8. Broadcast file_change events
    for fp in restored:
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "file_change",
            "action": "rollback_restore",
            "path": fp,
            "diff": None,
        })
    for fp in deleted_files:
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "file_change",
            "action": "rollback_delete",
            "path": fp,
            "diff": None,
        })

    # Broadcast task_deleted events
    for tid in deleted_task_ids:
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "task_deleted",
            "task_id": tid,
        })

    pivot_time_iso = (
        (pivot_time.isoformat() + "Z")
        if pivot_time and "+" not in pivot_time.isoformat() and not pivot_time.isoformat().endswith("Z")
        else (pivot_time.isoformat() if pivot_time else None)
    )

    # 9. Broadcast rewind event
    await event_bus.publish(f"team:{team_id_str}", {
        "type": "message_rewind",
        "from_message_id": message_id,
        "from_timestamp": pivot_time_iso,
        "restored_files": restored,
        "deleted_files": deleted_files,
        "deleted_task_ids": deleted_task_ids,
    })

    return {
        "ok": True,
        "deleted_count": len(later_msgs),
        "restored_files": restored,
        "deleted_files": deleted_files,
        "deleted_task_ids": deleted_task_ids,
    }


@router.delete("/projects/{project_id}/memory")
async def purge_project_memory(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Purge all long-term memory (learnings, entity facts, graph triples) for a project."""
    from sqlalchemy import delete, select
    from core.memory.models import Learning, EntityMemory, GraphTriple, CompactionEvent, Team
    from core.memory.lancedb_client import lancedb_client

    await _assert_project_access(db, project_id, user["sub"])
    proj_uuid = uuid.UUID(project_id)

    # Find team IDs belonging to this project
    team_rows = (await db.execute(select(Team.id).where(Team.project_id == proj_uuid))).scalars().all()
    team_uuids = list(team_rows)

    # Delete SQLite memories
    if team_uuids:
        await db.execute(delete(Learning).where((Learning.project_id == proj_uuid) | (Learning.team_id.in_(team_uuids))))
        await db.execute(delete(EntityMemory).where((EntityMemory.project_id == proj_uuid) | (EntityMemory.team_id.in_(team_uuids))))
        await db.execute(delete(GraphTriple).where((GraphTriple.project_id == proj_uuid) | (GraphTriple.team_id.in_(team_uuids))))
        await db.execute(delete(CompactionEvent).where(CompactionEvent.team_id.in_(team_uuids)))
    else:
        await db.execute(delete(Learning).where(Learning.project_id == proj_uuid))
        await db.execute(delete(EntityMemory).where(EntityMemory.project_id == proj_uuid))
        await db.execute(delete(GraphTriple).where(GraphTriple.project_id == proj_uuid))
    await db.commit()

    # Delete LanceDB vectors
    await lancedb_client.delete_by_project(str(proj_uuid))
    for tid in team_uuids:
        await lancedb_client.delete_by_team(str(tid))

    return {"ok": True, "message": "Project memory successfully purged from SQLite and LanceDB"}




# ============================================================
# Agent Stop (Cancel streaming generation)
# ============================================================

@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, cancel_all: bool = False, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Cancel the currently executing agent loop.
    If cancel_all=true, also drains the entire queue so no further
    queued tasks will execute.
    """
    await _assert_agent_access(db, agent_id, user["sub"])
    from core.chat.message_router import message_router
    cancelled = message_router.cancel_agent(agent_id, cancel_all=cancel_all)
    return {"ok": True, "cancelled_tasks": cancelled, "queue_cleared": cancel_all}


@router.get("/agents/{agent_id}/queue")
async def get_agent_queue(agent_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Return the current queue status for an agent:
    - queue_depth: number of tasks waiting
    - is_running: whether the agent is actively executing a loop right now
    - pending: list of pending prompt strings
    """
    await _assert_agent_access(db, agent_id, user["sub"])
    from core.chat.message_router import message_router
    return message_router.get_queue_status(agent_id)


# ============================================================
# Tasks
# ============================================================

@router.post("/tasks")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.chat.event_bus import event_bus
    from core.chat.message_router import message_router
    from core.agent.workflow_dag import workflow_dag, DAGCycleError

    if body.team_id:
        await _assert_team_access(db, body.team_id, user["sub"])

    team_uuid = uuid.UUID(body.team_id) if body.team_id else None

    # Fetch existing tasks to validate DAG acyclicity
    existing_tasks = []
    if team_uuid:
        stmt_all = select(Task).where(Task.team_id == team_uuid)
        existing_tasks = (await db.execute(stmt_all)).scalars().all()

    # Normalize dependencies
    clean_deps: List[str] = []
    if body.depends_on:
        for d in body.depends_on:
            norm_d = str(d).strip().lower()
            if norm_d and norm_d not in clean_deps:
                clean_deps.append(norm_d)

    if body.blocked_by_task_id:
        norm_b = str(body.blocked_by_task_id).strip().lower()
        if norm_b and norm_b not in clean_deps:
            clean_deps.append(norm_b)

    task_id_uuid = uuid.uuid4()
    task_id_str = str(task_id_uuid)

    # Validate DAG acyclicity
    try:
        workflow_dag.validate_acyclic(
            tasks=existing_tasks,
            new_or_updated_task_id=task_id_str,
            new_dependencies=clean_deps,
        )
    except DAGCycleError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Initial status: if has prerequisite tasks not yet 'done', mark blocked
    initial_status = "todo"
    primary_blocked_by = None
    if clean_deps and existing_tasks:
        status_map = {str(t.id).lower(): t.status for t in existing_tasks}
        all_done = all(status_map.get(d) == "done" for d in clean_deps if d in status_map)
        if not all_done:
            initial_status = "blocked"
            try:
                primary_blocked_by = uuid.UUID(clean_deps[0])
            except (ValueError, AttributeError):
                pass
    elif body.blocked_by_task_id:
        initial_status = "blocked"
        try:
            primary_blocked_by = uuid.UUID(body.blocked_by_task_id)
        except (ValueError, AttributeError):
            pass

    task = Task(
        id=task_id_uuid,
        team_id=team_uuid,
        title=body.title,
        description=body.description,
        priority=body.priority,
        status=initial_status,
        assigned_agent_id=uuid.UUID(body.assigned_agent_id) if body.assigned_agent_id else None,
        parent_task_id=uuid.UUID(body.parent_task_id) if body.parent_task_id else None,
        blocked_by_task_id=primary_blocked_by,
        depends_on=clean_deps,
        created_by=body.created_by,
    )
    db.add(task)
    await db.commit()

    assignee_name = "unassigned"
    agent = None
    if task.assigned_agent_id:
        agent_stmt = select(Agent).where(Agent.id == task.assigned_agent_id)
        agent_result = await db.execute(agent_stmt)
        agent = agent_result.scalar_one_or_none()
        if agent:
            assignee_name = agent.name

    if task.team_id:
        await event_bus.publish(f"team:{str(task.team_id)}", {
            "type": "task_update",
            "action": "created",
            "task": {
                "id": str(task.id), "title": task.title, "description": task.description,
                "status": task.status, "priority": task.priority,
                "assigned_to": assignee_name,
                "depends_on": clean_deps,
            },
        })
        if body.created_by == "human" or not body.created_by:
            creator = await _get_human_name(db, task.team_id)
        else:
            creator = body.created_by
        if agent:
            # Task was assigned — notify assignee
            if task.status == "blocked":
                assign_text = f"[TASK_ASSIGN] @{agent.name} a new task '{task.title}' was created and assigned to you by {creator}. However, it is currently BLOCKED by prerequisite dependencies ({', '.join(clean_deps[:3])}). You will be notified when it is unblocked. Do not start work yet."
            else:
                assign_text = f"[TASK_ASSIGN] @{agent.name} a new task '{task.title}' was created and assigned to you by {creator}. Please start working on it."
            await message_router.route_message(
                text=assign_text,
                sender_id="system",
                team_id=str(task.team_id),
                sender_name="System",
                attachments=[]
            )
        else:
            # Task is unassigned — ping the Coordinator to triage and assign it
            from sqlalchemy import func
            coord_stmt = select(Agent).where(
                Agent.team_id == task.team_id,
                func.lower(Agent.role).in_(["coordinator", "orchestrator"])
            ).limit(1)
            coord_res = await db.execute(coord_stmt)
            coordinator = coord_res.scalar_one_or_none()
            if coordinator:
                await message_router.route_message(
                    text=f"[TASK_CREATE] @{coordinator.name} a new unassigned task '{task.title}' was created by {creator}. Please review and assign it to the appropriate teammate.",
                    sender_id="system",
                    team_id=str(task.team_id),
                    sender_name="System",
                    attachments=[]
                )
                coord_prompt = (
                    f"A new unassigned task was created on the Kanban board: '{task.title}' (Task ID: {task.id}). "
                    f"Description: {task.description or 'No description provided.'}. Priority: {task.priority}. "
                    f"Please review your team roster and assign this task to the best-suited teammate using update_task(task_id='{task.id}', assignee_name='...'). "
                    f"If no existing teammate fits the required expertise, you may create a teammate or hire a specialist."
                )
                await message_router._trigger_agent(coordinator, coord_prompt, db)
            else:
                await message_router.route_message(
                    text=f"[TASK_CREATE] {creator} created task '{task.title}' (unassigned).",
                    sender_id="system",
                    team_id=str(task.team_id),
                    sender_name="System",
                    attachments=[]
                )

    if agent and task.status != "blocked":
        prompt = f"The human just assigned a new task to you on the Kanban board: '{task.title}'. Description: {task.description or 'No description provided.'}. Please review it and start working."
        await message_router._trigger_agent(agent, prompt, db)

    return {"id": str(task.id), "title": task.title, "status": task.status, "depends_on": task.depends_on or []}

@router.get("/tasks/{team_id}")
async def list_tasks(team_id: str, status: Optional[str] = None, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_team_access(db, team_id, user["sub"])
    stmt = select(Task).where(Task.team_id == uuid.UUID(team_id))
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.created_at.desc())
    result = await db.execute(stmt)
    return [
        {
            "id": str(t.id), "title": t.title, "description": t.description,
            "status": t.status, "priority": t.priority,
            "assigned_agent_id": str(t.assigned_agent_id) if t.assigned_agent_id else None,
            "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
            "blocked_by_task_id": str(t.blocked_by_task_id) if t.blocked_by_task_id else None,
            "depends_on": t.depends_on or [],
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "plan_status": t.plan_status,
            "todo_list": t.todo_list or [],
        }
        for t in result.scalars().all()
    ]

@router.get("/tasks/dag/{team_id}")
async def get_team_task_dag(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Returns the DAG graph structure, nodes, edges, cycle status, and execution waves."""
    await _assert_team_access(db, team_id, user["sub"])
    from core.agent.workflow_dag import workflow_dag
    stmt = select(Task).where(Task.team_id == uuid.UUID(team_id))
    team_tasks = (await db.execute(stmt)).scalars().all()
    return workflow_dag.build_dag_summary(team_tasks)

@router.put("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    task = await _assert_task_access(db, task_id, user["sub"])
    from core.agent.workflow_dag import workflow_dag, DAGCycleError
    from core.chat.message_router import message_router
    from core.memory.models import Agent
    from core.chat.event_bus import event_bus

    old_status = task.status
    team_id_str = str(task.team_id)

    # Validate and update dependencies if requested
    if body.depends_on is not None or body.blocked_by_task_id is not None:
        stmt_all = select(Task).where(Task.team_id == task.team_id)
        team_tasks = (await db.execute(stmt_all)).scalars().all()

        new_deps: List[str] = []
        if body.depends_on is not None:
            for d in body.depends_on:
                norm_d = str(d).strip().lower()
                if norm_d and norm_d not in new_deps:
                    new_deps.append(norm_d)
        else:
            new_deps = list(task.depends_on or [])

        if body.blocked_by_task_id is not None:
            if body.blocked_by_task_id:
                norm_b = str(body.blocked_by_task_id).strip().lower()
                if norm_b and norm_b not in new_deps:
                    new_deps.append(norm_b)
                try:
                    task.blocked_by_task_id = uuid.UUID(body.blocked_by_task_id)
                except (ValueError, AttributeError):
                    pass
            else:
                task.blocked_by_task_id = None

        try:
            workflow_dag.validate_acyclic(
                tasks=team_tasks,
                new_or_updated_task_id=str(task.id),
                new_dependencies=new_deps,
            )
        except DAGCycleError as e:
            raise HTTPException(status_code=400, detail=str(e))

        task.depends_on = new_deps

    if body.status is not None:
        task.status = body.status
    if body.priority is not None:
        task.priority = body.priority
    if body.assigned_agent_id is not None:
        try:
            task.assigned_agent_id = uuid.UUID(body.assigned_agent_id)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail="Invalid assigned_agent_id format")
    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    task.updated_at = datetime.now(timezone.utc)
    await db.commit()

    human_name = await _get_human_name(db, task.team_id)
    sys_text = f"[TASK_UPDATE] '{task.title}' moved to {task.status} by {human_name}"
    if task.assigned_agent_id:
        agent_res = await db.execute(select(Agent).where(Agent.id == task.assigned_agent_id))
        agent = agent_res.scalar_one_or_none()
        if agent:
            # Wake agent if assignment changed or task moved to in_progress
            if body.assigned_agent_id:
                if task.status == "blocked":
                    assign_text = f"[TASK_ASSIGN] @{agent.name} task '{task.title}' (Task ID: {task.id}) has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet. DO NOT create a new task — this task already exists on the board."
                else:
                    assign_text = f"[TASK_ASSIGN] @{agent.name} task '{task.title}' (Task ID: {task.id}) has been assigned to you. Description: {task.description or 'No description provided.'}. Please begin work now. IMPORTANT: DO NOT use create_task — this task already exists on the board with the ID above. Use update_task(task_id='{task.id}', status='in_progress') to start it, then update_task(task_id='{task.id}', status='done') when finished."
                await message_router.route_message(
                    text=assign_text,
                    sender_id="system",
                    team_id=team_id_str,
                    sender_name="System",
                    attachments=[]
                )
                if task.status != "blocked":
                    await message_router._enqueue_agent(agent, assign_text, db)
            elif body.status == "in_progress":
                if task.status == "blocked":
                    update_text = f"[TASK_UPDATE] @{agent.name} your task '{task.title}' has been moved to 'In Progress'. However, it is currently BLOCKED. You may investigate it, but wait for the blocking task to complete before making major changes."
                else:
                    update_text = f"[TASK_UPDATE] @{agent.name} your task '{task.title}' has been moved to 'In Progress'. Description: {task.description or 'No description provided.'}. Please continue work."
                await message_router.route_message(
                    text=update_text,
                    sender_id="system",
                    team_id=team_id_str,
                    sender_name="System",
                    attachments=[]
                )
                if task.status != "blocked":
                    await message_router._enqueue_agent(agent, update_text, db)

    # DAG MULTI-DEPENDENCY UNBLOCK & CASCADE ENGINE
    stmt_all = select(Task).where(Task.team_id == task.team_id)
    all_team_tasks = (await db.execute(stmt_all)).scalars().all()

    if task.status == "done" and old_status != "done":
        unblocked = workflow_dag.propagate_task_completion(all_team_tasks, str(task.id))
        for b_task in unblocked:
            b_task.blocked_by_task_id = None
            b_task.status = "todo"
            b_task.updated_at = datetime.now(timezone.utc)
            await event_bus.publish(f"team:{team_id_str}", {
                "type": "task_update",
                "action": "updated",
                "task": {
                    "id": str(b_task.id),
                    "title": b_task.title,
                    "status": "todo",
                    "priority": b_task.priority,
                    "depends_on": b_task.depends_on or [],
                }
            })
            if b_task.assigned_agent_id:
                agent_res = await db.execute(select(Agent).where(Agent.id == b_task.assigned_agent_id))
                b_agent = agent_res.scalar_one_or_none()
                if b_agent:
                    unblock_msg = f"[TASK_UNBLOCKED] @{b_agent.name} all prerequisite tasks for '{b_task.title}' are now complete. You may begin work."
                    await message_router.route_message(
                        text=unblock_msg,
                        sender_id="system",
                        team_id=team_id_str,
                        sender_name="System",
                        attachments=[]
                    )
                    await message_router._enqueue_agent(b_agent, unblock_msg, db)
        if unblocked:
            await db.commit()

    elif task.status == "blocked" and old_status != "blocked":
        cascade = workflow_dag.propagate_cascade_failure(
            all_team_tasks, str(task.id), f"Upstream prerequisite '{task.title}' is blocked"
        )
        for c_task, _ in cascade:
            if c_task.status != "blocked":
                c_task.status = "blocked"
                c_task.updated_at = datetime.now(timezone.utc)
                await event_bus.publish(f"team:{team_id_str}", {
                    "type": "task_update",
                    "action": "updated",
                    "task": {
                        "id": str(c_task.id),
                        "title": c_task.title,
                        "status": "blocked",
                        "priority": c_task.priority,
                        "depends_on": c_task.depends_on or [],
                    }
                })
        if cascade:
            await db.commit()

    await message_router.route_message(
        text=sys_text,
        sender_id="system",
        team_id=team_id_str,
        sender_name="System",
        attachments=[]
    )

    return {"status": "updated", "id": task_id}


# ============================================================
# Memory Dream Cycle Routes
# ============================================================

@router.post("/memory/dream/run")
async def trigger_dream_cycle(
    team_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """Triggers an on-demand memory consolidation (Dream) cycle immediately."""
    from core.memory.auto_dream import dream_worker
    if team_id:
        await _assert_team_access(db, team_id, user["sub"])
    return await dream_worker.run_once(team_id=team_id)


@router.get("/memory/dream/status")
async def get_dream_status(user: dict = Depends(require_auth)):
    """Returns operational metrics and telemetry for the background Dream worker."""
    from core.memory.auto_dream import dream_worker
    return dream_worker.get_status()


from core.memory.models import TaskComment

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    task = await _assert_task_access(db, task_id, user["sub"])
    from core.memory.models import Agent
    from core.chat.message_router import message_router

    # UNBLOCK ENGINE: If a task is deleted, unblock tasks waiting on it
    unblock_stmt = select(Task).where(Task.blocked_by_task_id == task.id)
    unblock_res = await db.execute(unblock_stmt)
    blocked_tasks = unblock_res.scalars().all()
    for b_task in blocked_tasks:
        b_task.blocked_by_task_id = None
        b_task.updated_at = datetime.now(timezone.utc)
        if b_task.assigned_agent_id:
            agent_res = await db.execute(select(Agent).where(Agent.id == b_task.assigned_agent_id))
            b_agent = agent_res.scalar_one_or_none()
            if b_agent:
                await message_router.route_message(
                    text=f"[TASK_UNBLOCKED] @{b_agent.name} the task you were waiting on ('{task.title}') was DELETED. You are now unblocked and can begin work on your task: '{b_task.title}'.",
                    sender_id="system",
                    team_id=str(b_task.team_id),
                    sender_name="System",
                    attachments=[]
                )

    await db.delete(task)
    await db.commit()
    from core.chat.message_router import message_router
    human_name = await _get_human_name(db, task.team_id)
    await message_router.route_message(
        text=f"[TASK_DELETE] '{task.title}' was deleted by {human_name}",
        sender_id="system",
        team_id=str(task.team_id),
        sender_name="System",
        attachments=[]
    )
    return {"status": "deleted", "id": task_id}

@router.post("/tasks/{task_id}/comments")
async def create_task_comment(task_id: str, body: TaskCommentCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    task = await _assert_task_access(db, task_id, user["sub"])
        
    comment = TaskComment(
        task_id=uuid.UUID(task_id),
        author_id=body.author_id,
        author_name=body.author_name,
        text=body.text
    )
    db.add(comment)
    await db.flush()
    
    from core.chat.message_router import message_router
    sys_text = f"[TASK_COMMENT] {body.author_name} on '{task.title}': {body.text}"
    
    import re
    if task.assigned_agent_id and not re.search(r"@\w+", body.text):
        agent_res = await db.execute(select(Agent).where(Agent.id == task.assigned_agent_id))
        agent = agent_res.scalar_one_or_none()
        if agent and str(agent.id) != body.author_id:
            sys_text += f"\n(Implicitly notifying assignee: @{agent.name})"
    await db.commit()
            
    await message_router.route_message(
        text=sys_text,
        sender_id="system",
        team_id=str(task.team_id),
        sender_name="System",
        attachments=[]
    )
    
    return {
        "id": str(comment.id),
        "author_id": comment.author_id,
        "author_name": comment.author_name,
        "text": comment.text,
        "created_at": comment.created_at.isoformat() if comment.created_at else None
    }

@router.get("/tasks/{task_id}/comments")
async def list_task_comments(task_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_task_access(db, task_id, user["sub"])
    stmt = select(TaskComment).where(TaskComment.task_id == uuid.UUID(task_id)).order_by(TaskComment.created_at.asc())
    result = await db.execute(stmt)
    comments = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "author_id": c.author_id,
            "author_name": c.author_name,
            "text": c.text,
            "created_at": c.created_at.isoformat() if c.created_at else None
        }
        for c in comments
    ]

# ============================================================
# LLM Model Catalog
# ============================================================

@router.get("/models")
async def list_models():
    """
    Returns the model catalog filtered to providers with active API keys.
    Used by AgentPanel to populate provider/model dropdowns.
    """
    from core.llm.model_catalog import get_active_catalog
    from core.llm.config_manager import load_config
    cfg = load_config()
    return get_active_catalog(cfg)


@router.get("/models/catalog")
async def get_model_catalog():
    """Full (unfiltered) catalog — used by Settings → Model Catalog editor."""
    from core.llm.model_catalog import load_model_catalog
    return load_model_catalog()


@router.get("/models/catalog/defaults")
async def get_default_model_catalog():
    """Returns ONLY the factory-shipped defaults (no user overrides)."""
    from core.llm.model_catalog import load_default_model_catalog
    return load_default_model_catalog()


@router.post("/models/catalog")
async def save_model_catalog_endpoint(body: dict, user: dict = Depends(require_auth)):
    """
    Saves the model catalog to ~/.carole/supported_models.json.
    Accepts the full catalog object (same shape as GET response).
    """
    from core.llm.model_catalog import save_model_catalog
    try:
        save_model_catalog(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "saved"}


@router.post("/models/catalog/reset")
async def reset_model_catalog_endpoint(user: dict = Depends(require_auth)):
    """
    Deletes ~/.carole/supported_models.json so factory defaults take effect.
    Returns the factory defaults so the UI can refresh immediately.
    """
    from core.llm.model_catalog import reset_model_catalog, load_default_model_catalog
    reset_model_catalog()
    return load_default_model_catalog()


# ============================================================
# Prompts
# ============================================================

@router.get("/prompts")
async def get_prompts():
    """Returns all prompts (merged defaults + user overrides)."""
    from core.prompts import load_prompts
    return load_prompts()


@router.get("/prompts/defaults")
async def get_default_prompts():
    """Returns ONLY the factory-shipped prompt defaults (no user overrides)."""
    from core.prompts import load_default_prompts
    return load_default_prompts()


@router.post("/prompts")
async def save_prompts_endpoint(body: dict, user: dict = Depends(require_auth)):
    """
    Saves prompts to ~/.carole/prompts.json.
    Accepts a flat dict of { slug: template_string }.
    """
    from core.prompts import save_prompts
    save_prompts(body)
    return {"status": "saved"}


@router.post("/prompts/reset")
async def reset_prompts_endpoint(user: dict = Depends(require_auth)):
    """
    Deletes ~/.carole/prompts.json so factory defaults take effect.
    Returns the factory defaults so the UI can refresh immediately.
    """
    from core.prompts import reset_prompts, load_default_prompts
    reset_prompts()
    return load_default_prompts()


# ============================================================
# Tools (dynamic registry)
# ============================================================

@router.get("/tools")
async def list_tools():
    return ToolRegistry.to_api_list()


# ============================================================
# Role Templates
# ============================================================

@router.get("/role-templates")
async def list_role_templates():
    from core.agent.role_templates import get_all_templates
    return get_all_templates()

@router.get("/role-templates/{role}")
async def get_role_template(role: str):
    from core.agent.role_templates import get_template_by_role
    template = get_template_by_role(role)
    if not template:
        raise HTTPException(status_code=404, detail=f"No template found for role '{role}'.")
    return template



# NOTE: search_messages is defined earlier in this file (line ~757) with proper
# auth checking, LIKE metachar escaping, and ownership verification.
# The duplicate unsafe version that previously appeared here has been removed.


# ============================================================
# Audio Transcription Upload
# ============================================================

@router.post("/audio/transcribe/{team_id}")
async def transcribe_audio_upload(team_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Accepts an audio file upload, transcribes it via OpenAI Whisper,
    and broadcasts the transcription to the team EventBus.
    """
    await _assert_team_access(db, team_id, user["sub"])
    from core.tools.meeting_tool import meeting_tool

    audio_data = await file.read()
    text = await meeting_tool.transcribe_audio(
        audio_data=audio_data,
        agent_id="system",
        agent_name="Meeting Assistant",
        team_id=team_id,
        filename=file.filename or "audio.webm",
    )
    return {"transcription": text}


# ============================================================
# Seed endpoint (dev convenience)
# ============================================================

@router.post("/seed")
async def seed_demo(db: AsyncSession = Depends(get_db)):
    """Creates a demo user, project, team, and 3 agents for quick testing."""
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    if env in ["production", "prod"]:
        raise HTTPException(status_code=403, detail="Seeding demo data is disabled in production environments.")

    from core.auth.auth_service import _hash_password
    # Check if already seeded
    existing = await db.execute(select(User).limit(1))
    if existing.scalar_one_or_none():
        return {"status": "already_seeded"}

    user = User(
        email="admin@carole.ai",
        hashed_password=_hash_password("demo123"),  # properly hashed — login with demo123
        first_name="Admin",
        last_name="User",
        is_verified=True,
    )
    db.add(user)
    await db.flush()

    project = Project(name="Carole.ai Dev", owner_id=user.id)
    db.add(project)
    await db.flush()

    team = Team(name="Core Team", project_id=project.id)
    db.add(team)
    await db.flush()

    agents_data = [
        {
            "name": "Archer",
            "role": "Orchestrator",
            "model": DEFAULT_FAST_MODEL,
            "personality": "casual",
            "tool_permissions": {
                "read_file": "safe", "list_directory": "safe",
                "web_search": "safe", "web_fetch": "safe",
                "spawn_agent": "safe", "send_message": "safe",
                "create_task": "safe", "list_tasks": "safe", "update_task": "safe",
                "write_file": "block", "edit_file": "block", "create_directory": "block",
            },
        },
        {
            "name": "Nova",
            "role": "Coder",
            "model": DEFAULT_FAST_MODEL,
            "personality": "witty",
            "tool_permissions": {
                "read_file": "safe", "write_file": "judge", "edit_file": "judge",
                "list_directory": "safe", "execute_command": "judge",
                "git_status": "safe", "git_diff": "safe", "git_add": "judge",
                "git_commit": "judge", "git_log": "safe",
                "web_search": "safe", "web_fetch": "safe",
            },
        },
        {
            "name": "Sage",
            "role": "Reviewer",
            "model": DEFAULT_FAST_MODEL,
            "personality": "mentor",
            "tool_permissions": {
                "read_file": "safe", "list_directory": "safe",
                "git_status": "safe", "git_diff": "safe", "git_log": "safe",
                "web_search": "safe", "web_fetch": "safe",
                "edit_file": "judge",
            },
        },
    ]

    for data in agents_data:
        prompt = _default_system_prompt(data["name"], data["role"], data["personality"])
        agent = Agent(
            team_id=team.id,
            name=data["name"],
            role=data["role"],
            model=data["model"],
            system_prompt=prompt,
            tool_permissions=data["tool_permissions"],
        )
        db.add(agent)

    await db.flush()
    return {
        "status": "seeded",
        "project_id": str(project.id),
        "team_id": str(team.id),
        "agents": [d["name"] for d in agents_data],
    }


# ============================================================
# Helpers
# ============================================================

def _default_system_prompt(name: str, role: str, personality: str = "professional") -> str:
    """
    Assembles the full agent system prompt from modular prompt slugs.
    Text is loaded from defaults/prompts.json (overridable via ~/.carole/prompts.json).
    """
    from core.prompts import build_agent_system_prompt
    return build_agent_system_prompt(name=name, role=role, personality=personality)


# ============================================================
# Knowledge Upload & Ingestion
# ============================================================

@router.post("/knowledge/upload")
async def upload_knowledge(
    project_id: str,
    team_id: Optional[str] = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """
    Ingests an uploaded file (PDF, TXT, MD) into the learnings table (pgvector).
    """
    await _assert_project_access(db, project_id, user["sub"])
    if team_id:
        await _assert_team_access(db, team_id, user["sub"])
    from core.knowledge.knowledge_ingestor import ingest_file

    data = await file.read()
    res = await ingest_file(db, project_id, team_id, file.filename, data)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.get("/knowledge/symbols/{project_id}")
async def get_project_symbols(
    project_id: str,
    name: Optional[str] = None,
    kind: Optional[str] = None,
    file_path: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """
    Returns AST symbol definitions and metadata for a project.
    Supports filtering by symbol name, symbol kind, and file path.
    """
    await _assert_project_access(db, project_id, user["sub"])
    from core.knowledge.code_graph import code_graph
    try:
        if name:
            defs = await code_graph.get_symbol_definitions(name, project_id)
        else:
            chunks = await code_graph.get_all_chunks(project_id)
            defs = [c.to_dict() for c in chunks]

        if kind:
            defs = [d for d in defs if d.get("kind", "").lower() == kind.lower()]

        if file_path:
            norm_fp = file_path.replace("\\", "/")
            defs = [d for d in defs if norm_fp in d.get("file_path", "").replace("\\", "/")]

        return {
            "status": "success",
            "project_id": project_id,
            "total": len(defs),
            "symbols": defs[:limit]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols: {str(e)}")


@router.get("/knowledge/graph/{project_id}")
async def get_project_code_graph(
    project_id: str,
    file_path: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """
    Returns code dependency graph information:
    - If file_path is specified: returns imports, dependents, and symbol outline.
    - If file_path is omitted: returns graph node/edge counts and top central files by PageRank.
    """
    await _assert_project_access(db, project_id, user["sub"])
    from core.knowledge.code_graph import code_graph
    try:
        graph = await code_graph.get_graph(project_id)
        if file_path:
            norm_fp = file_path.replace("\\", "/").strip("/")
            deps = await code_graph.get_module_dependencies(norm_fp, project_id)
            outline = await code_graph.get_file_outline(norm_fp, project_id)
            return {
                "status": "success",
                "project_id": project_id,
                "file_path": norm_fp,
                "dependencies": deps.get("dependencies", []),
                "dependents": deps.get("dependents", []),
                "symbols": outline
            }
        else:
            import networkx as nx
            pagerank = {}
            if len(graph) > 1 and graph.number_of_edges() > 0:
                try:
                    pagerank = nx.pagerank(graph, alpha=0.85, max_iter=100)
                except Exception:
                    pagerank = {n: 1.0 / len(graph) for n in graph.nodes()}
            top_nodes = sorted(graph.nodes(), key=lambda n: pagerank.get(n, 0.0), reverse=True)[:25]
            return {
                "status": "success",
                "project_id": project_id,
                "node_count": graph.number_of_nodes(),
                "edge_count": graph.number_of_edges(),
                "top_central_files": [
                    {"file": n, "pagerank": round(pagerank.get(n, 0.0), 5)}
                    for n in top_nodes
                ]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch code graph: {str(e)}")


@router.get("/knowledge/hierarchy/{project_id}")
async def get_project_class_hierarchy(
    project_id: str,
    class_name: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    """
    Returns class inheritance hierarchy (superclasses, subclasses, and ancestry) for a class.
    """
    await _assert_project_access(db, project_id, user["sub"])
    from core.knowledge.code_graph import code_graph
    try:
        hierarchy = await code_graph.get_class_hierarchy(class_name, project_id)
        return {
            "status": "success",
            "project_id": project_id,
            "hierarchy": hierarchy
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch hierarchy: {str(e)}")



# ============================================================
# Estimated Token Usage & Cost Routing
# ============================================================

@router.get("/usage/{project_id}")
async def get_project_usage(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Returns estimated token usage and cost for all agents in the project.
    """
    await _assert_project_access(db, project_id, user["sub"])
    from core.memory.models import TokenUsage
    import uuid

    stmt = select(TokenUsage).where(TokenUsage.project_id == uuid.UUID(project_id))
    result = await db.execute(stmt)
    usages = result.scalars().all()

    total_prompt = 0
    total_completion = 0
    total_cost = 0.0

    by_agent = {}

    for u in usages:
        prompt = int(u.prompt_tokens or 0)
        completion = int(u.completion_tokens or 0)
        cost = float(u.estimated_cost_usd or 0.0)

        total_prompt += prompt
        total_completion += completion
        total_cost += cost

        name = u.agent_name or "Unknown Agent"
        if name not in by_agent:
            by_agent[name] = {"prompt": 0, "completion": 0, "cost": 0.0, "calls": 0}
        by_agent[name]["prompt"] += prompt
        by_agent[name]["completion"] += completion
        by_agent[name]["cost"] += cost
        by_agent[name]["calls"] += 1

    return {
        "project_id": project_id,
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_cost_usd": f"{total_cost:.4f}",
        "by_agent": {
            name: {
                "prompt_tokens": data["prompt"],
                "completion_tokens": data["completion"],
                "estimated_cost_usd": f"{data['cost']:.4f}",
                "calls": data["calls"]
            }
            for name, data in by_agent.items()
        }
    }


# ============================================================
# MCP Servers
# ============================================================

@router.get("/mcp/status")
async def get_mcp_status():
    from core.tools.mcp_client import mcp_manager
    # Convert tuple keys to strings for JSON serialization
    safe_statuses = {}
    for k, v in mcp_manager.statuses.items():
        key_str = f"{k[0]}::{k[1]}::{k[2]}"
        entry = dict(v)
        # Include attempt progress if present (set during retries)
        if "attempt" in entry or "max_attempts" in entry:
            pass  # already included via dict(v)
        safe_statuses[key_str] = entry
    return safe_statuses

@router.get("/mcp/templates")
async def get_mcp_templates():
    """Return the dynamic catalog of pre-configured MCP integration templates."""
    import pathlib, json
    
    # We can load from a dynamic JSON/YAML configuration if present or return standard dynamic list
    templates = [
        {
            "id": "github",
            "name": "GitHub",
            "category": "Developer",
            "description": "Inspect repositories, file issues, review PRs, search code, and manage workflows.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-github",
            "docsUrl": "https://github.com/settings/tokens",
            "badge": "Official",
            "logo": "github",
            "fields": [
                {
                    "key": "GITHUB_PERSONAL_ACCESS_TOKEN",
                    "label": "Personal Access Token",
                    "placeholder": "ghp_xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Needs 'repo', 'workflow', and 'read:org' scopes."
                }
            ]
        },
        {
            "id": "gitlab",
            "name": "GitLab",
            "category": "Developer",
            "description": "Interact with GitLab projects, merge requests, issues, pipelines, and wiki.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-gitlab",
            "docsUrl": "https://gitlab.com/-/user_settings/personal_access_tokens",
            "badge": "Popular",
            "logo": "gitlab",
            "fields": [
                {
                    "key": "GITLAB_PERSONAL_ACCESS_TOKEN",
                    "label": "Personal Access Token",
                    "placeholder": "glpat-xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Create a token with 'api' and 'read_repository' scopes."
                },
                {
                    "key": "GITLAB_API_URL",
                    "label": "GitLab Instance URL (Optional)",
                    "placeholder": "https://gitlab.com/api/v4",
                    "required": False,
                    "defaultValue": "https://gitlab.com/api/v4"
                }
            ]
        },
        {
            "id": "sentry",
            "name": "Sentry",
            "category": "Developer",
            "description": "Search production error issues, view stack traces, and analyze crash telemetry.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-sentry",
            "docsUrl": "https://sentry.io/settings/account/api/auth-tokens/",
            "logo": "sentry",
            "fields": [
                {
                    "key": "SENTRY_AUTH_TOKEN",
                    "label": "Auth Token",
                    "placeholder": "sntrys_xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "User auth token from Sentry settings."
                }
            ]
        },
        {
            "id": "puppeteer",
            "name": "Puppeteer Web Automator",
            "category": "Developer",
            "description": "Direct Headless Chromium execution for automated scraping and testing.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-puppeteer",
            "docsUrl": "https://pptr.dev",
            "logo": "puppeteer",
            "fields": [
                {
                    "key": "DOCKER_CONTAINER",
                    "label": "Headless Sandbox Options (Optional)",
                    "placeholder": "allow-all",
                    "required": False
                }
            ]
        },
        {
            "id": "docker",
            "name": "Docker",
            "category": "Developer",
            "description": "Manage local & remote Docker containers, images, volumes, and compose swarms.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-docker",
            "docsUrl": "https://docs.docker.com",
            "badge": "Popular",
            "logo": "docker",
            "fields": [
                {
                    "key": "DOCKER_HOST",
                    "label": "Docker Host (Optional)",
                    "placeholder": "unix:///var/run/docker.sock",
                    "required": False
                }
            ]
        },
        {
            "id": "postgres",
            "name": "PostgreSQL",
            "category": "Database",
            "description": "Run schema introspection, execute read queries, and analyze table structures.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-postgres",
            "docsUrl": "https://www.postgresql.org/docs/",
            "badge": "Official",
            "logo": "postgres",
            "fields": [
                {
                    "key": "POSTGRES_URL",
                    "label": "Database Connection URI",
                    "placeholder": "postgresql://user:password@localhost:5432/mydb",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Connection string with read/write access."
                }
            ]
        },
        {
            "id": "redis",
            "name": "Redis",
            "category": "Database",
            "description": "Query Redis keys, streams, cached objects, and pub/sub message queues.",
            "command": "uvx",
            "args": "mcp-server-redis",
            "docsUrl": "https://redis.io/docs/",
            "logo": "redis",
            "fields": [
                {
                    "key": "REDIS_URL",
                    "label": "Redis Connection URL",
                    "placeholder": "redis://localhost:6379",
                    "required": True,
                    "defaultValue": "redis://localhost:6379"
                }
            ]
        },
        {
            "id": "supabase",
            "name": "Supabase",
            "category": "Database",
            "description": "Manage Supabase tables, Postgres functions, Auth users, and Storage buckets.",
            "command": "npx",
            "args": "-y,@supabase/mcp-server",
            "docsUrl": "https://supabase.com/dashboard/project/_/settings/api",
            "badge": "Popular",
            "logo": "supabase",
            "fields": [
                {
                    "key": "SUPABASE_URL",
                    "label": "Project URL",
                    "placeholder": "https://xyzcompany.supabase.co",
                    "required": True
                },
                {
                    "key": "SUPABASE_SERVICE_ROLE_KEY",
                    "label": "Service Role Key (Secret)",
                    "placeholder": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "slack",
            "name": "Slack",
            "category": "Communication",
            "description": "Post messages, query channels, retrieve message threads, and reply to team members.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-slack",
            "docsUrl": "https://api.slack.com/apps",
            "badge": "Official",
            "logo": "slack",
            "fields": [
                {
                    "key": "SLACK_BOT_TOKEN",
                    "label": "Bot User OAuth Token",
                    "placeholder": "xoxb-xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Starts with 'xoxb-'. Needs channels:read, chat:write scopes."
                },
                {
                    "key": "SLACK_TEAM_ID",
                    "label": "Slack Team / Workspace ID",
                    "placeholder": "T0123456789",
                    "required": True
                }
            ]
        },
        {
            "id": "discord",
            "name": "Discord",
            "category": "Communication",
            "description": "Send channel notifications, inspect Discord servers, and interact with guilds.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-discord",
            "docsUrl": "https://discord.com/developers/applications",
            "logo": "discord",
            "fields": [
                {
                    "key": "DISCORD_BOT_TOKEN",
                    "label": "Discord Bot Token",
                    "placeholder": "MTE0xxxxxxxxxxxxxxxxxxxx.xxxxxx.xxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "linear",
            "name": "Linear",
            "category": "Productivity",
            "description": "Create and update issues, query sprint cycles, and track bug tickets.",
            "command": "npx",
            "args": "-y,@linear/mcp-server",
            "docsUrl": "https://linear.app/settings/api",
            "badge": "Popular",
            "logo": "linear",
            "fields": [
                {
                    "key": "LINEAR_API_KEY",
                    "label": "Linear API Key",
                    "placeholder": "lin_api_xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Generate a personal API key from Linear Settings → API."
                }
            ]
        },
        {
            "id": "notion",
            "name": "Notion",
            "category": "Productivity",
            "description": "Read & write Notion pages, query databases, and append structured documentation.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-notion",
            "docsUrl": "https://www.notion.so/my-integrations",
            "badge": "Official",
            "logo": "notion",
            "fields": [
                {
                    "key": "NOTION_API_KEY",
                    "label": "Internal Integration Secret",
                    "placeholder": "secret_xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Create an integration and connect it to your workspace pages."
                }
            ]
        },
        {
            "id": "jira",
            "name": "Jira & Confluence",
            "category": "Productivity",
            "description": "Manage Atlassian Jira epics/tasks, sprints, and Confluence wiki spaces.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-atlassian",
            "docsUrl": "https://id.atlassian.com/manage-profile/security/api-tokens",
            "logo": "jira",
            "fields": [
                {
                    "key": "CONFLUENCE_DOMAIN",
                    "label": "Atlassian Subdomain",
                    "placeholder": "yourcompany.atlassian.net",
                    "required": True
                },
                {
                    "key": "ATLASSIAN_EMAIL",
                    "label": "Account Email",
                    "placeholder": "developer@company.com",
                    "required": True
                },
                {
                    "key": "ATLASSIAN_API_TOKEN",
                    "label": "API Token",
                    "placeholder": "ATATT3xFfGF0xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "google-drive",
            "name": "Google Drive & Docs",
            "category": "Productivity",
            "description": "Search Google Drive files, extract text from Docs/Sheets, and export assets.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-google-drive",
            "docsUrl": "https://console.cloud.google.com/apis/credentials",
            "logo": "google-drive",
            "fields": [
                {
                    "key": "GOOGLE_DRIVE_CREDENTIALS",
                    "label": "Credentials JSON",
                    "placeholder": "{\"type\": \"service_account\", ...}",
                    "required": True,
                    "type": "textarea",
                    "isSecret": True
                }
            ]
        },
        {
            "id": "airtable",
            "name": "Airtable",
            "category": "Productivity",
            "description": "Read & write records in Airtable bases, manage schema tables, and query views.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-airtable",
            "docsUrl": "https://airtable.com/create/tokens",
            "badge": "Popular",
            "logo": "airtable",
            "fields": [
                {
                    "key": "AIRTABLE_API_KEY",
                    "label": "Personal Access Token",
                    "placeholder": "patxxxxxxxxxxxxxxxxxxxx.xxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Create a token with 'data.records:read' and 'data.records:write' scopes."
                }
            ]
        },
        {
            "id": "figma",
            "name": "Figma",
            "category": "Productivity",
            "description": "Inspect design components, extract CSS variables/tokens, and read canvas layers.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-figma",
            "docsUrl": "https://www.figma.com/developers/api",
            "logo": "figma",
            "fields": [
                {
                    "key": "FIGMA_PERSONAL_ACCESS_TOKEN",
                    "label": "Personal Access Token",
                    "placeholder": "figd_xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "asana",
            "name": "Asana",
            "category": "Productivity",
            "description": "Create tasks, query project sections, assign team owners, and update milestone status.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-asana",
            "docsUrl": "https://app.asana.com/0/my-apps",
            "logo": "asana",
            "fields": [
                {
                    "key": "ASANA_ACCESS_TOKEN",
                    "label": "Personal Access Token",
                    "placeholder": "1/120xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "stripe",
            "name": "Stripe",
            "category": "Finance & CRM",
            "description": "Query charges, invoices, subscription tiers, customer records, and payment events.",
            "command": "npx",
            "args": "-y,@stripe/mcp-server",
            "docsUrl": "https://dashboard.stripe.com/apikeys",
            "badge": "Official",
            "logo": "stripe",
            "fields": [
                {
                    "key": "STRIPE_SECRET_KEY",
                    "label": "Secret Key (Test or Live)",
                    "placeholder": "sk_test_51xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Restricted or standard secret key from Stripe dashboard."
                }
            ]
        },
        {
            "id": "hubspot",
            "name": "HubSpot",
            "category": "Finance & CRM",
            "description": "Search CRM contacts, deals, company pipelines, and customer notes.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-hubspot",
            "docsUrl": "https://app.hubspot.com/private-apps",
            "badge": "Popular",
            "logo": "hubspot",
            "fields": [
                {
                    "key": "HUBSPOT_ACCESS_TOKEN",
                    "label": "Private App Access Token",
                    "placeholder": "pat-na1-xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "aws-s3",
            "name": "AWS Cloud & S3",
            "category": "Cloud & Search",
            "description": "Read, write, and list objects across Amazon S3 buckets and AWS cloud assets.",
            "command": "uvx",
            "args": "mcp-server-aws-s3",
            "docsUrl": "https://aws.amazon.com/console/",
            "logo": "aws",
            "fields": [
                {
                    "key": "AWS_ACCESS_KEY_ID",
                    "label": "Access Key ID",
                    "placeholder": "AKIAIOSFODNN7EXAMPLE",
                    "required": True
                },
                {
                    "key": "AWS_SECRET_ACCESS_KEY",
                    "label": "Secret Access Key",
                    "placeholder": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                    "required": True,
                    "isSecret": True
                },
                {
                    "key": "AWS_REGION",
                    "label": "AWS Region",
                    "placeholder": "us-east-1",
                    "defaultValue": "us-east-1",
                    "required": True
                }
            ]
        },
        {
            "id": "brave-search",
            "name": "Brave Web Search",
            "category": "Cloud & Search",
            "description": "Independent web search index with fast text snippets, news, and links.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-brave-search",
            "docsUrl": "https://brave.com/search/api/",
            "badge": "Official",
            "logo": "brave-search",
            "fields": [
                {
                    "key": "BRAVE_API_KEY",
                    "label": "Brave Search API Key",
                    "placeholder": "BSAxxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True
                }
            ]
        },
        {
            "id": "perplexity",
            "name": "Perplexity AI Search",
            "category": "Cloud & Search",
            "description": "Real-time AI grounded web search, citation retrieval, and factual research engine.",
            "command": "npx",
            "args": "-y,perplexity-mcp",
            "docsUrl": "https://www.perplexity.ai/settings/api",
            "badge": "Popular",
            "logo": "perplexity",
            "fields": [
                {
                    "key": "PERPLEXITY_API_KEY",
                    "label": "Perplexity API Key",
                    "placeholder": "pplx-xxxxxxxxxxxxxxxxxxxx",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Obtain an API key from Perplexity AI account settings."
                }
            ]
        },
        {
            "id": "mongodb",
            "name": "MongoDB",
            "category": "Database",
            "description": "Query documents, aggregate collections, inspect BSON schemas, and run analytics.",
            "command": "npx",
            "args": "-y,@modelcontextprotocol/server-mongodb",
            "docsUrl": "https://www.mongodb.com/docs/atlas/",
            "badge": "Official",
            "logo": "mongodb",
            "fields": [
                {
                    "key": "MONGODB_URI",
                    "label": "MongoDB Connection URI",
                    "placeholder": "mongodb+srv://user:pass@cluster.mongodb.net/dbname",
                    "required": True,
                    "isSecret": True,
                    "helpText": "Atlas or self-hosted MongoDB connection string."
                }
            ]
        }
    ]
    return templates


@router.post("/mcp/resolve-logo")
async def resolve_mcp_logo_endpoint(body: dict):
    """
    Dynamically resolves or automatically downloads official brand SVG logo for any MCP server.
    """
    import re, pathlib, urllib.request

    server_name = body.get("server_name", "").strip().lower()
    command = body.get("command", "").strip().lower()
    args = body.get("args", "")
    if isinstance(args, list):
        args = " ".join(args).lower()
    else:
        args = str(args).lower()

    # Determine slug from server_name or package name
    combined = f"{server_name} {args}"
    slug = None
    common_brands = [
        "github", "gitlab", "slack", "discord", "linear", "notion", "jira", "confluence",
        "postgres", "postgresql", "redis", "supabase", "google-drive", "google", "sentry",
        "stripe", "aws", "airtable", "brave-search", "brave", "figma", "hubspot", "asana",
        "puppeteer", "docker", "datadog", "posthog", "mongodb", "mysql", "clickup", "trello",
        "zendesk", "intercom", "elasticsearch", "snowflake", "graphql", "kubernetes"
    ]
    
    for brand in common_brands:
        if brand in combined:
            slug = "postgres" if brand == "postgresql" else ("brave-search" if brand == "brave" else brand)
            break
            
    if not slug:
        # Clean server_name to alphanumeric slug
        slug = re.sub(r"[^a-z0-9\-]", "", server_name.replace(" ", "-").replace("_", "-"))
        slug = slug.removeprefix("mcp-server-").removeprefix("server-").removeprefix("@modelcontextprotocol/")

    if not slug:
        slug = "default"

    # Check if logo exists in frontend/public/logos
    frontend_logo_dir = pathlib.Path(__file__).resolve().parents[3] / "frontend" / "public" / "logos"
    frontend_logo_dir.mkdir(parents=True, exist_ok=True)
    target_file = frontend_logo_dir / f"{slug}.svg"

    if target_file.exists():
        return {"slug": slug, "logo_url": f"/logos/{slug}.svg", "cached": True}

    # Attempt to download from Simple Icons CDN API
    cdn_slug = "postgresql" if slug == "postgres" else ("amazons3" if slug == "aws" else ("googledrive" if slug == "google-drive" else slug))
    cdn_url = f"https://cdn.jsdelivr.net/npm/simple-icons@v14/icons/{cdn_slug}.svg"
    try:
        req = urllib.request.Request(cdn_url, headers={"User-Agent": "CaroleAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            svg_data = resp.read().decode("utf-8")
            target_file.write_text(svg_data, encoding="utf-8")
            return {"slug": slug, "logo_url": f"/logos/{slug}.svg", "cached": False, "downloaded": True}
    except Exception:
        # Generate custom SVG monogram badge as fallback
        initial = (slug[:2] if len(slug) >= 2 else slug[:1]).upper()
        fallback_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none">
  <rect width="24" height="24" rx="5" fill="#6366F1"/>
  <text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" fill="#FFFFFF" font-size="10" font-weight="bold" font-family="sans-serif">{initial}</text>
</svg>'''
        target_file.write_text(fallback_svg, encoding="utf-8")
        return {"slug": slug, "logo_url": f"/logos/{slug}.svg", "cached": False, "generated": True}


@router.post("/mcp")
async def add_mcp_server(body: McpServerCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_team_access(db, body.team_id, user["sub"])
    if body.agent_id:
        await _assert_agent_access(db, body.agent_id, user["sub"])
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager
    import asyncio
    
    # Gracefully parse args whether string or list
    if isinstance(body.args, str):
        import shlex
        try:
            args_list = shlex.split(body.args) if body.args.strip() else []
        except Exception:
            args_list = body.args.split()
    elif isinstance(body.args, list):
        args_list = body.args
    else:
        args_list = []

    # Automatically resolve/cache logo for this server
    try:
        asyncio.create_task(
            resolve_mcp_logo_endpoint({"server_name": body.server_name, "command": body.command, "args": args_list})
        )
    except Exception:
        pass

    server = McpServer(
        team_id=uuid.UUID(body.team_id),
        agent_id=uuid.UUID(body.agent_id) if body.agent_id else None,
        server_name=body.server_name,
        command=body.command,
        args=args_list,
        env_vars=body.env_vars
    )
    db.add(server)
    await db.commit()

    # Launch in background
    asyncio.create_task(
        mcp_manager.connect_stdio_server(
            server_name=body.server_name,
            command=body.command,
            args=args_list,
            team_id=body.team_id,
            agent_id=body.agent_id,
            env_vars=body.env_vars
        )
    )

    from core.chat.message_router import message_router
    t_uuid = uuid.UUID(body.team_id) if body.team_id else None
    human_name = await _get_human_name(db, t_uuid)
    await message_router.route_message(
        text=f"[MCP_ADD] New MCP Server '{body.server_name}' was connected by {human_name}",
        sender_id="system",
        team_id=body.team_id,
        sender_name="System",
        attachments=[]
    )

    return {"id": str(server.id), "status": "connecting"}

@router.get("/mcp/global")
async def list_global_mcps():
    import json
    from core.config import GLOBAL_MCPS, DISABLED_GLOBAL_MCPS_FILE
    from core.tools.mcp_client import mcp_manager
    
    disabled_mcps = []
    if DISABLED_GLOBAL_MCPS_FILE.exists():
        try:
            with open(DISABLED_GLOBAL_MCPS_FILE, "r") as f:
                disabled_mcps = json.load(f)
        except Exception:
            pass

    results = []
    for mcp in GLOBAL_MCPS:
        is_disabled = mcp["server_name"] in disabled_mcps
        key = ("None", "global", mcp["server_name"])
        is_connected = key in mcp_manager.sessions
        
        results.append({
            "server_name": mcp["server_name"],
            "command": mcp["command"],
            "args": mcp["args"],
            "description": mcp.get("description", ""),
            "is_global": True,
            "is_disabled": is_disabled,
            "is_connected": is_connected
        })
    return results

@router.post("/mcp/reload")
async def reload_global_mcps(user: dict = Depends(require_auth)):
    """Hot-reload all enabled global MCP servers without a full server restart.

    - Unregisters tools and clears status for any currently errored/disconnected global MCPs.
    - Re-launches them with the 300 s timeout and retry logic.
    - Already-connected servers are left untouched (idempotent).
    """
    import asyncio as _asyncio
    from core.config import GLOBAL_MCPS, DISABLED_GLOBAL_MCPS_FILE
    from core.tools.mcp_client import mcp_manager

    disabled_mcps: list = []
    if DISABLED_GLOBAL_MCPS_FILE.exists():
        try:
            with open(DISABLED_GLOBAL_MCPS_FILE, "r") as f:
                disabled_mcps = json.load(f)
        except Exception:
            pass

    async def _retry(mcp_cfg: dict, max_attempts: int = 3, backoff: float = 5.0):
        name = mcp_cfg["server_name"]
        for attempt in range(1, max_attempts + 1):
            try:
                await mcp_manager.connect_stdio_server(
                    server_name=name,
                    command=mcp_cfg["command"],
                    args=mcp_cfg["args"],
                    team_id=None,
                    agent_id=None,
                    init_timeout=300.0,
                )
                return
            except Exception as exc:
                if attempt < max_attempts:
                    await _asyncio.sleep(backoff * attempt)
                else:
                    logger.error("[MCP reload] '%s' gave up after %d attempts: %s", name, max_attempts, exc)

    reloading = []
    for mcp in GLOBAL_MCPS:
        name = mcp["server_name"]
        if name in disabled_mcps:
            continue

        key = ("None", "global", name)
        current_status = mcp_manager.statuses.get(key, {})

        # Skip servers that are already successfully connected
        if current_status.get("status") == "connected":
            continue

        # Clear stale error/loading state so the UI shows "loading" immediately
        mcp_manager.statuses.pop(key, None)
        old_stack = mcp_manager.exit_stacks.pop(key, None)
        if old_stack:
            _asyncio.create_task(mcp_manager._close_stack(old_stack, name))

        # Unregister any orphaned tools from a previous failed attempt
        prefix = f"{name}_"
        from core.tools.tool_registry import ToolRegistry
        for tool_name in list(ToolRegistry.list_names()):
            if tool_name.startswith(prefix):
                ToolRegistry.unregister(tool_name)

        _asyncio.create_task(
            _retry(mcp),
            name=f"{name}_mcp_reload",
        )
        reloading.append(name)
        logger.info("[MCP reload] Re-launching '%s'", name)

    return {"ok": True, "reloading": reloading}


@router.post("/mcp/global/{server_name}/toggle")
async def toggle_global_mcp(server_name: str, user: dict = Depends(require_auth)):
    import asyncio as _asyncio
    from core.config import GLOBAL_MCPS, DISABLED_GLOBAL_MCPS_FILE
    from core.tools.mcp_client import mcp_manager

    mcp_config = next((m for m in GLOBAL_MCPS if m["server_name"] == server_name), None)
    if not mcp_config:
        raise HTTPException(404, "Global MCP not found")

    disabled_mcps: list = []
    if DISABLED_GLOBAL_MCPS_FILE.exists():
        try:
            with open(DISABLED_GLOBAL_MCPS_FILE, "r") as f:
                disabled_mcps = json.load(f)
        except Exception:
            pass

    is_disabling = server_name not in disabled_mcps

    if is_disabling:
        disabled_mcps.append(server_name)
        key = ("None", "global", server_name)
        mcp_manager.statuses.pop(key, None)
        old_stack = mcp_manager.exit_stacks.pop(key, None)
        if old_stack:
            _asyncio.create_task(mcp_manager._close_stack(old_stack, server_name))
        mcp_manager.sessions.pop(key, None)
        # Unregister tools
        prefix = f"{server_name}_"
        from core.tools.tool_registry import ToolRegistry
        for tool_name in list(ToolRegistry.list_names()):
            if tool_name.startswith(prefix):
                ToolRegistry.unregister(tool_name)
    else:
        disabled_mcps.remove(server_name)

        async def _retry_enable(mcp_cfg: dict, max_attempts: int = 3, backoff: float = 5.0):
            name = mcp_cfg["server_name"]
            for attempt in range(1, max_attempts + 1):
                try:
                    await mcp_manager.connect_stdio_server(
                        server_name=name,
                        command=mcp_cfg["command"],
                        args=mcp_cfg["args"],
                        team_id=None,
                        agent_id=None,
                        init_timeout=300.0,
                    )
                    return
                except Exception as exc:
                    if attempt < max_attempts:
                        await _asyncio.sleep(backoff * attempt)
                    else:
                        logger.error("[MCP toggle] '%s' gave up after %d attempts: %s", name, max_attempts, exc)

        _asyncio.create_task(
            _retry_enable(mcp_config),
            name=f"{server_name}_mcp_server",
        )

    with open(DISABLED_GLOBAL_MCPS_FILE, "w") as f:
        json.dump(disabled_mcps, f)

    return {"ok": True, "server_name": server_name, "is_disabled": is_disabling}

@router.get("/mcp/{team_id}")
async def list_mcp_servers(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    await _assert_team_access(db, team_id, user["sub"])
    from core.memory.models import McpServer
    stmt = select(McpServer).where(McpServer.team_id == uuid.UUID(team_id))
    result = await db.execute(stmt)
    servers = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "server_name": s.server_name,
            "command": s.command,
            "args": s.args,
            "agent_id": str(s.agent_id) if s.agent_id else None
        }
        for s in servers
    ]

@router.delete("/mcp/{server_id}")
async def delete_mcp_server(server_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager

    # Try UUID lookup first
    server = None
    try:
        stmt = select(McpServer).where(McpServer.id == uuid.UUID(server_id))
        result = await db.execute(stmt)
        server = result.scalars().first()
    except ValueError:
        pass

    # If not found by UUID, try lookup by server_name
    if not server:
        stmt = select(McpServer).where(McpServer.server_name == server_id)
        result = await db.execute(stmt)
        server = result.scalars().first()

    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")

    if server.team_id:
        await _assert_team_access(db, str(server.team_id), user["sub"])

    server_name = server.server_name
    team_id_str = str(server.team_id) if server.team_id else None
    agent_id_str = str(server.agent_id) if server.agent_id else None

    await db.delete(server)
    await db.commit()

    # Fully disconnect from mcp_manager (sessions, statuses, ToolRegistry)
    await mcp_manager.disconnect_server(
        team_id=team_id_str,
        agent_id=agent_id_str,
        server_name=server_name
    )

    if server and server.team_id:
        from core.chat.message_router import message_router
        human_name = await _get_human_name(db, server.team_id)
        await message_router.route_message(
            text=f"[MCP_DELETE] MCP Server '{server_name}' was disconnected by {human_name}",
            sender_id="system",
            team_id=str(server.team_id),
            sender_name="System",
            attachments=[]
        )

    return {"ok": True}


@router.post("/mcp/disconnect/{server_name}")
async def disconnect_mcp_by_name(server_name: str, body: dict = None, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager

    team_id = (body or {}).get("team_id")
    stmt = select(McpServer).where(McpServer.server_name == server_name)
    if team_id:
        try:
            stmt = stmt.where(McpServer.team_id == uuid.UUID(team_id))
        except ValueError:
            pass

    res = await db.execute(stmt)
    servers = res.scalars().all()
    for s in servers:
        await db.delete(s)
    await db.commit()

    await mcp_manager.disconnect_server(team_id=team_id, server_name=server_name)
    return {"ok": True}


# ============================================================
# App Settings (API Keys & Provider Config)
# ============================================================

class AppSettings(BaseModel):
    api_keys: dict = {}
    providers: dict = {}
    default_models: dict = {}
    agent_settings: dict = {}
    browser_automation: dict = {}
    access_control: dict = {}  # Global Access Control & Safety defaults


@router.get("/settings")
async def get_settings(user: dict = Depends(require_auth)):
    """
    Returns the current application settings from ~/.carole/config.json.
    API key values are masked (last 4 chars visible) for security. Requires authentication.
    """
    from core.llm.config_manager import load_config
    cfg = load_config()

    # Mask keys so they never leave the backend in plaintext
    masked_keys = {}
    for k, v in cfg.get("api_keys", {}).items():
        if v and len(v) > 8:
            masked_keys[k] = f"{'*' * (len(v) - 4)}{v[-4:]}"
        elif v:
            masked_keys[k] = "****"
        else:
            masked_keys[k] = ""

    # Mask browser_automation api_keys
    ba_cfg = dict(cfg.get("browser_automation", {}))
    masked_ba_keys = {}
    for k, v in ba_cfg.get("api_keys", {}).items():
        if v and len(v) > 8:
            masked_ba_keys[k] = f"{'*' * (len(v) - 4)}{v[-4:]}"
        elif v:
            masked_ba_keys[k] = "****"
        else:
            masked_ba_keys[k] = ""
    ba_cfg["api_keys"] = masked_ba_keys

    return {
        "api_keys": masked_keys,
        "providers": cfg.get("providers", {}),
        "default_models": cfg.get("default_models", {}),
        "agent_settings": cfg.get("agent_settings", {}),
        "browser_automation": ba_cfg,
        "access_control": cfg.get("access_control", {}),
    }


@router.post("/settings")
async def save_settings(body: AppSettings, user: dict = Depends(require_auth)):
    """
    Saves API keys and provider config to ~/.carole/config.json and hot-reloads
    the LLM router so changes take effect immediately without a server restart.
    Ignores keys where the value is all asterisks (masked / unchanged).
    """
    from core.llm.config_manager import load_config, save_config
    from core.llm.multi_model_router import llm_router

    # Load current config so we can do a partial update (masked keys = unchanged)
    current = load_config()

    new_keys = dict(current.get("api_keys", {}))
    for k, v in body.api_keys.items():
        if v == "":
            new_keys[k] = ""
        elif v and not all(c == "*" for c in v.replace("-", "").replace("_", "")):
            new_keys[k] = v.strip()

    new_providers = {**current.get("providers", {}), **body.providers}
    new_default_models = {**current.get("default_models", {}), **body.default_models}
    new_agent_settings = {**current.get("agent_settings", {}), **body.agent_settings}

    current_ba = current.get("browser_automation", {})
    new_ba = {**current_ba, **body.browser_automation}
    new_ba_keys = dict(current_ba.get("api_keys", {}))
    for k, v in body.browser_automation.get("api_keys", {}).items():
        if v == "":
            new_ba_keys[k] = ""
        elif v and not all(c == "*" for c in v.replace("-", "").replace("_", "")):
            new_ba_keys[k] = v.strip()
    new_ba["api_keys"] = new_ba_keys

    updated_cfg = {
        "api_keys": new_keys,
        "providers": new_providers,
        "default_models": new_default_models,
        "agent_settings": new_agent_settings,
        "browser_automation": new_ba,
        "access_control": {**current.get("access_control", {}), **body.access_control},
    }
    save_config(updated_cfg)

    # Hot-reload the LLM router so new keys are used immediately
    llm_router.reload_config()

    # Hot-reload web_tools so Tavily key is picked up
    from core.tools.web_tools import web_tools
    web_tools.reload_config()

    # Hot-reload voice_service so TTS/STT keys are picked up
    from core.tools.voice_stt_tts import voice_service
    voice_service.reload_config()
    
    # Close active browsers so they restart with the new provider
    from core.tools.browser_pool import close_all
    await close_all()

    return {"status": "saved", "reloaded": True}

# ============================================================
# Entity Memory Endpoints (Wave 5.1)
# ============================================================

from core.memory.models import EntityMemory

class EntityMemoryCreate(BaseModel):
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    key: str
    value: str

@router.get("/memories/entities")
async def list_entity_memories(
    team_id: Optional[str] = None,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    if not team_id and not project_id:
        return []
    
    stmt = select(EntityMemory)
    has_filter = False
    if team_id and team_id not in ("undefined", "null", ""):
        try:
            stmt = stmt.where(EntityMemory.team_id == uuid.UUID(team_id))
            has_filter = True
        except (ValueError, TypeError):
            pass
    if project_id and project_id not in ("undefined", "null", ""):
        try:
            stmt = stmt.where(EntityMemory.project_id == uuid.UUID(project_id))
            has_filter = True
        except (ValueError, TypeError):
            pass
        
    if not has_filter:
        return []

    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/memories/entities")
async def create_entity_memory(
    body: EntityMemoryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    t_uuid = None
    if body.team_id and body.team_id not in ("undefined", "null", ""):
        try:
            t_uuid = uuid.UUID(body.team_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid team_id format.")
    p_uuid = None
    if body.project_id and body.project_id not in ("undefined", "null", ""):
        try:
            p_uuid = uuid.UUID(body.project_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid project_id format.")

    mem = EntityMemory(
        team_id=t_uuid,
        project_id=p_uuid,
        key=body.key,
        value=body.value
    )
    db.add(mem)
    await db.commit()
    await db.refresh(mem)
    return mem

@router.delete("/memories/entities/{memory_id}")
async def delete_entity_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    if not memory_id or memory_id in ("undefined", "null", ""):
        raise HTTPException(status_code=400, detail="Invalid memory_id.")
    try:
        m_uuid = uuid.UUID(memory_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid memory_id format.")
    stmt = delete(EntityMemory).where(EntityMemory.id == m_uuid)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}


# ── Prompt Blocks ─────────────────────────────────────────────────────────────

@router.get("/settings/prompt-blocks")
async def get_prompt_blocks():
    """Return all editable system prompt blocks with their current content."""
    from core.agent.prompt_blocks import list_blocks
    return list_blocks()


@router.put("/settings/prompt-blocks")
async def save_prompt_blocks(updates: list[dict], user: dict = Depends(require_auth)):
    """Save one or more prompt block overrides. Send a list of { key, enabled, content }."""
    from core.agent.prompt_blocks import save_blocks
    save_blocks(updates)
    from core.agent.prompt_blocks import list_blocks
    return list_blocks()


@router.post("/settings/prompt-blocks/{key}/reset")
async def reset_prompt_block(key: str, user: dict = Depends(require_auth)):
    """Reset a single prompt block back to its default content."""
    from core.agent.prompt_blocks import reset_block
    try:
        return reset_block(key)
    except ValueError as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# /compact — Manual conversation compaction command
# ============================================================

@router.post("/teams/{team_id}/compact")
async def compact_team_conversation(
    team_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Manually compact the conversation history for a team.

    Triggered by the /compact slash command in the chat UI.

    Flow:
    1. Load recent non-intermediate messages for the team.
    2. Call the fast LLM to summarize them (same prompt as auto-compaction).
    3. Persist a CompactionEvent checkpoint to DB.
    4. Broadcast a 'compaction_event' SSE so the UI renders a divider.
    5. Return the summary and event metadata to the caller.
    """
    from core.config import COMPACTION_SYSTEM_PROMPT, COMPACTION_USER_PROMPT, DEFAULT_FAST_MODEL
    from core.llm.multi_model_router import llm_router
    from core.chat.event_bus import event_bus
    import json

    team = await _assert_team_access(db, team_id, user["sub"])
    t_uuid = team.id

    # Load all non-intermediate messages since the last compaction checkpoint
    from datetime import timezone
    compaction_after_dt = None
    last_cp = (
        await db.execute(
            select(CompactionEvent)
            .where(CompactionEvent.team_id == t_uuid)
            .order_by(CompactionEvent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last_cp:
        compaction_after_dt = last_cp.created_at

    msg_stmt = (
        select(Message)
        .where(Message.team_id == t_uuid)
        .where(Message.is_intermediate == False)  # noqa: E712
        .where(Message.is_private == False)        # noqa: E712
    )
    if compaction_after_dt:
        msg_stmt = msg_stmt.where(Message.created_at > compaction_after_dt)

    msg_stmt = msg_stmt.order_by(Message.created_at.asc())
    messages_raw = (await db.execute(msg_stmt)).scalars().all()

    if len(messages_raw) < 3:
        raise HTTPException(
            status_code=422,
            detail="Not enough messages to compact (need at least 3 since last compaction)."
        )

    # Convert to LLM message format for summarization
    messages_for_llm = [
        {
            "role": "assistant" if m.sender_id not in ("human", "system") else "user",
            "content": f"[{m.sender_name or m.sender_id}]: {m.text}"
        }
        for m in messages_raw
    ]

    # Call LLM to summarize
    summary_prompt = COMPACTION_USER_PROMPT.format(
        context=json.dumps(messages_for_llm, default=str)
    )
    try:
        summary = await llm_router.generate_completion(
            model=DEFAULT_FAST_MODEL,
            system_prompt=COMPACTION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": summary_prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM compaction failed: {e}")

    # Persist CompactionEvent checkpoint
    cp_event = CompactionEvent(
        team_id=t_uuid,
        summary=summary,
        message_count_before=len(messages_raw),
        triggered_by="manual",
    )
    db.add(cp_event)
    await db.commit()
    await db.refresh(cp_event)

    # Broadcast SSE so all connected clients render the compaction divider
    topic = f"team:{team_id}"
    await event_bus.publish(topic, {
        "type": "compaction_event",
        "id": str(cp_event.id),
        "sender_id": "system",
        "sender_name": "System",
        "triggered_by": "manual",
        "message_count_before": len(messages_raw),
        "summary_preview": summary[:300] + "..." if len(summary) > 300 else summary,
    })

    return {
        "event_id": str(cp_event.id),
        "messages_compacted": len(messages_raw),
        "triggered_by": "manual",
        "summary_preview": summary[:200] + "..." if len(summary) > 200 else summary,
        "created_at": cp_event.created_at.isoformat(),
    }


@router.get("/teams/{team_id}/compactions")
async def get_team_compaction_events(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Return all compaction events for a team so the UI can re-render
    compaction dividers after a page reload.
    """
    team = await _assert_team_access(db, team_id, user["sub"])
    t_uuid = team.id

    events = (
        await db.execute(
            select(CompactionEvent)
            .where(CompactionEvent.team_id == t_uuid)
            .order_by(CompactionEvent.created_at.asc())
        )
    ).scalars().all()

    return [
        {
            "id": str(e.id),
            "triggered_by": e.triggered_by,
            "message_count_before": e.message_count_before,
            "summary_preview": (e.summary[:300] + "...") if e.summary and len(e.summary) > 300 else e.summary,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]

