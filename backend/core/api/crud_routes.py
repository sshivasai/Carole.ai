"""
# backend/core/api/crud_routes.py

REST API routes for managing Projects, Teams, Agents, Tasks, and Messages.
Also provides a /api/seed endpoint for bootstrapping a demo environment.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.memory.models import User, Project, Team, Agent, Message, Task, FileBackup
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


async def _assert_team_access(db: AsyncSession, team_id: str, user_id: str) -> None:
    """
    Finding #8 — Ownership check. Raises 403 if the authenticated user does not
    own the project that this team belongs to.
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

class ProjectUpdate(BaseModel):
    name: Optional[str] = None

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

class TaskCreate(BaseModel):
    team_id: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assigned_agent_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    blocked_by_task_id: Optional[str] = None
    created_by: str = "human"

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    blocked_by_task_id: Optional[str] = None

class TaskCommentCreate(BaseModel):
    author_id: str
    author_name: str
    text: str


class McpServerCreate(BaseModel):
    team_id: str
    server_name: str
    command: str
    args: List[str] = []  # List instead of comma-separated string to support args with commas
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
    # If owner_id is provided, make sure it is valid; otherwise fetch the first user or default
    owner_uuid = None
    if body.owner_id:
        owner_uuid = uuid.UUID(body.owner_id)
    else:
        # fallback to first user
        users_result = await db.execute(select(User).limit(1))
        first_user = users_result.scalar_one_or_none()
        if first_user:
            owner_uuid = first_user.id
        else:
            owner_uuid = uuid.uuid4()
    
    project = Project(name=body.name, owner_id=owner_uuid)
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

    return {"id": str(project.id), "name": project.name}

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return [{"id": str(p.id), "name": p.name, "owner_id": str(p.owner_id)} for p in result.scalars().all()]

