"""
# backend/core/memory/models.py

This file defines the SQLAlchemy database models for Carole.ai.

Multi-Tenant Hierarchical Architecture:
1. User - The top-level account owner.
2. Project - A workspace belonging to a User. Contains multiple Teams.
3. Team - Group chat environments containing agents and humans, scoped under a Project.
4. Agent - Customizable AI entities with assigned roles, scoped under a Team.
5. Message - Short-term chat history logs scoped under a Team.
6. Learning - Semantic long-term memory. Vectors are stored externally in LanceDB. Can be scoped Project-wide OR Team-specific.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean, Uuid
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    
    is_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    avatar_url = Column(String(512), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Each Project belongs to a User Account
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Team(Base):
    __tablename__ = "teams"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Each Team is scoped under a Project
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)  # e.g. "Coder", "Reviewer", "Manager", or custom role
    model = Column(String(50), nullable=False)   # e.g. "claude-sonnet-4", "gpt-4o-mini", "gemini-2.0-flash"
    system_prompt = Column(Text, nullable=False)
    
    # Personality style: professional, casual, witty, mentor
    personality = Column(String(50), nullable=True, default="professional")
    
    # Custom role instructions provided during agent creation
    custom_instructions = Column(Text, nullable=True)
    
    # List of specialized skills/toolkits the agent has
    skills = Column(JSON, nullable=True, default=list)
    
    # JSON columns for dynamic configuration
    tool_permissions = Column(JSON, nullable=False, default=dict)  # {"file_read": "safe", "bash": "human_only"}
    working_memory = Column(JSON, nullable=True, default=dict)    # Scratchpad state / current task variables
    
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    
    # Direct routing keys
    sender_id = Column(String(100), nullable=False)  # "human" or specific agent UUID
    sender_name = Column(String(100), nullable=True)  # Display name for the sender
    recipient_id = Column(String(100), nullable=True) # Null for group broadcast, specific agent ID for private message (/@name)
    is_private = Column(Boolean, default=False, nullable=False) # True if sent via /@name
    
    text = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Learning(Base):
    __tablename__ = "learnings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    
    # Bound primarily to the parent Project boundary
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # OPTIONAL Scope Boundaries:
    # 1. If team_id is NULL, knowledge is shared Project-wide (all teams).
    # 2. If team_id is set, knowledge is restricted ONLY to this specific team.
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    
    # Optional direct bind to a specific agent's personal history
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    task_summary = Column(Text, nullable=False)  # Context of what was executed
    lesson_rule = Column(Text, nullable=False)   # Concrete rule to avoid future mistakes
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    
    # Workflow states: todo → in_progress → review → done | blocked
    status = Column(String(20), nullable=False, default="todo")
    priority = Column(String(10), nullable=False, default="medium")  # low, medium, high, critical
    
    assigned_agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    parent_task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True)
    created_by = Column(String(100), nullable=False, default="human")  # agent_id or "human"
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenUsage(Base):
    """
    Tracks LLM token usage and estimated cost per agent call.
    Enables cost monitoring per project/agent over time.
    """
    __tablename__ = "token_usage"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    agent_name = Column(String(100), nullable=True)

    model = Column(String(80), nullable=False)
    provider = Column(String(30), nullable=False)        # anthropic | openai | google | qwen | ollama

    prompt_tokens = Column(String(20), nullable=True)   # stored as string for flexibility
    completion_tokens = Column(String(20), nullable=True)
    total_tokens = Column(String(20), nullable=True)
    estimated_cost_usd = Column(String(20), nullable=True)  # e.g. "0.0024"

    created_at = Column(DateTime, default=datetime.utcnow)

class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    server_name = Column(String(255), nullable=False)
    command = Column(String(255), nullable=False)
    args = Column(JSON, nullable=False, default=list)
    env_vars = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
