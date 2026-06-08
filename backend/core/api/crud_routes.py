"""
# backend/core/api/crud_routes.py

REST API routes for managing Projects, Teams, Agents, Tasks, and Messages.
Also provides a /api/seed endpoint for bootstrapping a demo environment.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.memory.models import User, Project, Team, Agent, Message, Task
from core.tools.tool_registry import ToolRegistry
from core.config import DEFAULT_FAST_MODEL

router = APIRouter(prefix="/api", tags=["crud"])


# ============================================================
# Pydantic Schemas
# ============================================================

class UserCreate(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    password: str = "demo"

class LearningCreate(BaseModel):
    project_id: str
    task_summary: str
    lesson_rule: str
    team_id: Optional[str] = None

class ProjectCreate(BaseModel):
    name: str
    owner_id: Optional[str] = None

class TeamCreate(BaseModel):
    name: str
    project_id: str

class AgentCreate(BaseModel):
    team_id: str
    name: str
    role: str
    model: str = DEFAULT_FAST_MODEL
    system_prompt: str = ""
    personality: str = "professional"  # professional, casual, witty, mentor
    tool_permissions: dict = {}
    custom_instructions: Optional[str] = None
    skills: Optional[List[str]] = None

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
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
    created_by: str = "human"

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None


class McpServerCreate(BaseModel):
    team_id: str
    server_name: str
    command: str
    args: str
    agent_id: Optional[str] = None

# ============================================================
# Users / Tenants
# ============================================================

@router.post("/users")
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(
        email=body.email,
        hashed_password=body.password,
        first_name=body.first_name,
        last_name=body.last_name,
        is_verified=True,
    )
    db.add(user)
    await db.flush()
    return {"id": str(user.id), "email": user.email, "first_name": user.first_name, "last_name": user.last_name}

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return [{"id": str(u.id), "email": u.email, "first_name": u.first_name, "last_name": u.last_name} for u in result.scalars().all()]


# ============================================================
# Projects
# ============================================================

@router.post("/projects")
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
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
    return {"id": str(project.id), "name": project.name}

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return [{"id": str(p.id), "name": p.name, "owner_id": str(p.owner_id)} for p in result.scalars().all()]


# ============================================================
# Learnings (Knowledge base)
# ============================================================

@router.post("/learnings")
async def create_learning(body: LearningCreate, db: AsyncSession = Depends(get_db)):
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
    await db.flush()
    
    await lancedb_client.insert_learning(
        project_id=body.project_id,
        team_id=body.team_id,
        task_summary=body.task_summary,
        lesson_rule=body.lesson_rule,
        vector=embedding
    )
    
    return {"id": str(learning.id), "task_summary": learning.task_summary, "lesson_rule": learning.lesson_rule}

@router.get("/learnings/{project_id}")
async def list_learnings(project_id: str, db: AsyncSession = Depends(get_db)):
    from core.memory.models import Learning
    stmt = select(Learning).where(Learning.project_id == uuid.UUID(project_id)).order_by(Learning.created_at.desc())
    result = await db.execute(stmt)
    return [
        {
            "id": str(l.id),
            "task_summary": l.task_summary,
            "lesson_rule": l.lesson_rule,
            "team_id": str(l.team_id) if l.team_id else None,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in result.scalars().all()
    ]

@router.put("/learnings/{learning_id}")
async def update_learning(learning_id: str, body: LearningCreate, db: AsyncSession = Depends(get_db)):
    from core.memory.models import Learning
    from core.memory.lancedb_client import lancedb_client
    
    stmt = select(Learning).where(Learning.id == uuid.UUID(learning_id))
    result = await db.execute(stmt)
    learning = result.scalar_one_or_none()
    if not learning:
        raise HTTPException(status_code=404, detail="Learning not found")
        
    learning.task_summary = body.task_summary
    learning.lesson_rule = body.lesson_rule
    await db.flush()
    return {"status": "updated", "id": learning_id}

@router.delete("/learnings/{learning_id}")
async def delete_learning(learning_id: str, db: AsyncSession = Depends(get_db)):
    from core.memory.models import Learning
    await db.execute(delete(Learning).where(Learning.id == uuid.UUID(learning_id)))
    await db.flush()
    return {"status": "deleted", "id": learning_id}



# ============================================================
# Teams
# ============================================================

@router.post("/teams")
async def create_team(body: TeamCreate, db: AsyncSession = Depends(get_db)):
    team = Team(name=body.name, project_id=uuid.UUID(body.project_id))
    db.add(team)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "project_id": str(team.project_id)}


@router.get("/teams/{project_id}")
async def list_teams(project_id: str, db: AsyncSession = Depends(get_db)):
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
        system_prompt=prompt,
        personality=body.personality,
        custom_instructions=body.custom_instructions,
        skills=body.skills or [],
        tool_permissions=body.tool_permissions,
    )
    db.add(agent)
    await db.flush()
    return {
        "id": str(agent.id), "name": agent.name, "role": agent.role,
        "model": agent.model, "team_id": str(agent.team_id),
        "personality": agent.personality, "skills": agent.skills,
        "custom_instructions": agent.custom_instructions,
    }

@router.get("/agents/{team_id}")
async def list_agents(team_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Agent).where(Agent.team_id == uuid.UUID(team_id)).order_by(Agent.created_at)
    )
    return [
        {
            "id": str(a.id), "name": a.name, "role": a.role,
            "model": a.model, "tool_permissions": a.tool_permissions,
            "personality": a.personality, "skills": a.skills or [],
            "custom_instructions": a.custom_instructions,
        }
        for a in result.scalars().all()
    ]

@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
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
    await db.flush()
    return {"status": "updated", "id": agent_id}

@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Agent).where(Agent.id == uuid.UUID(agent_id)))
    return {"status": "deleted", "id": agent_id}


# ============================================================
# Delete endpoints for Projects, Teams, Users
# ============================================================

@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Project).where(Project.id == uuid.UUID(project_id)))
    return {"status": "deleted", "id": project_id}

@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Team).where(Team.id == uuid.UUID(team_id)))
    return {"status": "deleted", "id": team_id}

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(User).where(User.id == uuid.UUID(user_id)))
    return {"status": "deleted", "id": user_id}


# ============================================================
# Single-entity GET endpoints
# ============================================================

@router.get("/projects/single/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == uuid.UUID(project_id)))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": str(p.id), "name": p.name, "owner_id": str(p.owner_id)}

@router.get("/teams/single/{team_id}")
async def get_team(team_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Team not found")
    return {"id": str(t.id), "name": t.name, "project_id": str(t.project_id)}


# ============================================================
# Messages
# ============================================================

@router.get("/messages/{team_id}")
async def list_messages(team_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.team_id == uuid.UUID(team_id))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id), "sender_id": m.sender_id,
            "recipient_id": m.recipient_id, "text": m.text,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in reversed(messages)  # chronological order
    ]


# ============================================================
# Tasks
# ============================================================

@router.post("/tasks")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
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
    await db.flush()

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

    if agent:
        prompt = f"The human just assigned a new task to you on the Kanban board: '{task.title}'. Please review it and start working."
        await message_router._trigger_agent(agent, prompt, db)

    return {"id": str(task.id), "title": task.title, "status": task.status}

@router.get("/tasks/{team_id}")
async def list_tasks(team_id: str, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
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
async def update_task(task_id: str, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == uuid.UUID(task_id)))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.status is not None:
        task.status = body.status
    if body.priority is not None:
        task.priority = body.priority
    if body.assigned_agent_id is not None:
        task.assigned_agent_id = body.assigned_agent_id
    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    task.updated_at = datetime.utcnow()
    await db.flush()
    return {"status": "updated", "id": task_id}


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


# ============================================================
# Semantic Search (pgvector)
# ============================================================

@router.get("/messages/search/{team_id}")
async def search_messages(team_id: str, q: str, limit: int = 10, db: AsyncSession = Depends(get_db)):
    """Simple text search over past team messages using ILIKE."""
    from core.memory.models import Message

    stmt = (
        select(Message)
        .where(Message.team_id == uuid.UUID(team_id))
        .where(Message.text.ilike(f"%{q}%"))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()

    return [
        {
            "id": str(m.id), "sender_id": m.sender_id,
            "text": m.text,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


# ============================================================
# Audio Transcription Upload
# ============================================================

@router.post("/audio/transcribe/{team_id}")
async def transcribe_audio_upload(team_id: str, file: UploadFile = File(...)):
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
    # Check if already seeded
    existing = await db.execute(select(User).limit(1))
    if existing.scalar_one_or_none():
        return {"status": "already_seeded"}

    user = User(
        email="admin@carole.ai",
        hashed_password="demo",
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
    """Generates a human-like system prompt so agents talk like real devs."""

    personality_traits = {
        "professional": (
            f"You are {name}, a {role} on this engineering team. "
            "You communicate clearly and directly, like a senior engineer in a Slack channel. "
            "Keep messages concise. Use casual technical language — say 'looks good', 'let me check', "
            "'hmm that's a bit off', 'on it', 'done ✓'. Never be robotic or overly formal. "
            "When you spot issues, be direct: 'this will break because...' not 'I would suggest considering...'. "
            "Share your reasoning briefly. Use emoji sparingly but naturally (✓, 🔥, 👀, 🐛)."
        ),
        "casual": (
            f"You are {name}, the {role} of this team. You're the one who keeps things moving. "
            "Talk like you're in a team standup — relaxed, direct, no fluff. "
            "Say things like 'yo, let me handle that', 'alright so here's the plan', "
            "'heads up — this needs attention', 'shipped it 🚀'. "
            "You delegate clearly: 'Hey @Nova, can you take the API routes? I'll handle the schema.' "
            "When things go wrong, stay calm: 'okay that broke, let me figure out why'. "
            "You think out loud briefly before acting."
        ),
        "witty": (
            f"You are {name}, a {role} who writes clean code and occasionally drops a dry one-liner. "
            "You're the dev who names variables well and leaves helpful comments. "
            "Talk naturally: 'alright, writing the handler now', 'this function is doing too much, "
            "let me split it', 'tests passing ✓', 'found the bug — it was a classic off-by-one 🤦'. "
            "Be helpful and proactive. When you finish something, share what you did concisely. "
            "If you hit an error, say what happened and what you're trying next."
        ),
        "mentor": (
            f"You are {name}, a senior {role} who reviews code thoughtfully. "
            "You're the teammate who catches edge cases and suggests better patterns. "
            "Talk like a senior dev in a PR review: 'nice approach, but consider using X here', "
            "'this works but it'll be hard to test — what about...', 'lgtm 👍', "
            "'one nit: the naming could be clearer'. "
            "Be constructive, never condescending. When you approve something, be genuine: "
            "'solid work, this is clean'. When something needs changes, be specific about why."
        ),
    }

    base = personality_traits.get(personality, personality_traits["professional"])

    return (
        f"{base}\n\n"
        "IMPORTANT BEHAVIORAL RULES:\n"
        "1. You are part of a real engineering team. Address teammates by name when relevant.\n"
        "2. Think step by step but share only the key reasoning, not every thought.\n"
        "3. When you use a tool, briefly say what you're doing: 'let me read that file first' or 'running the tests now'.\n"
        "4. After completing work, summarize what you did in 1-2 sentences.\n"
        "5. If you're unsure, say so honestly: 'not 100% sure about this, let me check'.\n"
        "6. Coordinate with teammates — if a task isn't yours, suggest who should handle it.\n"
        "7. When you see a file change or code, give concrete feedback, not generic praise.\n"
        "8. Use [ACTION]tool_name({\"param\": \"value\"})[/ACTION] to invoke tools.\n"
        "9. When done, just say your final answer naturally — no [ACTION] tag means you're done.\n"
    )


# ============================================================
# Knowledge Upload & Ingestion
# ============================================================

@router.post("/knowledge/upload")
async def upload_knowledge(
    project_id: str,
    team_id: Optional[str] = None,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
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
async def get_project_usage(project_id: str, db: AsyncSession = Depends(get_db)):
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

@router.post("/mcp")
async def add_mcp_server(body: McpServerCreate, db: AsyncSession = Depends(get_db)):
    from core.memory.models import McpServer
    from core.tools.mcp_client import mcp_manager
    import asyncio
    
    # Parse args
    args_list = [arg.strip() for arg in body.args.split(",") if arg.strip()]

    server = McpServer(
        team_id=uuid.UUID(body.team_id),
        agent_id=uuid.UUID(body.agent_id) if body.agent_id else None,
        server_name=body.server_name,
        command=body.command,
        args=args_list,
        env_vars=None
    )
    db.add(server)
    await db.flush()

    # Launch in background
    asyncio.create_task(
        mcp_manager.connect_stdio_server(
            server_name=body.server_name,
            command=body.command,
            args=args_list,
            team_id=body.team_id,
            agent_id=body.agent_id
        )
    )

    return {"id": str(server.id), "status": "connecting"}

@router.get("/mcp/{team_id}")
async def list_mcp_servers(team_id: str, db: AsyncSession = Depends(get_db)):
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