@router.put("/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Project).where(Project.id == uuid.UUID(project_id)))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if body.name is not None and body.name != project.name:
        project.name = body.name
        
        # Rename workspace folder if it exists
        import re
        from core.tools.file_tools import file_tools
        old_dir = await file_tools.get_workspace_root(project_id)
        
        if old_dir.exists() and old_dir.name != "workspaces":
            new_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', body.name).strip('-')
            if not new_slug:
                new_slug = str(project.id)[:8]
            new_dir = old_dir.parent / new_slug
            if old_dir != new_dir and not new_dir.exists():
                old_dir.rename(new_dir)
                
    await db.flush()
    return {"status": "updated", "id": project_id}


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
    
    await lancedb_client.insert_learning(
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
async def list_learnings(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import Learning
    from sqlalchemy import or_
    stmt = select(Learning).where(
        or_(
            Learning.project_id == uuid.UUID(project_id),
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
    
    stmt = select(Learning).where(Learning.id == uuid.UUID(learning_id))
    result = await db.execute(stmt)
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(status_code=404, detail="Learning not found")
        
    if body.task_summary is not None:
        learning.task_summary = body.task_summary
    if body.lesson_rule is not None:
        learning.lesson_rule = body.lesson_rule
    if body.project_id == "null":
        learning.project_id = None
        from core.memory.lancedb_client import lancedb_client
        await lancedb_client.update_project_id(learning_id, None)

    await db.flush()
    return {"status": "updated", "id": learning_id}

@router.delete("/learnings/{learning_id}")
async def delete_learning(learning_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import Learning
    await db.execute(delete(Learning).where(Learning.id == uuid.UUID(learning_id)))
    await db.flush()
    return {"status": "deleted", "id": learning_id}



# ============================================================
# Teams
# ============================================================

@router.post("/teams")
async def create_team(body: TeamCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    team = Team(name=body.name, project_id=uuid.UUID(body.project_id))
    db.add(team)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "project_id": str(team.project_id)}


@router.get("/teams/{project_id}")
async def list_teams(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(
        select(Team).where(Team.project_id == uuid.UUID(project_id)).order_by(Team.created_at.desc())
    )
    return [{"id": str(t.id), "name": t.name} for t in result.scalars().all()]


# ============================================================
# Agents
# ============================================================

@router.post("/agents")
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
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
    )
    db.add(agent)
    await db.commit()

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
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
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
    }

@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if agent:
        await db.execute(delete(Agent).where(Agent.id == uuid.UUID(agent_id)))
        await db.commit()
        from core.chat.message_router import message_router
        human_name = await _get_human_name(db, agent.team_id)
        await message_router.route_message(
            text=f"[AGENT_REMOVE] @{agent.name} was removed from the team by {human_name}",
            sender_id="system",
            team_id=str(agent.team_id),
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
    # Finding #2 — authentication required
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
    # Finding #2 — authentication required
    if delete_content:
        import shutil
        import re
        from core.tools.file_tools import file_tools
        try:
            result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
            team = result.scalar_one_or_none()
            if team:
                workspace_dir = await file_tools.get_workspace_root(str(team.project_id))
                team_slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', team.name).strip('-')
                team_dir = workspace_dir / team_slug
                if team_dir.exists():
                    shutil.rmtree(str(team_dir))
        except Exception as e:
            import logging
            logging.getLogger("carole.crud").warning("Failed to delete team folder: %s", e)

    await db.execute(delete(Team).where(Team.id == uuid.UUID(team_id)))
    return {"status": "deleted", "id": team_id}

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    # Finding #2 — authentication required
    await db.execute(delete(User).where(User.id == uuid.UUID(user_id)))
    return {"status": "deleted", "id": user_id}


# ============================================================
# Single-entity GET endpoints
# ============================================================

@router.get("/projects/single/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Project).where(Project.id == uuid.UUID(project_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": str(p.id), "name": p.name, "owner_id": str(p.owner_id)}

@router.get("/teams/single/{team_id}")
async def get_team(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"id": str(t.id), "name": t.name, "project_id": str(t.project_id)}


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
async def upload_file(file: UploadFile = File(...), team_id: Optional[str] = None, user: dict = Depends(require_auth)):
    """Handles file uploads for multimodal chat support, organizing them by workspace."""
    import uuid
    import os
    from core.config import CAROLE_HOME_DIR
    import os as _os
    
    # Validate file size (50 MB max)
    MAX_SIZE = 50 * 1024 * 1024
    
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ""
    filename = f"{file_id}{ext}"
    
    upload_dir = _UPLOAD_DIR  # fallback
    url_path = f"/api/uploads/{filename}"
    
    if team_id:
        from core.memory.database import async_session
        from core.memory.models import Team, Project
        from sqlalchemy import select
        
        async with async_session() as db:
            try:
                stmt = select(Team).where(Team.id == uuid.UUID(team_id))
                res = await db.execute(stmt)
                team = res.scalar_one_or_none()
                if team:
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
            except Exception as e:
                import logging as _log
                _log.getLogger("carole.upload").warning("Error resolving workspace for upload: %s", e)
                
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
    
    # Derive the base URL from environment so it works beyond localhost
    base_url = os.getenv("PUBLIC_API_URL", "http://localhost:8001")
        
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
    msg = await db.get(Message, uuid.UUID(message_id))
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")
    msg.text = body.text.strip()
    await db.commit()
    return {"ok": True, "id": message_id, "text": msg.text}


@router.delete("/messages/{message_id}")
async def delete_message(message_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """Delete a single message only. No rollback, no cascade to later messages."""
    msg = await db.get(Message, uuid.UUID(message_id))
    if not msg:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")
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
    """Delete all messages for a team permanently."""
    from sqlalchemy import delete, update
    import shutil
    from core.tools.file_tools import file_tools
    
    try:
        team_uuid = uuid.UUID(team_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid team_id")

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
    await db.commit()

    # 3. Delete Chat Media from Disk
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
    Rollback: delete this message AND all messages that came after it in the
    same team, then replay FileBackup records in reverse to restore the workspace.
    """
    from fastapi import HTTPException
    from sqlalchemy import delete as sa_delete
    from pathlib import Path
    from core.config import CAROLE_HOME_DIR
    import shutil
    import logging as _rlog
    _rollback_log = _rlog.getLogger("carole.rollback")

    msg = await db.get(Message, uuid.UUID(message_id))
    if not msg:
        raise HTTPException(404, "Message not found")

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

    # 2. Collect file backups for those messages, oldest-first so we replay in
    #    correct chronological order (but we restore in reverse = newest first)
    restored: list = []
    deleted_files: list = []
    if later_ids:
        from core.memory.models import FileBackup
        backups = (await db.execute(
            select(FileBackup)
            .where(FileBackup.message_id.in_(later_ids))
            .order_by(FileBackup.created_at.desc())  # newest change first = undo order
        )).scalars().all()

        # 3. Restore files (newest change undone first)
        restored, deleted_files = [], []
        seen_paths = set()
        for bk in backups:
            if bk.file_path in seen_paths:
                # Only restore the OLDEST backup per file path (original state)
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
                    team_carole_dir = await file_tools.get_team_carole_dir(team_id_str)
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

        # 4. Delete FileBackup records
        await db.execute(
            sa_delete(FileBackup).where(FileBackup.message_id.in_(later_ids))
        )

    # 5. Delete the messages themselves
    for m in later_msgs:
        await db.delete(m)
    await db.commit()

    from core.chat.event_bus import event_bus
    
    # 6. Broadcast file_change events so the diff panel updates immediately
    for fp in restored:
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "file_change",
            "action": "rollback_restore",
            "path": fp,
            "diff": None,
        })
    for fp in deleted_files if later_ids else []:
        await event_bus.publish(f"team:{team_id_str}", {
            "type": "file_change",
            "action": "rollback_delete",
            "path": fp,
            "diff": None,
        })

    # 7. Broadcast rewind event
    await event_bus.publish(f"team:{team_id_str}", {
        "type": "message_rewind",
        "from_message_id": message_id,
        "from_timestamp": pivot_time.isoformat() if pivot_time else None,
        "restored_files": restored if later_ids else [],
        "deleted_files": deleted_files if later_ids else [],
    })

    return {
        "ok": True,
        "deleted_count": len(later_msgs),
        "restored_files": restored if later_ids else [],
        "deleted_files": deleted_files if later_ids else [],
    }



# ============================================================
# Agent Stop (Cancel streaming generation)
# ============================================================

@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, cancel_all: bool = False, user: dict = Depends(require_auth)):
    """
    Cancel the currently executing agent loop.
    If cancel_all=true, also drains the entire queue so no further
    queued tasks will execute.
    """
    from core.chat.message_router import message_router
    cancelled = message_router.cancel_agent(agent_id, cancel_all=cancel_all)
    return {"ok": True, "cancelled_tasks": cancelled, "queue_cleared": cancel_all}


@router.get("/agents/{agent_id}/queue")
async def get_agent_queue(agent_id: str, user: dict = Depends(require_auth)):
    """
    Return the current queue status for an agent:
    - queue_depth: number of tasks waiting
    - is_running: whether the agent is actively executing a loop right now
    - pending: list of pending prompt strings
    """
    from core.chat.message_router import message_router
    return message_router.get_queue_status(agent_id)


# ============================================================
# Tasks
# ============================================================

@router.post("/tasks")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.chat.event_bus import event_bus
    from core.chat.message_router import message_router

    task = Task(
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assigned_agent_id=uuid.UUID(body.assigned_agent_id) if body.assigned_agent_id else None,
        parent_task_id=uuid.UUID(body.parent_task_id) if body.parent_task_id else None,
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
            },
        })
        if body.created_by == "human" or not body.created_by:
            creator = await _get_human_name(db, task.team_id)
        else:
            creator = body.created_by
        if agent:
            # Task was assigned — notify assignee
            if task.blocked_by_task_id:
                assign_text = f"[TASK_ASSIGN] @{agent.name} a new task '{task.title}' was created and assigned to you by {creator}. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet."
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
            # Task is unassigned — ping the Coordinator to triage it
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
            else:
                await message_router.route_message(
                    text=f"[TASK_CREATE] {creator} created task '{task.title}' (unassigned).",
                    sender_id="system",
                    team_id=str(task.team_id),
                    sender_name="System",
                    attachments=[]
                )

    if agent:
        prompt = f"The human just assigned a new task to you on the Kanban board: '{task.title}'. Please review it and start working."
        await message_router._trigger_agent(agent, prompt, db)

    return {"id": str(task.id), "title": task.title, "status": task.status}

@router.get("/tasks/{team_id}")
async def list_tasks(team_id: str, status: Optional[str] = None, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
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
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in result.scalars().all()
    ]

@router.put("/tasks/{task_id}")
async def update_task(task_id: str, body: TaskUpdate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
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
    task.updated_at = datetime.utcnow()
    await db.commit()

    from core.chat.message_router import message_router
    from core.memory.models import Agent
    human_name = await _get_human_name(db, task.team_id)
    sys_text = f"[TASK_UPDATE] '{task.title}' moved to {task.status} by {human_name}"
    if task.assigned_agent_id:
        agent_res = await db.execute(select(Agent).where(Agent.id == task.assigned_agent_id))
        agent = agent_res.scalar_one_or_none()
        if agent:
            # Wake agent if assignment changed or task moved to in_progress
            if body.assigned_agent_id:
                if task.blocked_by_task_id:
                    assign_text = f"[TASK_ASSIGN] @{agent.name} task '{task.title}' has been assigned to you. However, it is currently BLOCKED by another task. You will be notified when it is unblocked. Do not start work yet."
                else:
                    assign_text = f"[TASK_ASSIGN] @{agent.name} task '{task.title}' has been assigned to you. Please start working on it."
                await message_router.route_message(
                    text=assign_text,
                    sender_id="system",
                    team_id=str(task.team_id),
                    sender_name="System",
                    attachments=[]
                )
            elif body.status == "in_progress":
                if task.blocked_by_task_id:
                    update_text = f"[TASK_UPDATE] @{agent.name} your task '{task.title}' has been moved to 'In Progress'. However, it is currently BLOCKED. You may investigate it, but wait for the blocking task to complete before making major changes."
                else:
                    update_text = f"[TASK_UPDATE] @{agent.name} your task '{task.title}' has been moved to 'In Progress'. Please begin work now."
                await message_router.route_message(
                    text=update_text,
                    sender_id="system",
                    team_id=str(task.team_id),
                    sender_name="System",
                    attachments=[]
                )

    await message_router.route_message(
        text=sys_text,
        sender_id="system",
        team_id=str(task.team_id),
        sender_name="System",
        attachments=[]
    )

    return {"status": "updated", "id": task_id}


from core.memory.models import TaskComment

@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    result = await db.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    from core.memory.models import Agent
    from core.chat.message_router import message_router

    # UNBLOCK ENGINE: If a task is deleted, unblock tasks waiting on it
    unblock_stmt = select(Task).where(Task.blocked_by_task_id == task.id)
    unblock_res = await db.execute(unblock_stmt)
    blocked_tasks = unblock_res.scalars().all()
    for b_task in blocked_tasks:
        b_task.blocked_by_task_id = None
        b_task.updated_at = datetime.utcnow()
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
    result = await db.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    comment = TaskComment(
        task_id=uuid.UUID(task_id),
        author_id=body.author_id,
        author_name=body.author_name,
        text=body.text
    )
    db.add(comment)
    await db.flush()
    
    from core.chat.message_router import message_router
    sys_text = f"[TASK_COMMENT] {body.author_name} commented on '{task.title}'"
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
    save_model_catalog(body)
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
async def transcribe_audio_upload(team_id: str, file: UploadFile = File(...), user: dict = Depends(require_auth)):
    """
    Accepts an audio file upload, transcribes it via OpenAI Whisper,
    and broadcasts the transcription to the team EventBus.
    """
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
            "role": "Coordinator",
            "model": DEFAULT_FAST_MODEL,
            "personality": "casual",
            "tool_permissions": {
                "read_file": "safe", "list_directory": "safe",
                "web_search": "safe", "web_fetch": "safe",
                "spawn_agent": "safe", "send_message": "safe",
                "create_task": "safe", "list_tasks": "safe", "update_task": "safe",
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
    from core.knowledge.knowledge_ingestor import ingest_file

    data = await file.read()
    res = await ingest_file(db, project_id, team_id, file.filename, data)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


# ============================================================
# Estimated Token Usage & Cost Routing
# ============================================================

@router.get("/usage/{project_id}")
async def get_project_usage(project_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Returns estimated token usage and cost for all agents in the project.
    """
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
        safe_statuses[key_str] = v
    return safe_statuses

@router.post("/mcp")
async def add_mcp_server(body: McpServerCreate, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager
    import asyncio
    
    # args is now List[str] directly — no splitting needed
    args_list = body.args

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

@router.post("/mcp/global/{server_name}/toggle")
async def toggle_global_mcp(server_name: str, user: dict = Depends(require_auth)):
    import json
    import asyncio
    from core.config import GLOBAL_MCPS, DISABLED_GLOBAL_MCPS_FILE
    from core.tools.mcp_client import mcp_manager
    
    mcp_config = next((m for m in GLOBAL_MCPS if m["server_name"] == server_name), None)
    if not mcp_config:
        raise HTTPException(404, "Global MCP not found")
        
    disabled_mcps = []
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
        if key in mcp_manager.sessions:
            mcp_manager.sessions.pop(key, None)
    else:
        disabled_mcps.remove(server_name)
        asyncio.create_task(
            mcp_manager.connect_stdio_server(
                server_name=mcp_config["server_name"],
                command=mcp_config["command"],
                args=mcp_config["args"],
                team_id=None,
                agent_id=None,
            ),
            name=f"{server_name}_mcp_server",
        )
        
    with open(DISABLED_GLOBAL_MCPS_FILE, "w") as f:
        json.dump(disabled_mcps, f)
        
    return {"ok": True, "server_name": server_name, "is_disabled": is_disabling}

@router.get("/mcp/{team_id}")
async def list_mcp_servers(team_id: str, db: AsyncSession = Depends(get_db), user: dict = Depends(require_auth)):
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
    stmt = select(McpServer).where(McpServer.id == uuid.UUID(server_id))
    result = await db.execute(stmt)
    server = result.scalars().first()
    if not server:
        raise HTTPException(404, "MCP server not found")
        
    await db.delete(server)
    
    # Also disconnect from mcp_manager
    # mcp_manager uses a tuple key: (team_id, agent_id, server_name)
    key = (str(server.team_id), str(server.agent_id) if server.agent_id else "global", server.server_name)
    if key in mcp_manager.sessions:
        # Drop our reference to the session. The underlying connection is owned by
        # the manager's AsyncExitStack and is fully released on app shutdown.
        mcp_manager.sessions.pop(key, None)
    
    await db.commit()
    from core.chat.message_router import message_router
    human_name = await _get_human_name(db, server.team_id)
    await message_router.route_message(
        text=f"[MCP_DELETE] MCP Server '{server.server_name}' was disconnected by {human_name}",
        sender_id="system",
        team_id=str(server.team_id),
        sender_name="System",
        attachments=[]
    )
    
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
async def get_settings():
    """
    Returns the current application settings from ~/.carole/config.json.
    API key values are masked (last 4 chars visible) for security.
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
        # Skip masked placeholder values sent back from the UI
        if v and not all(c == "*" for c in v.replace("-", "").replace("_", "")):
            new_keys[k] = v.strip()

    new_providers = {**current.get("providers", {}), **body.providers}
    new_default_models = {**current.get("default_models", {}), **body.default_models}
    new_agent_settings = {**current.get("agent_settings", {}), **body.agent_settings}

    current_ba = current.get("browser_automation", {})
    new_ba = {**current_ba, **body.browser_automation}
    new_ba_keys = dict(current_ba.get("api_keys", {}))
    for k, v in body.browser_automation.get("api_keys", {}).items():
        if v and not all(c == "*" for c in v.replace("-", "").replace("_", "")):
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
    if team_id:
        stmt = stmt.where(EntityMemory.team_id == uuid.UUID(team_id))
    if project_id:
        stmt = stmt.where(EntityMemory.project_id == uuid.UUID(project_id))
        
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/memories/entities")
async def create_entity_memory(
    body: EntityMemoryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(require_auth)
):
    mem = EntityMemory(
        team_id=uuid.UUID(body.team_id) if body.team_id else None,
        project_id=uuid.UUID(body.project_id) if body.project_id else None,
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
    stmt = delete(EntityMemory).where(EntityMemory.id == uuid.UUID(memory_id))
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
