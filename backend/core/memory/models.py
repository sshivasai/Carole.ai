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
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Boolean, Uuid, Integer, Numeric, Float, Index, func
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
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Project(Base):
    __tablename__ = "projects"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Each Project belongs to a User Account
    owner_id = Column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Cost Management — stored as Numeric for SQL aggregation
    budget_limit_usd = Column(Numeric(10, 4), nullable=True)
    total_spend_usd = Column(Numeric(10, 4), nullable=False, default=0.0)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Team(Base):
    __tablename__ = "teams"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Each Team is scoped under a Project
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    role = Column(String(100), nullable=False)  # e.g. "Coder", "Reviewer", "Manager", or custom role
    model = Column(String(100), nullable=False)  # e.g. "claude-sonnet-4", "gpt-4o-mini", "gemini-2.0-flash"
    fallback_model = Column(String(100), nullable=True)  # Optional recovery model if primary fails
    # Reasoning effort for reasoning-capable models: none | low | medium | high
    reasoning_effort = Column(String(20), nullable=False, default="none")
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

    # Implementation plan auto-approval: if True, plans created by this agent
    # are approved automatically without requiring admin review.
    auto_approve_plans = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

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
    # Raw model reasoning / thinking trace (for DeepSeek R1, Claude thinking, etc.)
    reasoning_text = Column(Text, nullable=True)
    attachments = Column(JSON, nullable=True, default=list)

    # Tracks whether the AutoDream worker has processed this message for memory consolidation.
    # Prevents duplicate lesson extraction across dream cycles.
    processed = Column(Boolean, default=False, nullable=False)

    # Monotonically increasing integer for stable sub-second ordering (tiebreaker after created_at).
    # SQLite/Postgres autoincrement ensures globally unique order even within the same second.
    sequence = Column(Integer, autoincrement=True, nullable=True, index=True)

    # True for intermediate per-loop rows (thought + tool trace). False for final agent responses.
    # Lets the UI render intermediate steps as compact collapsed rows vs full chat bubbles.
    is_intermediate = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Composite indexes for hot query paths: team_id + created_at is the most
    # common access pattern (loading chat history). team_id + sender_id is used
    # for per-agent history filtering.
    __table_args__ = (
        Index('ix_messages_team_created', 'team_id', 'created_at'),
        Index('ix_messages_team_sender', 'team_id', 'sender_id'),
    )

