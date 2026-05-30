"""
# backend/core/memory/models.py

This file defines the SQLAlchemy database models for Carole.ai.

Multi-Tenant Hierarchical Architecture:
1. User - The top-level account owner.
2. Project - A workspace belonging to a User. Contains multiple Teams.
3. Team - Group chat environments containing agents and humans, scoped under a Project.
4. Agent - Customizable AI entities with assigned roles, scoped under a Team.
5. Message - Short-term chat history logs scoped under a Team. Supports semantic search via vector embeddings.
6. Learning - Semantic long-term memory (pgvector). Can be scoped Project-wide OR Team-specific.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    
    # Each Project belongs to a User Account
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    
    # Each Team is scoped under a Project
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)  # e.g. "Coder", "Reviewer", "Manager"
    model = Column(String(50), nullable=False)   # e.g. "claude-3-5-sonnet", "gpt-4o-mini", "qwen"
    system_prompt = Column(Text, nullable=False)
    
    # JSONB columns for dynamic configuration
    tool_permissions = Column(JSON, nullable=False, default=dict)  # {"file_read": "safe", "bash": "human_only"}
    working_memory = Column(JSON, nullable=True, default=dict)    # Scratchpad state / current task variables
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    
    # Direct routing keys
    sender_id = Column(String(100), nullable=False)  # "human" or specific agent UUID
    recipient_id = Column(String(100), nullable=True) # Null for group broadcast, specific agent ID for private message (/@name)
    
    text = Column(Text, nullable=False)
    
    # Optional pgvector embedding of the message text.
    # Enables humans or agents to perform semantic vector searches on historical team conversations!
    embedding = Column(Vector(1536), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

class Learning(Base):
    __tablename__ = "learnings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Bound primarily to the parent Project boundary
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # OPTIONAL Scope Boundaries:
    # 1. If team_id is NULL, knowledge is shared Project-wide (all teams).
    # 2. If team_id is set, knowledge is restricted ONLY to this specific team.
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    
    # Optional direct bind to a specific agent's personal history
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    task_summary = Column(Text, nullable=False)  # Context of what was executed
    lesson_rule = Column(Text, nullable=False)   # Concrete rule to avoid future mistakes
    
    # pgvector embedding column (1536 dimensions)
    embedding = Column(Vector(1536), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
