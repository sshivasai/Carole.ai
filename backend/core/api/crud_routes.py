"""
# backend/core/api/crud_routes.py

REST API routes for managing Projects, Teams, Agents, Tasks, and Messages.
Also provides a /api/seed endpoint for bootstrapping a demo environment.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import get_db
from core.memory.models import User, Project, Team, Agent, Message, Task
from core.tools.tool_registry import ToolRegistry

router = APIRouter(prefix="/api", tags=["crud"])


# ============================================================
# Pydantic Schemas
# ============================================================

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
    model: str = "gpt-4o-mini"
    system_prompt: str = ""
    personality: str = "professional"  # professional, casual, witty, mentor
    tool_permissions: dict = {}

class AgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    personality: Optional[str] = None
    tool_permissions: Optional[dict] = None

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


# ============================================================
# Projects
# ============================================================

@router.post("/projects")
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(name=body.name, owner_id=body.owner_id or uuid.uuid4())
    db.add(project)
    await db.flush()
    return {"id": str(project.id), "name": project.name}

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    return [{"id": str(p.id), "name": p.name} for p in result.scalars().all()]


# ============================================================
# Teams
# ============================================================

@router.post("/teams")
async def create_team(body: TeamCreate, db: AsyncSession = Depends(get_db)):
    team = Team(name=body.name, project_id=body.project_id)
    db.add(team)
    await db.flush()
    return {"id": str(team.id), "name": team.name, "project_id": str(team.project_id)}

@router.get("/teams/{project_id}")
async def list_teams(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team).where(Team.project_id == project_id).order_by(Team.created_at.desc())
    )
    return [{"id": str(t.id), "name": t.name} for t in result.scalars().all()]


# ============================================================
# Agents
# ============================================================

@router.post("/agents")
async def create_agent(body: AgentCreate, db: AsyncSession = Depends(get_db)):
    agent = Agent(
        team_id=body.team_id,
        name=body.name,
        role=body.role,
        model=body.model,
        system_prompt=body.system_prompt or _default_system_prompt(body.name, body.role, body.personality),
        tool_permissions=body.tool_permissions,
    )
    db.add(agent)
    await db.flush()
    return {
        "id": str(agent.id), "name": agent.name, "role": agent.role,
        "model": agent.model, "team_id": str(agent.team_id),
    }

@router.get("/agents/{team_id}")
async def list_agents(team_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Agent).where(Agent.team_id == team_id).order_by(Agent.created_at)
    )
    return [
        {
            "id": str(a.id), "name": a.name, "role": a.role,
            "model": a.model, "tool_permissions": a.tool_permissions,
        }
        for a in result.scalars().all()
    ]

@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, body: AgentUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if body.name is not None:
        agent.name = body.name
    if body.role is not None:
        agent.role = body.role
    if body.model is not None:
        agent.model = body.model
    if body.system_prompt is not None:
        agent.system_prompt = body.system_prompt
    if body.tool_permissions is not None:
        agent.tool_permissions = body.tool_permissions
    await db.flush()
    return {"status": "updated", "id": agent_id}

@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Agent).where(Agent.id == agent_id))
    return {"status": "deleted", "id": agent_id}


# ============================================================
# Messages
# ============================================================

@router.get("/messages/{team_id}")
async def list_messages(team_id: str, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message)
        .where(Message.team_id == team_id)
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
    task = Task(
        team_id=body.team_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        assigned_agent_id=body.assigned_agent_id,
        parent_task_id=body.parent_task_id,
        created_by=body.created_by,
    )
    db.add(task)
    await db.flush()
    return {"id": str(task.id), "title": task.title, "status": task.status}

@router.get("/tasks/{team_id}")
async def list_tasks(team_id: str, status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Task).where(Task.team_id == team_id)
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
    result = await db.execute(select(Task).where(Task.id == task_id))
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
            "model": "gpt-4o-mini",
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
            "model": "gpt-4o-mini",
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
            "model": "gpt-4o-mini",
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