class Learning(Base):
    __tablename__ = "learnings"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    
    # Bound primarily to the parent Project boundary (NULL means global cross-project knowledge)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    
    # OPTIONAL Scope Boundaries:
    # 1. If team_id is NULL, knowledge is shared Project-wide (all teams).
    # 2. If team_id is set, knowledge is restricted ONLY to this specific team.
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    
    # Optional direct bind to a specific agent's personal history
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    task_summary = Column(Text, nullable=False)  # Context of what was executed
    lesson_rule = Column(Text, nullable=False)   # Concrete rule to avoid future mistakes
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Wave 5.4: Confidence decay
    confidence_score = Column(Float, default=1.0, server_default="1.0", nullable=False)
    last_validated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now())

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
    blocked_by_task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_by = Column(String(100), nullable=False, default="human")  # agent_id or "human"

    # ── Implementation Plan ───────────────────────────────────────────────────
    # Path to the plan .md file on disk:
    #   ~/.carole/workspaces/{project_slug}/.carole/{team_slug}/plans/{task_id}_plan.md
    plan_file_path = Column(String(1000), nullable=True)

    # Cached markdown content of the plan (mirrors disk file for fast reads)
    implementation_plan = Column(Text, nullable=True)

    # Lifecycle: draft → awaiting_approval → approved | rejected | revision_requested
    plan_status = Column(String(30), nullable=True, default="draft")

    # Admin review notes / rejection reason / revision requests
    plan_feedback = Column(Text, nullable=True)

    # ── Todo Checklist ────────────────────────────────────────────────────────
    # JSON list: [{"id": "t1", "text": "...", "done": false}, ...]
    todo_list = Column(JSON, nullable=True, default=list)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TaskComment(Base):
    __tablename__ = "task_comments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    
    author_id = Column(String(100), nullable=False)  # "human" or agent_id
    author_name = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PlanInlineComment(Base):
    """A per-line inline comment anchored to a specific line in an implementation plan.

    line_index: 0-based index into the plan's rendered line array.
    Styled like GitHub PR review comments — attached to a specific section of the plan.
    """
    __tablename__ = "plan_inline_comments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id = Column(Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # 0-based line index in the plan markdown where this comment is anchored
    line_index = Column(Integer, nullable=False)

    author_id = Column(String(100), nullable=False)   # "human" or agent_id
    author_name = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)

    # Whether the agent has resolved/addressed this comment
    resolved = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    cron_expression = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    
    is_active = Column(Boolean, default=True, nullable=False)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(100), nullable=False, index=True) # ID from auth token (sub)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50), default="info") # e.g. "info", "success", "error", "warning"
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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

    # Stored as Integer/Numeric for proper SQL aggregation (SUM, AVG, GROUP BY).
    # Previously stored as String which prevented cost analytics queries.
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    estimated_cost_usd = Column(Numeric(12, 8), nullable=True)  # e.g. 0.00240000

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Uuid, ForeignKey("agents.id", ondelete="SET NULL"), nullable=True)
    
    server_name = Column(String(255), nullable=False)
    command = Column(String(255), nullable=False)
    args = Column(JSON, nullable=False, default=list)
    env_vars = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FileBackup(Base):
    """
    Stores a snapshot of a file's state BEFORE an agent modifies it.
    Uses an append-only, copy-on-write file backup strategy.
    
    - `backup_file_name = None`  → file did not exist before; rollback should unlink/delete the file.
    - `backup_file_name = str`   → SHA-256 hash filename in `~/.carole/workspaces/{project_slug}/.carole/{team_slug}/file-history/`. Rollback should copy this over the live file.
    - `operation`                → 'write' or 'edit', for debugging/auditing.
    """
    __tablename__ = "file_backups"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)

    # The chat message that triggered this file change (optional)
    message_id = Column(Uuid, ForeignKey("messages.id", ondelete="CASCADE"), nullable=True)

    # Absolute path of the live file that was modified
    file_path = Column(Text, nullable=False)

    # Name of the backup file in the file-history directory. NULL means file did not exist.
    backup_file_name = Column(String(255), nullable=True)

    # Which tool created this backup: 'write_file' or 'edit_file'
    operation = Column(String(20), nullable=False, default="write_file")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Skill(Base):
    """
    Modular skill package that provides an agent with additional prompt instructions
    and specific tools/MCP servers to execute a particular workflow.
    """
    __tablename__ = "skills"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    system_prompt_addendum = Column(Text, nullable=True)
    
    # List of tool names (e.g., built-in tools or plugin tools)
    tools = Column(JSON, nullable=True, default=list)
    # List of associated MCP server config IDs or names
    mcp_servers = Column(JSON, nullable=True, default=list)
    
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class EntityMemory(Base):
    """
    Explicit fact store for agents ("Remember that X = Y").
    Facts are injected into the system prompt as 'KNOWN FACTS'.
    """
    __tablename__ = "entity_memories"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    # Scope: can be bound to a team, or broadly to a project
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    
    # Fact key (e.g. 'user_preference', 'repo_linter')
    key = Column(String(255), nullable=False)
    # Fact value (e.g. 'Prefers TypeScript over JS')
    value = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GraphTriple(Base):
    """
    Knowledge Graph Triples (Subject -> Predicate -> Object) for Multi-Hop GraphRAG.
    Example:
    Subject: 'ChatInterface' | Predicate: 'renders' | Object: 'BrowserView'
    Subject: 'BrowserView'   | Predicate: 'connects_to' | Object: 'browser_routes.py'
    """
    __tablename__ = "graph_triples"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id = Column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)

    subject = Column(String(255), nullable=False, index=True)
    predicate = Column(String(255), nullable=False, index=True)
    object_val = Column(Text, nullable=False)
    confidence_score = Column(Float, default=1.0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CompactionEvent(Base):
    """
    Records when context compaction occurred for a team conversation.

    Each row represents one compaction checkpoint:
    - summary: LLM-generated dense summary of everything before this point
    - triggered_by: "auto" (token threshold hit) | "manual" (user invoked /compact)
    - message_count_before: how many messages existed when compaction was triggered

    The history loader uses the most recent CompactionEvent as a starting checkpoint:
    it loads the summary as a synthetic first message, then only loads real messages
    AFTER this event's created_at — making compaction persist across server restarts.
    """
    __tablename__ = "compaction_events"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    team_id = Column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)

    # LLM-generated dense summary of all conversation content before this checkpoint
    summary = Column(Text, nullable=False)

    # How many total messages existed in the team when compaction fired
    message_count_before = Column(Integer, nullable=True)

    # "auto" = token threshold triggered it | "manual" = user invoked /compact command
    triggered_by = Column(String(20), nullable=False, default="auto")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

