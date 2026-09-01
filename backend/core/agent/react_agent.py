"""
# backend/core/agent/react_agent.py

Core ReACT (Reasoning and Acting) loop for Worker and Coordinator agents.

Key features:
1. Thought-Action-Observation loop with streaming.
2. Loads recent conversation history from DB for context continuity.
3. Confidence-based research with web search fallback.
4. Retry/backoff for LLM API errors.
5. Working memory persistence.
"""

import uuid
import json
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import llm_router
from core.chat.event_bus import event_bus
from core.memory.models import Message, Agent, Project, User, EntityMemory, CompactionEvent
from core.tools.tool_registry import ToolRegistry
from core.tools.context import CancellationToken, ToolExecutionContext, ToolPermissionContext
from core.memory.lancedb_client import lancedb_client
import core.config
from core.config import (
    STRICT_REASONING_GUIDELINES, COMPACTION_SYSTEM_PROMPT, COMPACTION_USER_PROMPT,
)

logger = logging.getLogger("carole.react_agent")


from dataclasses import dataclass

@dataclass
class ASTNode:
    original_message: Dict[str, Any]

@dataclass
class ThoughtNode(ASTNode):
    pass

@dataclass
class ActionNode(ASTNode):
    pass

@dataclass
class ObservationNode(ASTNode):
    pass

@dataclass
class ErrorNode(ASTNode):
    pass

class ReACTAgent:
    def __init__(
        self, agent_id: str, team_id: str, project_id: str,
        name: str, role: str, model: str, system_prompt: str,
        parent_coordinator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        fallback_model: Optional[str] = None,
        reasoning_effort: str = "none",
        parent_message_id: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.team_id = team_id
        self.project_id = project_id
        self.name = name
        self.role = role
        self.model = model
        self.fallback_model = fallback_model
        self.reasoning_effort = reasoning_effort
        self.system_prompt = system_prompt
        self.topic = f"team:{self.team_id}"
        self.parent_coordinator_id = parent_coordinator_id
        self.task_id = task_id
        self.parent_message_id = parent_message_id
        # Tracks the DB id of the current response message (for file snapshotting)
        self.active_message_id: str | None = None
        self._worker_results: List[Dict[str, Any]] = []
        self._notification_queue: asyncio.Queue = asyncio.Queue()
        self._listening = False
        self._log = logger.getChild(self.name)
        # Strong reference to the background cancel-cleanup task so it isn't
        # garbage-collected mid-run (asyncio only holds weak refs to tasks).
        self._pending_cleanup: Optional[asyncio.Task] = None

        # --- Session-level caches (cleared at start of each run_loop call) ---
        # Cached assembled system prompt — rebuilt once per session, not per loop.
        self._cached_system_prompt: Optional[str] = None
        # Last observation text for no-progress detection.
        self._last_observation: str = ""
        self._no_progress_count: int = 0
        self._consecutive_tool_errors: int = 0

    async def _load_conversation_history(self, db_session: AsyncSession, limit: int = 20, exclude_msg_id: Optional[str] = None) -> List[Dict[str, str]]:
        """Loads recent team messages from the DB to give the agent conversation context.

        Compaction-Aware Loading:
        Checks for the most recent CompactionEvent for this team. If one exists,
        only messages AFTER the compaction timestamp are loaded — the compaction
        summary is prepended as a synthetic first message. This makes rolling
        compaction persist across server restarts (previously, in-memory compaction
        was discarded on each new run and the full verbose history was reloaded).
        """
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id

        # --- Check for the most recent compaction checkpoint ---
        compaction_summary_msg = None
        compaction_after_dt = None
        try:
            cp_stmt = (
                select(CompactionEvent)
                .where(CompactionEvent.team_id == team_uuid)
                .order_by(CompactionEvent.created_at.desc())
                .limit(1)
            )
            cp_result = await db_session.execute(cp_stmt)
            last_compaction = cp_result.scalar_one_or_none()
            if last_compaction:
                compaction_after_dt = last_compaction.created_at
                compaction_summary_msg = {
                    "role": "user",
                    "content": (
                        f"[COMPACTED HISTORY — Context from before {last_compaction.created_at.strftime('%Y-%m-%d %H:%M UTC')}]\n"
                        f"{last_compaction.summary}\n"
                        f"[/COMPACTED HISTORY]"
                    )
                }
                self._log.info(
                    "Compaction checkpoint found (created %s). Loading only post-compaction messages.",
                    last_compaction.created_at.isoformat()
                )
        except Exception as cp_err:
            self._log.warning("Could not check CompactionEvent table: %s", cp_err)

        stmt = (
            select(Message)
            .where(Message.team_id == team_uuid)
            .where(
                or_(
                    Message.is_private == False,
                    Message.recipient_id == self.agent_id,
                    Message.sender_id == self.agent_id
                )
            )
            .where(Message.sender_id != "system")
            # CRITICAL: Exclude intermediate tool-trace rows.
            # is_intermediate=True rows (tool call traces, system corrections)
            # are UI-only scratch data. Loading them back into LLM context
            # causes 60-80% token bloat with no benefit — the agent already
            # consumed and acted on those results in the same run they were created.
            .where(Message.is_intermediate == False)
        )
        # If there's a compaction checkpoint, only load messages after it
        if compaction_after_dt is not None:
            stmt = stmt.where(Message.created_at > compaction_after_dt)

        if exclude_msg_id:
            try:
                ex_uuid = uuid.UUID(exclude_msg_id) if isinstance(exclude_msg_id, str) else exclude_msg_id
                stmt = stmt.where(Message.id != ex_uuid)
            except Exception:
                pass
        stmt = (
            stmt.order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await db_session.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        history = []
        # Prepend the compaction summary as the first message so the LLM
        # has context for everything that came before the checkpoint.
        if compaction_summary_msg:
            history.append(compaction_summary_msg)

        for msg in messages:
            is_self = msg.sender_id == self.agent_id

            content_list = []

            if is_self:
                content_list.append({"type": "text", "text": msg.text})
            else:
                if msg.sender_id == "human":
                    sender_label = msg.sender_name or "Human User"
                    content_list.append({"type": "text", "text": f"[{sender_label} (User)]: {msg.text}"})
                else:
                    sender_label = msg.sender_name or msg.sender_id
                    content_list.append({"type": "text", "text": f"[{sender_label} (Teammate)]: {msg.text}"})

            if msg.attachments:
                for att in msg.attachments:
                    if att.get("type", "").startswith("image/"):
                        content_list.append({
                            "type": "image",
                            "local_path": att.get("local_path"),
                            "mime_type": att.get("type")
                        })

            final_content = content_list[0]["text"] if len(content_list) == 1 else content_list

            history.append({
                "role": "assistant" if is_self else "user",
                "content": final_content
            })
        return history

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """Assembles system prompt with learnings, tools, team roster, and reasoning guidelines.

        SESSION-CACHED: The assembled prompt is cached on the instance after the
        first call and reused for all subsequent loops in the same session.
        This avoids repeated DB queries + LanceDB embedding searches on every loop.
        Call _invalidate_system_prompt_cache() to force a rebuild (e.g. after
        receiving new worker results that should be visible in context).

        Optimized: fetches Agent roster, Project, User, and Team in a single
        pass using joined selects instead of 3 sequential round-trips.
        """
        if self._cached_system_prompt is not None:
            return self._cached_system_prompt
        capabilities_block = "\n====\nCAPABILITIES & MEMORY\n====\n"

        # Single query: fetch all agents for the team
        team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
        stmt = select(Agent).where(Agent.team_id == team_uuid)
        roster_result = await db_session.execute(stmt)
        teammates = roster_result.scalars().all()

        roster_block = ""
        has_teammates = any(str(t.id) != self.agent_id for t in teammates)
        if has_teammates:
            roster_block = "TEAM ROSTER:\n"
            for teammate in teammates:
                if str(teammate.id) != self.agent_id:
                    roster_block += f"- {teammate.name} (Role: {teammate.role})\n"
            roster_block += "\n"
        capabilities_block += roster_block

        # Joined query: Project → User in two selects (still avoids a 3rd round-trip
        # by using project_id resolved from the agent's own team record)
        human_context = ""
        if self.project_id:
            try:
                proj_uuid = uuid.UUID(str(self.project_id))
                project_result = await db_session.execute(
                    select(Project, User)
                    .join(User, User.id == Project.owner_id)
                    .where(Project.id == proj_uuid)
                )
                row = project_result.first()
                if row:
                    _project, user = row
                    first = user.first_name or ""
                    last = user.last_name or ""
                    full_name = f"{first} {last}".strip() or "User"
                    human_context = (
                        f"HUMAN CONTEXT:\n"
                        f"- The human user / project owner is {full_name}.\n"
                        f"- In chat history, messages from the human user are labeled '[{full_name} (User)]'.\n"
                        f"- Messages from other AI teammates are labeled '[AgentName (Teammate)]'.\n"
                        f"- Always distinguish between what the human user asked vs what AI teammates said.\n\n"
                    )
            except Exception:
                pass
        capabilities_block += human_context

        # 1. Generate search embeddings
        query_vector = await llm_router.generate_embeddings(current_task)

        # 2. Search LanceDB for semantic memory
        past_learnings = await lancedb_client.search_learnings(
            vector=query_vector,
            project_id=self.project_id,
            team_id=self.team_id,
            limit=getattr(core.config, "MEMORY_RETRIEVAL_LIMIT", 3)
        )

        # 3. Format past learnings
        learnings_block = ""
        if past_learnings:
            learnings_block = "LESSONS LEARNED (Apply these rules to your current task):\n"
            for learning in past_learnings:
                # learning.get('lesson_rule') already contains [CATEGORY] prefix from auto_dream
                learnings_block += f"- Context: {learning.get('task_summary')}\n  Directive: {learning.get('lesson_rule')}\n"
            learnings_block += "\n"
            
        # 3.5 Format Entity Facts
        fact_stmt = select(EntityMemory).where(
            or_(
                EntityMemory.team_id == None,
                EntityMemory.team_id == team_uuid
            )
        )
        fact_result = await db_session.execute(fact_stmt)
        entity_facts = fact_result.scalars().all()
        if entity_facts:
            learnings_block += "ENTITY FACTS (Explicit details you must know):\n"
            for fact in entity_facts:
                learnings_block += f"- {fact.key}: {fact.value}\n"
            learnings_block += "\n"

        capabilities_block += learnings_block

        # 4. Dynamic Skills (Injected before tools so LLM reads skill context first)
        from core.skills.skill_manager import SkillManager
        active_skills = await SkillManager.get_team_skills(db_session, str(self.team_id), active_only=True)
        skill_addendums = ""
        for skill in active_skills:
            if skill.system_prompt_addendum:
                skill_addendums += f"\n[SKILL: {skill.name}]\n{skill.system_prompt_addendum}\n"
            if skill.tools:
                skill_addendums += f"Skill specific tools allowed: {', '.join(skill.tools)}\n"
            if skill.mcp_servers:
                skill_addendums += f"Skill MCP servers available: {', '.join(skill.mcp_servers)}\n"
                
        if skill_addendums:
            capabilities_block += f"\nACTIVE SKILLS:\n{skill_addendums}\n"

        # 5. Tool list
        tools_block = "AVAILABLE TOOLS:\n" + ToolRegistry.to_llm_prompt(team_id=str(self.team_id), agent_id=str(self.agent_id)) + "\n\n"
        capabilities_block += tools_block

        # 5. Worker reports
        worker_results_block = ""
        if self._worker_results:
            worker_results_block = "WORKER REPORTS:\n"
            for wr in self._worker_results:
                worker_results_block += (
                    f"- Agent: {wr.get('agent', 'unknown')}, Task: {wr.get('task_id', 'unknown')}, "
                    f"Status: {wr.get('status', 'unknown')}\n"
                    f"  Result: {wr.get('result', 'No result')[:500]}\n"
                )
            worker_results_block += "\n"
        capabilities_block += worker_results_block

        # Environment awareness — agents know the OS they are running on
        import platform
        os_name = platform.system()
        os_release = platform.release()
        env_block = (
            f"CURRENT ENVIRONMENT: You are running on {os_name} {os_release}.\n"
            f"When using shell tools, ensure your commands are compatible with {os_name} (e.g., use PowerShell/cmd syntax on Windows).\n\n"
        )
        
        # Temporal awareness — agents always know the current date/time
        now = datetime.now(timezone.utc)
        temporal_block = (
            f"CURRENT DATE/TIME: {now.strftime('%A, %B %d, %Y %H:%M UTC')}\n"
            f"(Timezone: UTC — adjust to user's local time if mentioned)\n\n"
        )
        capabilities_block = env_block + temporal_block + capabilities_block

        # ── Editable prompt blocks (configurable in Settings → Prompt Blocks) ──
        from core.agent.prompt_blocks import get_block

        # Scratchpad awareness
        _scratchpad = get_block("scratchpads")
        if _scratchpad:
            capabilities_block += _scratchpad

        # Documentation file awareness
        _docs = get_block("docs")
        if _docs:
            capabilities_block += _docs

        # Workspace temp-file path — compute the actual runtime path, then inject
        from core.config import CAROLE_HOME_DIR
        _project_slug = str(self.project_id)[:8] if self.project_id else "workspace"
        _team_slug = str(self.team_id)[:8] if self.team_id else "team"
        try:
            import re as _re
            if row:
                _proj_obj, _ = row
                _project_slug = _re.sub(r'[^a-zA-Z0-9_-]+', '-', _proj_obj.name).strip('-') or _project_slug
            
            from core.memory.models import Team as _TeamModel
            _team_obj = (await db_session.execute(select(_TeamModel).where(_TeamModel.id == team_uuid))).scalar_one_or_none()
            if _team_obj:
                _team_slug = _re.sub(r'[^a-zA-Z0-9_-]+', '-', _team_obj.name).strip('-') or _team_slug
        except Exception:
            pass
        _carole_dir = str(CAROLE_HOME_DIR / "workspaces" / _project_slug / ".carole" / _team_slug)
        import pathlib as _pl
        _pl.Path(_carole_dir).mkdir(parents=True, exist_ok=True)
        _workspace = get_block("workspace_paths", carole_dir=_carole_dir)
        if _workspace:
            capabilities_block += _workspace

        # Scheduler awareness
        _scheduler = get_block("scheduler")
        if _scheduler:
            capabilities_block += _scheduler

        # Browser automation — 3-Tier architecture
        _browser = get_block("browser")
        if _browser:
            capabilities_block += _browser


        # Reasoning guidelines & Output Efficiency
        identity_rule = f"\n\nCRITICAL IDENTITY RULE: You are {self.name} ({self.role}). You MUST speak in the first person ('I', 'me'). NEVER refer to {self.name} in the third person. NEVER pretend to be someone else."
        output_efficiency = getattr(core.config, "OUTPUT_EFFICIENCY_PROMPT", "")
        
        assembled = f"{self.system_prompt}{identity_rule}\n\n{output_efficiency}\n\n{capabilities_block}"
        self._cached_system_prompt = assembled
        return assembled

    def _invalidate_system_prompt_cache(self) -> None:
        """Force a rebuild of the cached system prompt on the next loop iteration.
        Call this when worker results arrive or team context changes."""
        self._cached_system_prompt = None

    async def run_loop(self, db_session: AsyncSession, initial_prompt: str, attachments: Optional[List[Dict]] = None, token: Optional["CancellationToken"] = None, trigger_message_id: Optional[str] = None):
        """Runs the core ReACT loop with conversation history and streaming."""
        if trigger_message_id:
            self.active_message_id = trigger_message_id
        
        self._listening = True
        listener_task = asyncio.create_task(self._listen_for_notifications())
        
        try:
            await self._run_loop_inner(db_session, initial_prompt, attachments, token, trigger_message_id=trigger_message_id)
        except asyncio.CancelledError:
            # User clicked "Stop Generating" — persist whatever was partially generated
            partial = getattr(self, "_current_thought_buffer", "").strip()
            reasoning = getattr(self, "_current_reasoning_buffer", None) or None
            
            async def _cleanup_cancelled_task():
                # We must use a new session because the task is cancelled,
                # and awaiting on the existing db_session might raise CancelledError.
                from core.memory.database import async_session
                async with async_session() as cleanup_db:
                    stop_note = "\n\n*[Generation stopped by user]*"
                    final_text = (partial + stop_note) if partial else stop_note.strip()
        
                    try:
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=final_text,
                            reasoning_text=reasoning,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        cleanup_db.add(db_msg)
                        await cleanup_db.commit()
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": final_text,
                            "is_private": self.is_private_response,
                            "recipient_id": self.reply_recipient_id,
                            "has_reasoning": bool(reasoning),
                        })
                    except Exception as persist_err:
                        self._log.warning("Could not persist partial message after cancel: %s", persist_err)
        
                    # Signal idle so the UI clears the typing indicator
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                    
            # Launch cleanup as a background task so it isn't aborted by the current task's cancellation
            self._pending_cleanup = asyncio.create_task(_cleanup_cancelled_task())
            self._log.info("Agent %s stopped by user request.", self.name)
            raise  # re-raise so asyncio.Task knows it was cancelled
        finally:
            self._listening = False
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass

    def _get_compaction_config(self) -> dict:
        """Load compaction settings from the user's config.json with model-aware defaults."""
        from core.llm.config_manager import load_config
        from core.llm.multi_model_router import get_model_context_window
        cfg = load_config()
        model_ctx = get_model_context_window(self.model)
        defaults = {
            "max_observation_chars": 2000 if model_ctx <= 16384 else 4000,
            "token_trigger_ratio": 0.65 if model_ctx <= 16384 else 0.80,
            "context_window_size": model_ctx,
            "recent_messages_to_keep": 4 if model_ctx <= 16384 else 8,
        }
        user_compaction = cfg.get("compaction", {})
        return {**defaults, **user_compaction}

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Stage 3 helper: Role-aware token estimation.

        Uses content-type heuristics for better accuracy than a flat chars/4:
        - System prompt / tool list (dense structured text): chars / 3.5
        - Tool observation blocks (JSON / code output):       chars / 3.0
        - Regular prose (user/assistant dialogue):            chars / 4.0
        - Compacted history blocks:                           chars / 3.5

        These ratios approximate real tokenizer output within ~10-15% for the
        models we use (Claude, GPT-4o, Gemini). We also add a 5% overhead buffer
        for message role/formatting tokens that aren't in the content field.
        """
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                # Multi-part content (text + image blocks)
                text_parts = " ".join(
                    p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
                )
                total += len(text_parts) // 4
            else:
                content_str = str(content)
                if "[OBSERVATION]" in content_str or "```" in content_str:
                    # Dense JSON/code content
                    total += len(content_str) // 3
                elif "[COMPACTED HISTORY" in content_str:
                    # Structured summary block
                    total += len(content_str) // 3
                else:
                    # Regular prose
                    total += len(content_str) // 4
        # 5% overhead for role/formatting tokens
        return int(total * 1.05)

    @staticmethod
    def _truncate_observation(content: str, max_chars: int) -> str:
        """Truncate an [OBSERVATION] block's inner text, keeping head + tail."""
        def _truncate_match(m):
            inner = m.group(1)
            if len(inner) > max_chars:
                half = max_chars // 2
                dropped = len(inner) - max_chars
                return f"[OBSERVATION]{inner[:half]}\n...[{dropped} chars truncated]...\n{inner[-half:]}[/OBSERVATION]"
            return m.group(0)
        return re.sub(r'\[OBSERVATION\](.*?)\[/OBSERVATION\]', _truncate_match, content, flags=re.DOTALL)

    def _micro_compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stage 1: Strip media, truncate oversized tool outputs, and micro-compact older historical tool results."""
        cc = self._get_compaction_config()
        max_chars = cc["max_observation_chars"]
        num_msgs = len(messages)

        new_msgs = []
        for idx, msg in enumerate(messages):
            content = msg.get("content", "")
            if msg.get("role") != "user" or not isinstance(content, str):
                new_msgs.append(msg)
                continue

            changed = False

            # Strip base64 image payloads
            if "data:image" in content:
                content = re.sub(r'data:image/[^;]+;base64,[a-zA-Z0-9+/=]+', '[IMAGE_STRIPPED]', content)
                changed = True

            # Historical tool result micro-compaction: for turns older than the 2 most recent turns (> 4 messages ago),
            # aggressively condense bulky tool outputs (> 300 chars) into concise summary tags to save tokens.
            is_historical = (num_msgs - idx) > 4
            if is_historical and "[OBSERVATION]" in content and len(content) > 300:
                def _condense_historical(m):
                    inner = m.group(1).strip()
                    lines = inner.splitlines()
                    first_line = lines[0][:100] if lines else "Result"
                    line_count = len(lines)
                    char_count = len(inner)
                    return f"[OBSERVATION]{first_line} ...[{line_count} lines / {char_count} chars compacted][/OBSERVATION]"
                condensed = re.sub(r'\[OBSERVATION\](.*?)\[/OBSERVATION\]', _condense_historical, content, flags=re.DOTALL)
                if condensed != content:
                    content = condensed
                    changed = True

            # Truncate large [OBSERVATION] blocks for recent messages
            if "[OBSERVATION]" in content and len(content) > max_chars:
                new_content = self._truncate_observation(content, max_chars)
                if new_content != content:
                    content = new_content
                    changed = True

            if changed:
                new_msg = dict(msg)
                new_msg["content"] = content
                new_msgs.append(new_msg)
            else:
                new_msgs.append(msg)

        return new_msgs

    def _parse_to_ast(self, messages: List[Dict[str, Any]]) -> List['ASTNode']:
        ast = []
        _ERROR_PATTERNS = (
            "Error — Missing Tool Call Tag",
            "Error — No [ACTION] tag found",
            "Error: Tool",
            "✗ Tool",
            "Unknown tool:",
            "CRITICAL ERROR — Code in Chat Detected",
            "CRITICAL ERROR — Plan Without Execution Detected"
        )
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            
            if role == "assistant":
                ast.append(ThoughtNode(msg))
                if isinstance(content, str) and "[ACTION]" in content and "[/ACTION]" in content:
                    ast.append(ActionNode(msg))
            elif role == "user":
                is_error = False
                if isinstance(content, str):
                    is_error = "[OBSERVATION]" in content and any(pat in content for pat in _ERROR_PATTERNS)
                if is_error:
                    ast.append(ErrorNode(msg))
                else:
                    ast.append(ObservationNode(msg))
            else:
                ast.append(ThoughtNode(msg))
                
        return ast

    def _snip_dead_ends(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stage 2: Remove failed tool call dead-ends from context.

        Uses the AST-level parser from core.agent.context_ast for precise,
        token-safe pruning. A dead-end is an assistant message with NO valid
        [ACTION] block immediately followed by a user message containing ONLY
        error observations. This correctly avoids snipping valid reasoning turns
        that happen to look similar to failed turns in naive text matching.
        """
        if len(messages) < 2:
            return messages

        from core.agent.context_ast import ast_snip_dead_ends
        pruned, snipped = ast_snip_dead_ends(messages)
        if snipped:
            self._log.info("_snip_dead_ends [AST]: removed %d dead-end pairs.", snipped)
        return pruned

    async def _rolling_compact(self, messages: List[Dict[str, Any]], db_session: Optional[AsyncSession] = None, triggered_by: str = "auto") -> List[Dict[str, Any]]:
        """Stage 4: Summarize the oldest messages, keeping the most recent N.

        After successful compaction:
        1. Persists a CompactionEvent to the DB so the checkpoint survives restarts.
        2. Emits a 'compaction_event' SSE so the UI renders a visible divider.
        """
        cc = self._get_compaction_config()
        keep_recent = cc["recent_messages_to_keep"]

        # Guard: not enough messages to compact
        if len(messages) <= keep_recent + 1:
            self._log.info("Rolling compact skipped — only %d messages, need > %d.", len(messages), keep_recent + 1)
            return messages

        to_compact = messages[1:-keep_recent]
        if not to_compact:
            return messages

        # High-Density Identifier Preservation Pass
        # Extract file paths and identifiers to pin at the top of the context
        extracted_paths = set()
        for msg in to_compact:
            content = str(msg.get("content", ""))
            # Extract paths from tool calls
            for m in re.finditer(r'[\'"]?(?:relative_path|path|filename)[\'"]?\s*[:=]\s*[\'"]([^\'"]+)[\'"]', content):
                extracted_paths.add(m.group(1))
            # Extract paths from markdown links
            for m in re.finditer(r'\[.*?\]\(file:([^\)]+)\)', content):
                extracted_paths.add(m.group(1))
            # Extract paths from code block headers
            for m in re.finditer(r'^\s*#\s+(?:backend|frontend|packages|src)/[a-zA-Z0-9_./-]+', content, re.MULTILINE):
                extracted_paths.add(m.group(0).strip('# \t'))

        pinned_block = ""
        if extracted_paths:
            pinned_block = "[PINNED CONTEXT: HIGH-DENSITY IDENTIFIERS]\n"
            pinned_block += "Active File Paths & References:\n"
            for p in sorted(extracted_paths):
                pinned_block += f"- {p}\n"
            pinned_block += "[/PINNED CONTEXT]\n\n"

        self._log.info("Rolling compaction: summarizing %d messages (keeping first + last %d).", len(to_compact), keep_recent)
        summary_prompt = COMPACTION_USER_PROMPT.format(context=json.dumps(to_compact, default=str))
        try:
            summary = await llm_router.generate_completion(
                model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                system_prompt=COMPACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,
                max_tokens=2000
            )
            full_summary = f"{pinned_block}{summary}" if pinned_block else summary
            compacted = (
                [messages[0]]
                + [{"role": "user", "content": f"[COMPACTED HISTORY]\n{full_summary}\n[/COMPACTED HISTORY]"}]
                + messages[-keep_recent:]
            )
            self._log.info("Rolling compaction complete. %d → %d messages.", len(messages), len(compacted))

            # --- Persist CompactionEvent to DB ---
            # This checkpoint makes compaction survive across server restarts.
            # On next load, _load_conversation_history reads this event and starts
            # from the summary instead of reloading the full verbose history.
            if db_session is not None:
                try:
                    team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
                    cp_event = CompactionEvent(
                        team_id=team_uuid,
                        summary=full_summary,
                        message_count_before=len(messages),
                        triggered_by=triggered_by,
                    )
                    db_session.add(cp_event)
                    await db_session.commit()
                    cp_event_id = str(cp_event.id)
                    self._log.info("Compaction checkpoint persisted (id=%s, triggered_by=%s).", cp_event_id, triggered_by)

                    # --- Emit SSE so the UI renders a visible compaction divider ---
                    await event_bus.publish(self.topic, {
                        "type": "compaction_event",
                        "id": cp_event_id,
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "triggered_by": triggered_by,
                        "message_count_before": len(messages),
                        "summary_preview": full_summary[:300] + "..." if len(full_summary) > 300 else full_summary,
                    })
                except Exception as persist_err:
                    self._log.warning("Could not persist CompactionEvent: %s", persist_err)

            return compacted
        except Exception as e:
            self._log.warning("Rolling compaction failed, continuing with full context: %s", e)
            return messages


    async def _run_loop_inner(self, db_session: AsyncSession, initial_prompt: str, attachments: Optional[List[Dict]] = None, token: Optional["CancellationToken"] = None, trigger_message_id: Optional[str] = None):
        # Reset all per-session caches at the start of each new run.
        # This ensures a fresh agent session doesn't carry stale state from a
        # previous invocation (e.g. if the agent object were somehow reused).
        self._cached_system_prompt = None
        self._last_observation = ""
        self._no_progress_count = 0
        self.is_private_response = False
        self.reply_recipient_id = None
        if trigger_message_id:
            self.active_message_id = trigger_message_id
            try:
                t_uuid = uuid.UUID(trigger_message_id) if isinstance(trigger_message_id, str) else trigger_message_id
                t_stmt = select(Message).where(Message.id == t_uuid)
                t_res = await db_session.execute(t_stmt)
                trigger_msg = t_res.scalar_one_or_none()
                if trigger_msg and trigger_msg.is_private:
                    self.is_private_response = True
                    self.reply_recipient_id = trigger_msg.sender_id
            except Exception as e:
                self._log.warning("Could not check trigger message privacy: %s", e)

        # Fetch agent config
        agent_uuid = uuid.UUID(self.agent_id) if isinstance(self.agent_id, str) else self.agent_id
        stmt = select(Agent).where(Agent.id == agent_uuid)
        res = await db_session.execute(stmt)
        db_agent = res.scalar_one_or_none()

        # Safety guard: if agent was deleted mid-run, deny all non-safe tool access
        if db_agent is None:
            self._log.warning(
                "Agent record not found in DB during run_loop — may have been deleted. "
                "Restricting all tools to safe-only mode."
            )
            permissions = {"__deny_non_safe__": True}
        else:
            permissions = db_agent.tool_permissions or {}

        system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)

        # Dynamic history limit: scale to model context window.
        # Larger-context models can use more history without risking truncation.
        _CONTEXT_WINDOW_LIMITS = {
            # Anthropic
            "claude-opus": 40, "claude-sonnet": 40, "claude-haiku": 30,
            # OpenAI
            "gpt-4o": 35, "gpt-4": 25, "gpt-3.5": 6, "o4-": 40, "o3-": 40,
            # Google
            "gemini-2.5": 60, "gemini-2.0": 50, "gemini-1.5": 50, "gemini-flash": 50,
            # Smaller open models
            "phi": 4, "llama-3.1-8b": 15, "8k": 4, "4k": 2,
        }
        history_limit = 15  # safe default
        model_lower = (self.model or "").lower()
        for prefix, limit in _CONTEXT_WINDOW_LIMITS.items():
            if prefix in model_lower:
                history_limit = limit
                break

        # Load conversation history for context continuity (excluding the current trigger message to prevent duplication)
        history = await self._load_conversation_history(db_session, limit=history_limit, exclude_msg_id=trigger_message_id)

        # Build messages: history + new prompt
        content = [{"type": "text", "text": initial_prompt}]
        if attachments:
            for att in attachments:
                if att.get("type", "").startswith("image/"):
                    content.append({
                        "type": "image",
                        "local_path": att.get("local_path"),
                        "mime_type": att.get("type")
                    })
                elif att.get("type") == "file_ref":
                    # An @file:path mention from the chat. Read the referenced
                    # file's contents *sandboxed to this agent's project* and
                    # inject them into context so the agent can reason about
                    # the file without a separate read_file tool call. The path
                    # is validated/sandboxed by file_tools._resolve_safe_path,
                    # so an agent can only pull in files from its own project
                    # workspace — never another project's, or anything outside.
                    ref_path = att.get("path") or att.get("relative_path")
                    if ref_path:
                        try:
                            from core.tools.file_tools import file_tools as _file_tools
                            file_content = await _file_tools.read_file(ref_path, self.project_id)
                            if file_content.startswith("Error"):
                                content.append({"type": "text", "text": f"\n\n[Referenced file '{ref_path}' could not be read: {file_content}]"})
                            else:
                                snippet = file_content if len(file_content) <= 8000 else file_content[:8000] + "\n...[truncated]"
                                content.append({"type": "text", "text": f"\n\n--- Referenced file: {ref_path} ---\n{snippet}\n--- end {ref_path} ---"})
                        except Exception as ref_err:
                            self._log.warning("file_ref read failed for %s: %s", ref_path, ref_err)
                            content.append({"type": "text", "text": f"\n\n[Referenced file '{ref_path}' unreadable: {ref_err}]"})
                else:
                    # Generic attachment (PDF, CSV, TXT, etc)
                    att_path = att.get("local_path")
                    att_name = att.get("name")
                    if att_path:
                        try:
                            from core.tools.file_tools import file_tools as _file_tools
                            from pathlib import Path
                            workspace_root = await _file_tools.get_workspace_root(self.project_id)
                            try:
                                rel_path = str(Path(att_path).relative_to(workspace_root)).replace("\\", "/")
                            except ValueError:
                                rel_path = att_path
                                
                            mime_type = att.get("type", "")
                            is_text = mime_type.startswith("text/") or mime_type in ["application/json", "application/javascript"]
                            
                            if is_text:
                                file_content = await _file_tools.read_file(rel_path, self.project_id)
                                if not file_content.startswith("Error"):
                                    snippet = file_content if len(file_content) <= 8000 else file_content[:8000] + "\n...[truncated]"
                                    content.append({"type": "text", "text": f"\n\n--- Attached file: {att_name} ({rel_path}) ---\n{snippet}\n--- end ---"})
                                else:
                                    content.append({"type": "text", "text": f"\n\n[User attached file '{att_name}'. Located at '{rel_path}'. Could not read contents automatically: {file_content}]"})
                            else:
                                content.append({"type": "text", "text": f"\n\n[User attached file '{att_name}'. Located at '{rel_path}'. Use the appropriate tool to read or analyze it if needed.]"})
                        except Exception as e:
                            self._log.warning("Failed to process attachment %s: %s", att_name, e)
                            content.append({"type": "text", "text": f"\n\n[User attached file '{att_name}']"})

        messages = history + [{"role": "user", "content": content if attachments else initial_prompt}]

        loop_count = 0
        max_loops = getattr(core.config, "MAX_LOOPS", 10)

        # Emit agent status: active
        await event_bus.publish(self.topic, {
            "type": "agent_status",
            "sender_id": self.agent_id,
            "sender_name": self.name,
            "role": self.role,
            "status": "active",
        })

        self._current_thought_buffer = ""
        self._current_reasoning_buffer = ""
        self._consecutive_tool_errors = 0
        action_call = None

        while loop_count < max_loops:
            loop_count += 1

            await event_bus.publish(self.topic, {
                "type": "typing",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking"
            })

            # STAGE 1 & 2: Micro-Compaction & Snipping
            messages = self._micro_compact(messages)
            messages = self._snip_dead_ends(messages)

            # STAGE 3: Token Budget Check & Rolling Compaction
            cc = self._get_compaction_config()
            window_size = cc["context_window_size"]
            trigger_ratio = cc["token_trigger_ratio"]
            trigger_tokens = window_size * trigger_ratio

            estimated_tokens = self._estimate_tokens(messages)
            
            # Broadcast real-time context token usage
            await event_bus.publish(self.topic, {
                "type": "context_usage",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "model": self.model,
                "estimated_tokens": estimated_tokens,
                "context_window": window_size,
                "usage_percent": round((estimated_tokens / window_size) * 100, 1) if window_size > 0 else 0,
                "loop_count": loop_count,
                "max_loops": max_loops,
            })
            
            if estimated_tokens > trigger_tokens:
                self._log.warning("Context window reached %.0f%% capacity (%d tokens). Triggering rolling compaction...", (estimated_tokens / window_size) * 100, estimated_tokens)
                messages = await self._rolling_compact(messages, db_session=db_session, triggered_by="auto")

            # Graceful Degradation Check — trigger 2 loops before max to give
            # the agent time to reflect AND execute the memory-save tool call.
            if loop_count == max_loops - 2:
                self._log.warning("Agent is approaching its loop limit (%d/%d). Injecting Graceful Degradation reflection prompt.", loop_count, max_loops)
                messages.append({
                    "role": "user",
                    "content": (
                        "[SYSTEM INSTRUCTION — GRACEFUL DEGRADATION]\n"
                        "You are running low on execution loops. You have 2 loops remaining.\n"
                        "STOP attempting your current approach. Do NOT retry the same failing action.\n\n"
                        "Produce a structured degradation report using this exact format:\n"
                        "<degradation-report>\n"
                        "  <what-was-attempted>One sentence describing the task and approach tried</what-was-attempted>\n"
                        "  <errors-encountered>Specific error messages or failure symptoms observed</errors-encountered>\n"
                        "  <partial-progress>Any files created, steps completed, or useful findings (or 'None')</partial-progress>\n"
                        "  <lesson>One actionable rule for next time — what to do differently</lesson>\n"
                        "  <user-message>A brief, honest explanation for the user of what happened and what they can try</user-message>\n"
                        "</degradation-report>\n\n"
                        "After producing the report, use write_scratchpad to persist the lesson to your personal pad."
                    )
                })

            # Stream completion with retry
            self._log.info("Thinking... (loop %d/%d)", loop_count, max_loops)

            # Emit explicit "thinking" status so the UI can show the indicator
            # before the first streamed chunk arrives.
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking",
            })

            thought_buffer = ""
            # Mirror buffers onto self so CancelledError handler can persist partial output
            # We save the reasoning trace accumulated so far (from previous loops) to restore it on retries
            saved_reasoning_buffer = self._current_reasoning_buffer
            had_error = False

            for attempt in range(3):
                try:
                    thought_buffer = ""
                    self._current_thought_buffer = ""
                    self._current_reasoning_buffer = saved_reasoning_buffer
                    
                    if attempt > 0:
                        await event_bus.publish(self.topic, {
                            "type": "thought_reset",
                            "sender_id": self.agent_id,
                        })

                    async for chunk in llm_router.generate_stream_with_reasoning(
                        model=self.model,
                        system_prompt=system_prompt,
                        messages=messages,
                        temperature=0.4,
                        project_id=self.project_id,
                        team_id=self.team_id,
                        agent_id=self.agent_id,
                        agent_name=self.name,
                        fallback_model=self.fallback_model,
                        reasoning_effort=self.reasoning_effort,
                    ):
                        content_chunk = chunk.get("content", "")
                        reasoning_chunk = chunk.get("reasoning", "")

                        if reasoning_chunk:
                            self._current_reasoning_buffer += reasoning_chunk
                            await event_bus.publish(self.topic, {
                                "type": "stream_reasoning",
                                "sender_id": self.agent_id,
                                "sender_name": self.name,
                                "role": self.role,
                                "chunk": reasoning_chunk,
                            })

                        if content_chunk:
                            thought_buffer += content_chunk
                            self._current_thought_buffer = thought_buffer
                            await event_bus.publish(self.topic, {
                                "type": "thought_delta",
                                "sender_id": self.agent_id,
                                "sender_name": self.name,
                                "role": self.role,
                                "delta": content_chunk
                            })
                    break  # Success
                except Exception as e:
                    from core.llm.multi_model_router import LLMProviderError
                    if isinstance(e, LLMProviderError):
                        had_error = True
                        error_msg = f"⚠️ {e.message}"
                        self._log.error("LLM Provider Error: %s", e.message)
                        
                        # Broadcast structured error event to trigger BYOK UI Warning Card
                        await event_bus.publish(self.topic, {
                            "type": "llm_error",
                            "sender_id": self.agent_id,
                            "error": e.to_dict()
                        })

                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=error_msg,
                            reasoning_text=self._current_reasoning_buffer or None,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        db_session.add(db_msg)
                        await db_session.commit()
                        break # Break retry loop on structural provider errors
                    
                    error_str = str(e).lower()
                    is_context_limit = ("413" in error_str or "too long" in error_str or "context_length" in error_str)
                    if is_context_limit:
                        # STAGE 5: Reactive Error Escalation — compact and break
                        # back to the outer while loop for a fresh retry set.
                        self._log.error("API hit context limit! Forcing emergency rolling compaction (attempt %d)." , attempt + 1)
                        messages = await self._rolling_compact(messages, db_session=db_session, triggered_by="emergency")
                        break  # break out of retry loop; outer while loop retries
                    if attempt < 2:
                            
                        wait = (2 ** attempt) * 2
                        self._log.warning("LLM error (attempt %d): %s. Retrying in %ds...", attempt + 1, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        had_error = True
                        error_msg = f"⚠️ LLM API error after 3 retries: {str(e)}"
                        self._log.error("LLM error after 3 retries: %s", e)
                        
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=error_msg,
                            reasoning_text=self._current_reasoning_buffer or None,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        db_session.add(db_msg)
                        await db_session.commit()

                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": error_msg,
                            "is_private": self.is_private_response,
                            "recipient_id": self.reply_recipient_id,
                            "has_reasoning": bool(self._current_reasoning_buffer)
                        })

            if had_error:
                # The post-loop max_loops block is skipped (loop_count < max_loops),
                # so we must publish idle here or the UI's typing indicator never clears.
                try:
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                except Exception:
                    pass
                break

            messages.append({"role": "assistant", "content": thought_buffer})

            # Strip any accidental "[Name]: " prefix the model may have
            # hallucinated at the start of its response.
            thought_buffer = re.sub(r'^\[[^\]]+\]:\s*', '', thought_buffer, count=1)

            action_call = self._parse_action(thought_buffer)
            if not action_call and self._current_reasoning_buffer:
                action_call = self._parse_action(self._current_reasoning_buffer)

            if not action_call:
                # ── Early-exit: agent explicitly signalled completion ──────────────
                # If the output ends with a "Status: COMPLETE" or "Status: BLOCKED"
                # sentinel (coordinator pattern), treat it as a genuine final answer
                # and break immediately — never inject a correction into a completed message.
                _completion_sentinels = ["status: complete", "status: blocked"]
                _lower_preview = thought_buffer.lower().strip()[-200:]
                if any(s in _lower_preview for s in _completion_sentinels):
                    self._log.info("Agent signalled completion (Status: COMPLETE/BLOCKED). Breaking loop cleanly.")
                    db_msg = Message(
                        team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                        sender_id=self.agent_id,
                        sender_name=self.name, text=thought_buffer,
                        reasoning_text=self._current_reasoning_buffer or None,
                        is_private=self.is_private_response,
                        recipient_id=self.reply_recipient_id,
                    )
                    db_session.add(db_msg)
                    await db_session.commit()
                    self.active_message_id = str(db_msg.id)
                    await event_bus.publish(self.topic, {
                        "type": "message",
                        "id": str(db_msg.id),
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "text": thought_buffer,
                        "is_private": self.is_private_response,
                        "recipient_id": self.reply_recipient_id,
                        "has_reasoning": bool(self._current_reasoning_buffer),
                    })
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                    break

                # Heuristic: does the CURRENT turn look like an unexecuted promise,
                # malformed tool call, or reasoning-only turn rather than a genuine final answer?
                _curr_text = (thought_buffer or "").strip()
                _lower = _curr_text.lower()
                action_promise_triggers = [
                    "[action", "[tool", "<tool", "tool_call", "function_call",
                    "writing the file", "writing to", "creating the file", "creating a file",
                    "i'll create", "i will create", "i'll write", "i will write",
                    "let me write", "let me create", "let me execute", "running the command",
                    "saving to", "creating file",
                    # Starting / Beginning / Task acceptance triggers
                    "let's start", "let's begin", "let's create", "let's write",
                    "let's execute", "let's run", "let's implement", "let's build",
                    "start by", "starting by", "starting with",
                    "i'll start by", "i will start by", "i'll begin by", "i will begin by",
                    "i'm going to create", "i will go ahead and create", "going to create",
                    "i'll go ahead and", "i will go ahead and",
                    "let me start", "let me begin",
                    "creating the", "creating a", "writing the", "writing a",
                    "executing the", "executing it", "running the",
                    # Step narration triggers — agent describing what it WILL do without doing it
                    "i'll now", "i will now", "i'll move on", "i'll work on", "i will work on",
                    "i'll get that set up", "i'll finalize", "i'll build",
                    "next, i'll", "next i'll", "now i'll", "now i will",
                    "i'll proceed", "first, i'll",
                    "let me handle", "let me proceed", "let me do this",
                    # Delegation-intent triggers — agent promising to delegate without calling the tool
                    "i'll hire", "i will hire", "i'll spawn", "i will spawn",
                    "i'll delegate", "i will delegate", "i'll assign", "i will assign",
                    "i'll use hire_subagent", "i'll use spawn_agent",
                    "hiring a", "spawning a", "delegating to",
                    "i'll kick off", "i will kick off",
                    "i'll send", "i will send a message",
                    # Retrieval & lookup intent triggers — model promising to fetch/check info without doing it
                    "let me retrieve", "i'll retrieve", "i will retrieve",
                    "let me check", "i'll check", "i will check",
                    "let me find", "i'll find", "i will find",
                    "let me look", "i'll look", "i will look",
                    "let me search", "i'll search", "i will search",
                    "let me get that", "let me get the",
                    # Conversational stalling phrases without tool action or answer
                    "just a moment", "one moment", "give me a moment", "hold on a moment",
                ]
                # Match explicit pseudo tool calls (e.g. read_file({...}) or execute_command("..."))
                # without [ACTION] tags
                has_pseudo_call = bool(re.search(r"\b[a-z]+(?:_[a-z]+)+\s*\(\s*\{", _curr_text))
                looks_like_tool_call = any(sig in _lower for sig in action_promise_triggers) or has_pseudo_call

                # Detect reasoning without content: model generated thoughts into reasoning but left content empty
                has_thought_without_action = not _curr_text and bool(self._current_reasoning_buffer)

                # Detect plan-only responses: model outputs a numbered plan/steps
                # list AND contains intent language but no ACTION tag was found.
                # Only trigger on the very first loop to avoid flagging long multi-step final answers.
                has_numbered_plan = bool(re.search(r"^\s*\d+[\.\)]\s+\S", _curr_text, re.MULTILINE)) and loop_count <= 1
                has_plan_header = any(p in _lower for p in ["plan:", "here's my plan", "here is my plan", "my plan is", "the plan is"]) and loop_count <= 1

                # Detect code-in-chat: model pastes ``` code blocks instead of using write_file.
                has_code_block = bool(re.search(r"```[\w\-]*\n[\s\S]{50,}", _curr_text))

                is_plan_without_action = (has_numbered_plan or has_plan_header)
                is_code_in_chat = has_code_block and loop_count <= max_loops - 1

                if (looks_like_tool_call or is_plan_without_action or is_code_in_chat or has_thought_without_action) and loop_count < max_loops - 1:
                    if has_thought_without_action:
                        correction = (
                            "[OBSERVATION] You have completed your reasoning. Now execute your planned tool action immediately using the required format:\n"
                            "  [ACTION]tool_name({\"param\": \"value\"})[/ACTION]\n"
                            "For example: [ACTION]write_file({\"relative_path\": \"hello_subagent.txt\", \"content\": \"Hello from subagent!\"})[/ACTION]\n"
                            "Execute your tool call NOW.[/OBSERVATION]"
                        )
                    elif is_code_in_chat and not looks_like_tool_call:
                        correction = (
                            "[OBSERVATION] CRITICAL ERROR — Code in Chat Detected.\n"
                            "You pasted a code block into chat instead of writing it to a file. This is strictly forbidden.\n"
                            "You MUST write code to disk using the tool. Exact format required:\n"
                            "  [ACTION]write_file({\"path\": \"backend/auth.py\", \"content\": \"# your code here\"})[/ACTION]\n"
                            "Execute write_file NOW with the code you just showed in chat.[/OBSERVATION]"
                        )
                    elif is_plan_without_action and not looks_like_tool_call:
                        correction = (
                            "[OBSERVATION] CRITICAL ERROR — Plan Without Execution Detected.\n"
                            "You described a plan but did not execute any of it. A plan is NOT progress.\n"
                            "You MUST immediately execute your first step using a tool call. Exact format:\n"
                            "  [ACTION]write_file({\"path\": \"index.html\", \"content\": \"<!DOCTYPE html>...\"})[/ACTION]\n"
                            "Start executing your first planned step RIGHT NOW. Do not stop until ALL steps are done.[/OBSERVATION]"
                        )
                    elif any(sig in _lower for sig in ["let me", "i'll", "i will", "let's", "working on it", "just a moment", "one moment"]):
                        correction = (
                            "[OBSERVATION] Incomplete Response / Unexecuted Promise.\n"
                            "You stated you would take an action or check something, but did not actually call a tool.\n"
                            "Saying you will do something is not doing it. You MUST immediately call the tool using:\n"
                            "  [ACTION]tool_name({\"param\": \"value\"})[/ACTION]\n"
                            "Otherwise, if you have finished all work, deliver your complete final answer to the user immediately.[/OBSERVATION]"
                        )
                    else:
                        # Check if it was a delegation promise specifically
                        _is_delegation_promise = any(
                            phrase in _lower for phrase in [
                                "i'll hire", "i will hire", "i'll spawn", "i will spawn",
                                "i'll delegate", "i will delegate", "hiring a", "spawning a",
                                "i'll kick off", "i will kick off",
                            ]
                        )
                        if _is_delegation_promise:
                            correction = (
                                "[OBSERVATION] CRITICAL ERROR — Delegation Promise Without Execution.\n"
                                "You said you would hire/spawn an agent but did NOT include the [ACTION] tag. Saying you will do something is NOT doing it.\n"
                                "You MUST immediately call the tool. Exact format required:\n"
                                "  [ACTION]hire_subagent({\"role\": \"Python Developer\", \"expertise\": \"file I/O\", \"task\": \"Create a file named hello.txt with content Hello\"})[/ACTION]\n"
                                "Or to spawn an existing teammate:\n"
                                "  [ACTION]spawn_agent({\"agent_name\": \"Nova\", \"task\": \"...\"})[/ACTION]\n"
                                "Execute the delegation tool call NOW.[/OBSERVATION]"
                            )
                        else:
                            correction = (
                                "[OBSERVATION] Error — Missing Tool Call Tag.\n"
                                "You indicated an action but did not include an [ACTION] tag. Use this exact format:\n"
                                "  [ACTION]tool_name({\"param\": \"value\"})[/ACTION]\n"
                                "For example: [ACTION]read_file({\"relative_path\": \"backend/main.py\"})[/ACTION]\n"
                                "Execute the tool call now.[/OBSERVATION]"
                            )
                    # FIX L2: Alternating-turn constraint.
                    # The messages list may end with a `user` message (the last observation).
                    # Injecting another `user` message back-to-back violates the
                    # strict alternating-turn requirement of Anthropic & Gemini APIs.
                    # Solution: prepend a minimal assistant acknowledgment stub so the
                    # sequence is always: ...user → assistant → user (correction).
                    last_role = messages[-1]["role"] if messages else "user"
                    if last_role == "user":
                        messages.append({
                            "role": "assistant",
                            "content": "[Acknowledged — executing correction]"
                        })
                    messages.append({"role": "user", "content": correction})
                    try:
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id="system",
                            sender_name="System",
                            text=correction,
                            is_intermediate=True,
                        )
                        db_session.add(db_msg)
                        await db_session.commit()
                    except Exception as corr_err:
                        self._log.warning("Could not persist correction observation: %s", corr_err)
                    continue


                # Agent is done — persist and broadcast
                self._log.info("Task finished after %d loops.", loop_count)
                
                # Differentiate subagent vs teammate
                is_temporary_subagent = self.name.startswith("Sub-")

                # If this agent was spawned by a coordinator, build the task notification
                coordinator_notification = None
                if self.parent_coordinator_id:
                    coordinator_notification = self._build_task_notification(thought_buffer, "completed")
                    # Only temporary subagents wrap their public chat message in XML report card
                    if is_temporary_subagent:
                        thought_buffer = coordinator_notification

                attachments_list = []
                if self.parent_message_id:
                    attachments_list.append({
                        "type": "parent_message",
                        "id": self.parent_message_id
                    })

                db_msg = Message(
                    team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                    sender_id=self.agent_id,
                    sender_name=self.name, text=thought_buffer,
                    reasoning_text=self._current_reasoning_buffer or None,
                    is_private=self.is_private_response,
                    recipient_id=self.reply_recipient_id,
                    attachments=attachments_list,
                )
                db_session.add(db_msg)
                await db_session.commit()
                # Track the persisted message id for future file snapshots in this loop
                self.active_message_id = str(db_msg.id)

                # Wake up the parent coordinator if present (using the XML block in the background)
                if self.parent_coordinator_id and coordinator_notification:
                    try:
                        from core.chat.message_router import message_router
                        # Look up parent coordinator details
                        stmt = select(Agent).where(Agent.id == uuid.UUID(self.parent_coordinator_id) if isinstance(self.parent_coordinator_id, str) else self.parent_coordinator_id)
                        res = await db_session.execute(stmt)
                        parent_agent = res.scalar_one_or_none()
                        if parent_agent:
                            # Route the task-notification text directly to the coordinator's queue
                            await message_router._enqueue_agent(
                                agent=parent_agent,
                                prompt_text=coordinator_notification,
                                db_session=db_session,
                                attachments=[],
                                trigger_message_id=str(db_msg.id)
                            )
                    except Exception as e:
                        self._log.exception("Failed to notify parent coordinator %s: %s", self.parent_coordinator_id, e)

                await event_bus.publish(self.topic, {
                    "type": "message",
                    "id": str(db_msg.id),
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": thought_buffer,
                    "is_private": self.is_private_response,
                    "recipient_id": self.reply_recipient_id,
                    "has_reasoning": bool(self._current_reasoning_buffer),
                    "is_task_notification": bool(self.parent_coordinator_id) if is_temporary_subagent else False,
                    "attachments": attachments_list,
                })

                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "idle",
                })
                break

            else:
                tool_name, tool_args = action_call
                self._log.info("Executing tool: %s", tool_name)

                # Move intermediate text to the reasoning trace.
                # Strip the raw [ACTION]...[/ACTION] block so the DB-persisted
                # reasoning_text only contains the agent's natural-language text
                # (e.g. "Let me write this now.") — the formatted 🛠️ block below
                # provides the structured tool call details. This way on refresh
                # the Thoughts panel looks identical to the live-streaming view.
                # NOTE: This non-greedy regex stops at the FIRST `[/ACTION]`.
                # If a tool argument's string value contains the literal
                # `[/ACTION]`, the strip truncates early. A proper fix requires
                # a state-machine parser (out of scope here).
                text_before_action = re.sub(r'\[ACTION\][\s\S]*?\[/ACTION\]', '', thought_buffer).strip()
                # Strip leftover empty markdown codeblocks if the model wrapped the ACTION tag
                text_before_action = re.sub(r'^\s*```[a-z]*\s*```\s*$', '', text_before_action, flags=re.MULTILINE).strip()

                if text_before_action:
                    self._current_reasoning_buffer += f"\n\n{text_before_action}\n"

                await event_bus.publish(self.topic, {
                    "type": "collapse_to_reasoning",
                    "sender_id": self.agent_id,
                })

                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "executing_tool",
                    "tool_name": tool_name,
                })

                await event_bus.publish(self.topic, {
                    "type": "tool_start",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "arguments": tool_args
                })

                try:
                    args_str = json.dumps(tool_args, indent=2)
                except Exception:
                    args_str = str(tool_args)
                self._current_reasoning_buffer += f"\n🛠️ **{tool_name}**\n```json\n{args_str}\n```\n"

                try:
                    observation = await self._execute_tool(
                        name=tool_name, args=tool_args, permissions=permissions, token=token
                    )
                except Exception as e:
                    observation = f"✗ Tool Error: {str(e)}"
                    self._log.error("Tool '%s' raised exception: %s", tool_name, e)

                await event_bus.publish(self.topic, {
                    "type": "tool_end",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "observation": observation[:500]
                })
                
                self._current_reasoning_buffer += f"\n📄 **Result:**\n```\n{observation[:1000]}\n```\n"

                # Broadcast the intermediate trace row (and persist to DB if spawned by a coordinator)
                # is_intermediate=True so the UI renders it as a compact trace row
                intermediate_trace = (
                    f"🛠️ **{tool_name}**\n"
                    f"```json\n{args_str}\n```\n"
                    f"📄 **Result:**\n```\n{observation[:500]}\n```"
                )
                
                db_trace_msg_id = None
                attachments_list = []
                if self.parent_coordinator_id:
                    try:
                        if self.parent_message_id:
                            attachments_list.append({
                                "type": "parent_message",
                                "id": self.parent_message_id
                            })
                        
                        db_trace_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=intermediate_trace,
                            is_intermediate=True,
                            attachments=attachments_list
                        )
                        db_session.add(db_trace_msg)
                        await db_session.commit()
                        db_trace_msg_id = str(db_trace_msg.id)
                    except Exception as persist_err:
                        self._log.warning("Failed to persist intermediate tool trace: %s", persist_err)

                await event_bus.publish(self.topic, {
                    "type": "tool_trace",
                    "id": db_trace_msg_id,
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": intermediate_trace,
                    "is_intermediate": True,
                    "attachments": attachments_list
                })
                # --- Error recovery & consecutive failure breaker ---
                is_error = observation.startswith("✗") or "Error:" in observation or "Error " in observation or "error:" in observation or "Exception:" in observation
                if is_error:
                    self._consecutive_tool_errors += 1
                else:
                    self._consecutive_tool_errors = 0

                # Inject lightweight hints for common error patterns
                if is_error:
                    hint = ""
                    obs_lower = observation.lower()
                    if "modulenotfounderror" in obs_lower or "importerror" in obs_lower:
                        hint = "\n\n💡 Hint: A Python module is missing. Try installing it with execute_command({\"command\": \"pip install <module_name>\"})."
                    elif "command not found" in obs_lower or "not recognized" in obs_lower:
                        hint = "\n\n💡 Hint: The command was not found. Check if the tool is installed, or use the full path."
                    elif "permission denied" in obs_lower:
                        hint = "\n\n💡 Hint: Permission denied. The file may be read-only or owned by another user."
                    elif "no such file or directory" in obs_lower or "filenotfounderror" in obs_lower:
                        hint = "\n\n💡 Hint: File or directory not found. Use list_directory to verify the path exists."
                    elif "target_content not found" in obs_lower or "no match found" in obs_lower:
                        hint = "\n\n💡 Hint: The target_content for edit_file didn't match. Use read_file to see the exact current content, then copy the exact text."
                    elif "timeout" in obs_lower and "browser" in tool_name.lower():
                        hint = "\n\n💡 Hint: Browser selector timed out. Call browser_get_interactive_elements to discover the correct selectors on the page."
                    elif "missing required parameter" in obs_lower and tool_name == "write_file":
                        hint = (
                            "\n\n💡 Hint: write_file requires TWO separate parameters — not a nested JSON value. "
                            "Exact format:\n"
                            "  [ACTION]write_file({\"relative_path\": \"path/to/file.py\", \"content\": \"# your code here\"})[/ACTION]\n"
                            "Do NOT wrap both inside a \"value\" key. Use relative_path and content as top-level keys."
                        )
                    if hint:
                        observation += hint

                    # Step-Back Mechanism: Inject breaker warning on 3+ consecutive failures
                    if self._consecutive_tool_errors >= 3:
                        observation += (
                            f"\n\n🛑 [SYSTEM WARNING: CONSECUTIVE FAILURE BREAKER]\n"
                            f"You have encountered {self._consecutive_tool_errors} consecutive tool failures. "
                            "STOP repeating the same action. "
                            "Step back, diagnose why this approach is failing, verify your assumptions (using read_file or checking logs), "
                            "and formulate a completely different strategy before executing another tool."
                        )

                # Check if the tool returned a structured binary file response
                is_file_obs = False
                try:
                    import json
                    obs_dict = json.loads(observation)
                    if isinstance(obs_dict, dict) and obs_dict.get("_is_file"):
                        is_file_obs = True
                        file_path = obs_dict.get("local_path")
                        mime = obs_dict.get("mime_type", "application/octet-stream")
                        source = obs_dict.get("source_url", "unknown source")
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"[OBSERVATION] Tool extracted a file from {source}:\nPath: {file_path}\nMIME: {mime}\n[/OBSERVATION]"},
                                {"type": "document", "local_path": file_path, "mime_type": mime}
                            ]
                        })
                except Exception:
                    pass

                if not is_file_obs:
                    observation_text = f"[OBSERVATION] Tool output:\n{observation}\n[/OBSERVATION]"
                    messages.append({
                        "role": "user",
                        "content": observation_text
                    })

                # --- No-progress guard ---
                # If the last 3 tool observations are identical, the agent is
                # stuck in a loop (e.g. calling the same broken tool repeatedly).
                # Break early with a diagnostic rather than burning all max_loops.
                import hashlib
                obs_fingerprint = hashlib.md5(observation.strip().encode()).hexdigest()
                if obs_fingerprint and obs_fingerprint == self._last_observation:
                    self._no_progress_count += 1
                    if self._no_progress_count >= 2:  # bail out after 2 identical results, not 3
                        self._log.warning(
                            "No-progress guard triggered after %d identical observations. Breaking loop.",
                            self._no_progress_count,
                        )
                        stuck_note = (
                            "\n\n*[System: Agent loop stopped — the last 3 tool calls returned identical results. "
                            "This usually means the tool is stuck or the target resource is unavailable. "
                            "Please review the tool output above and try a different approach.]*"
                        )
                        thought_buffer = (self._current_thought_buffer or "") + stuck_note
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=thought_buffer,
                            reasoning_text=self._current_reasoning_buffer or None,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        db_session.add(db_msg)
                        await db_session.commit()
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": thought_buffer,
                            "is_private": self.is_private_response,
                            "recipient_id": self.reply_recipient_id,
                            "has_reasoning": bool(self._current_reasoning_buffer),
                        })
                        await event_bus.publish(self.topic, {
                            "type": "agent_status",
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "status": "idle",
                        })
                        # ── SERVER-SIDE FAILSAFE: save lesson on stuck-loop too ──
                        await self._auto_save_failure_lesson(
                            initial_prompt=initial_prompt,
                            messages=messages,
                            reason="no-progress (3 identical observations)",
                        )
                        return
                else:
                    self._no_progress_count = 0
                self._last_observation = obs_fingerprint

                # If worker results arrived mid-loop, invalidate the cached system
                # prompt so they appear in context on the next assemble call.
                if self._worker_results:
                    self._invalidate_system_prompt_cache()

        # If we exited the loop by hitting max_loops, we still need to publish a final message
        if loop_count >= max_loops and action_call:
            self._log.warning("Agent hit max loop limit (%d). Terminating.", max_loops)
            final_note = f"\n\n*[System: Agent reached maximum loop limit of {max_loops}.]*"
            thought_buffer = self._current_thought_buffer + final_note
            
            db_msg = Message(
                team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                sender_id=self.agent_id,
                sender_name=self.name,
                text=thought_buffer,
                reasoning_text=self._current_reasoning_buffer or None,
                is_private=self.is_private_response,
                recipient_id=self.reply_recipient_id,
            )
            db_session.add(db_msg)
            await db_session.commit()
            
            await event_bus.publish(self.topic, {
                "type": "message",
                "id": str(db_msg.id),
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "text": thought_buffer,
                "is_private": self.is_private_response,
                "recipient_id": self.reply_recipient_id,
                "has_reasoning": bool(self._current_reasoning_buffer),
            })
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "idle",
            })

            # ── SERVER-SIDE FAILSAFE: Auto-extract and save a lesson ──
            # The graceful degradation prompt ASKS the LLM to save a lesson,
            # but it may ignore it. This block guarantees a lesson is ALWAYS
            # written when the agent hits max_loops, by using a cheap LLM call
            # to extract the lesson directly from the conversation context.
            await self._auto_save_failure_lesson(
                initial_prompt=initial_prompt,
                messages=messages,
                reason=f"max_loops ({max_loops})",
            )

    # ──────────────────────────────────────────────────────────────────────
    # Server-side Failsafe: Auto-extract & persist a lesson on termination
    # ──────────────────────────────────────────────────────────────────────

    async def _auto_save_failure_lesson(
        self,
        initial_prompt: str,
        messages: List[Dict[str, Any]],
        reason: str,
    ) -> None:
        """Extract a lesson from a failed/terminated agent run and save it to
        long-term memory (LanceDB + SQLite Learning table).

        This is a SERVER-SIDE failsafe — it doesn't rely on the LLM calling
        update_memory. It runs a cheap, fast LLM call to summarize the failure
        and directly writes the result into the vector store.
        """
        try:
            # Build a compact summary of the last few messages (tool calls & errors)
            recent = messages[-8:]  # last 8 messages should capture the failure pattern
            summary_lines = []
            for msg in recent:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        c.get("text", "") for c in content if isinstance(c, dict)
                    )
                # Truncate each message to keep token cost low
                if len(content) > 500:
                    content = content[:500] + "..."
                summary_lines.append(f"[{role}]: {content}")
            context_block = "\n".join(summary_lines)

            extraction_prompt = (
                "An AI agent was attempting the following task but got terminated due to: "
                f"{reason}.\n\n"
                f"Original user request: {initial_prompt[:300]}\n\n"
                f"Last conversation context:\n{context_block}\n\n"
                "Extract exactly ONE concise lesson the agent should remember for next time. "
                "Focus on: which approaches/selectors/tools FAILED and what the correct approach should be.\n\n"
                "Output format:\n"
                "TASK: <one-line summary of what the agent was trying to do>\n"
                "LESSON: <one-line actionable rule for next time>\n\n"
                "Output exactly NO_LESSON (nothing else) if ANY of these are true:\n"
                "- The failure was caused by an external factor (API downtime, rate limits, network errors, service unavailable)\n"
                "- The failure was caused by missing credentials or permissions the agent cannot control\n"
                "- The agent succeeded partially and the remaining work is straightforward\n"
                "- The conversation context shows no repeated mistake pattern\n"
                "Only extract a lesson if there is a clear, correctable agent behavior to encode."
            )

            extraction = await llm_router.generate_completion(
                model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                system_prompt=(
                    "You are a precise failure analysis engine for AI agent systems. "
                    "Your job is to extract ONE actionable lesson from a failed agent run. "
                    "Only output a lesson if the failure reflects a repeatable, correctable agent behavior. "
                    "Output NO_LESSON for external failures (API errors, rate limits, missing credentials). "
                    "Keep lessons concrete and tool-specific — not generic advice."
                ),
                messages=[{"role": "user", "content": extraction_prompt}],
                temperature=0.2,
                max_tokens=300,
            )

            if "NO_LESSON" in extraction:
                self._log.info("Auto-lesson extraction: no useful lesson found.")
                return

            # Parse TASK/LESSON lines
            task_summary = initial_prompt[:200]
            lesson_rule = extraction.strip()
            for line in extraction.strip().split("\n"):
                if line.startswith("TASK:"):
                    task_summary = line[5:].strip()
                elif line.startswith("LESSON:"):
                    lesson_rule = f"[FAILURE-LESSON] {line[7:].strip()}"

            # Generate embedding
            combined_text = f"{task_summary} | {lesson_rule}"
            embedding = await llm_router.generate_embeddings(combined_text)

            # Deduplication check — skip if a very similar lesson already exists
            existing = await lancedb_client.search_learnings(
                vector=embedding,
                project_id=self.project_id,
                team_id=self.team_id,
                limit=1,
            )
            if existing and existing[0].get("_distance", 1.0) < 0.15:
                self._log.info("Auto-lesson extraction: duplicate lesson already exists, skipping.")
                return

            # Save to SQLite
            from core.memory.database import async_session as _async_session
            from core.memory.models import Learning
            async with _async_session() as db:
                learning = Learning(
                    project_id=uuid.UUID(self.project_id) if isinstance(self.project_id, str) else self.project_id,
                    team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                    task_summary=task_summary,
                    lesson_rule=lesson_rule,
                )
                db.add(learning)
                await db.commit()

            # Save to LanceDB vector store
            await lancedb_client.insert_learning(
                project_id=str(self.project_id),
                team_id=str(self.team_id),
                task_summary=task_summary,
                lesson_rule=lesson_rule,
                vector=embedding,
            )

            self._log.info(
                "✓ Auto-saved failure lesson: '%s' → '%s'",
                task_summary[:60], lesson_rule[:80],
            )
        except Exception as e:
            # Never let lesson extraction crash the agent — it's best-effort
            self._log.warning("Auto-lesson extraction failed (non-fatal): %s", e)

    @staticmethod
    def _repair_json(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        s = s.strip()
        
        in_str = False
        escape = False
        stack = []
        out = []
        
        for c in s:
            if not in_str:
                if c == '"':
                    in_str = True
                    out.append(c)
                elif c in '{[':
                    stack.append(c)
                    out.append(c)
                elif c in '}]':
                    if stack:
                        stack.pop()
                    out.append(c)
                else:
                    out.append(c)
            else:
                if escape:
                    escape = False
                    out.append(c)
                elif c == '\\':
                    escape = True
                    out.append(c)
                elif c == '"':
                    in_str = False
                    out.append(c)
                elif c == '\n':
                    out.append('\\n')
                elif c == '\t':
                    out.append('\\t')
                else:
                    out.append(c)
                    
        if in_str:
            out.append('"')
        while stack:
            c = stack.pop()
            if c == '{': out.append('}')
            elif c == '[': out.append(']')
            
        return "".join(out)

    def _parse_action(self, text: str) -> Any:
        """Parses [ACTION]tool_name(args)[/ACTION] or untagged tool_name(args) even with nested docstrings.

        Extraction strategy:
        1. Find tool name (tagged with [ACTION] or untagged snake_case).
        2. If explicit closing tag exists, slice directly.
        3. Otherwise, use quote-aware (single, double, and triple quotes) balanced-paren walker.
        4. Parse arguments: JSON → AST literal_eval → AST kwargs → Specialized multiline extractor → Regex fallback.
        """
        # Locate the tag + tool name
        # 1. Tagged match: [ACTION]tool_name(...) or [TOOL]... or <tool_call>...
        tagged_match = re.search(
            r"(?:\[(?:ACTION|TOOL)\]|<tool_call>)\s*(\w+)\s*\(",
            text, re.DOTALL
        )
        if tagged_match:
            tool_name = tagged_match.group(1)
            scan_start = tagged_match.end()
        else:
            # 2. Untagged match: Only match genuine registered tool names
            # Strip code blocks to avoid false-matching tool call templates/examples
            clean_text = re.sub(r"```[\s\S]*?```", "", text)
            from core.tools.tool_registry import ToolRegistry
            registered_names = set(ToolRegistry.list_names())
            untagged_match = None
            for rname in registered_names:
                m = re.search(rf"\b({re.escape(rname)})\s*\(", clean_text)
                if m:
                    if untagged_match is None or m.start() < untagged_match.start():
                        untagged_match = m
            if not untagged_match:
                return None
            tool_name = untagged_match.group(1)
            # Find the match position in the original text to align indices for walking
            orig_match = re.search(rf"\b({re.escape(tool_name)})\s*\(", text)
            if not orig_match:
                return None
            scan_start = orig_match.end()


        # If explicit closing tag exists, slice directly
        closing_tag_match = re.search(r"\[/(?:ACTION|TOOL)\]|</tool_call>", text[scan_start:], re.DOTALL)
        if closing_tag_match:
            inside = text[scan_start:scan_start + closing_tag_match.start()].strip()
            if inside.endswith(")"):
                inside = inside[:-1].strip()
            raw_args = inside
        else:
            # Walk forward to find the balanced closing paren with triple-quote awareness
            depth = 1
            i = scan_start
            n = len(text)
            in_triple_double = False
            in_triple_single = False
            in_single = False
            in_double = False

            while i < n and depth > 0:
                if text[i:i+3] == '"""' and not in_single and not in_triple_single:
                    in_triple_double = not in_triple_double
                    i += 3
                    continue
                if text[i:i+3] == "'''" and not in_double and not in_triple_double:
                    in_triple_single = not in_triple_single
                    i += 3
                    continue

                ch = text[i]
                if ch == '\\' and (in_single or in_double or in_triple_single or in_triple_double):
                    i += 2
                    continue

                if not in_triple_double and not in_triple_single:
                    if ch == "'" and not in_double:
                        in_single = not in_single
                    elif ch == '"' and not in_single:
                        in_double = not in_double
                    elif not in_single and not in_double:
                        if ch in '([{':
                            depth += 1
                        elif ch in ')]}':
                            depth -= 1
                i += 1

            if depth == 0:
                raw_args = text[scan_start:i - 1].strip()
            else:
                raw_args = text[scan_start:].strip()
                raw_args = re.sub(r"\)\s*(?:\[/(?:ACTION|TOOL)\]|</tool_call>)?\s*$", "", raw_args).strip()

        if not raw_args:
            return tool_name, {}

        # 1. Try JSON with Grammar Repair
        try:
            repaired_args = ReACTAgent._repair_json(raw_args)
            arguments = json.loads(repaired_args)
            if isinstance(arguments, dict):
                return tool_name, arguments
        except (json.JSONDecodeError, ValueError):
            pass

        # 2. Try Python AST literal_eval (handles dict with multiline strings, booleans, numbers)
        try:
            import ast as _ast
            arguments = _ast.literal_eval(raw_args)
            if isinstance(arguments, dict):
                return tool_name, arguments
        except Exception:
            pass

        # 3. Try Python AST kwargs & positional args (e.g. key="value", or "arg1", "arg2")
        try:
            import ast as _ast
            tree = _ast.parse(f"_dummy({raw_args})", mode="eval")
            arguments = {}
            if hasattr(tree.body, "args") and tree.body.args:
                pos_vals = []
                for a in tree.body.args:
                    try:
                        pos_vals.append(_ast.literal_eval(a))
                    except Exception:
                        pass
                if pos_vals:
                    arguments["_positional_args"] = pos_vals
            for kw in getattr(tree.body, "keywords", []):  # type: ignore[attr-defined]
                arguments[kw.arg] = _ast.literal_eval(kw.value)
            if arguments:
                return tool_name, arguments
        except Exception:
            pass

        # 4. Fallback: Specialized regex extractor for write_file / edit_file with docstrings
        try:
            path_m = re.search(r'["\'](?:relative_path|path|filename|file)["\']\s*[:=]\s*["\']([^"\']+)["\']', raw_args)
            content_m = re.search(r'["\']content["\']\s*[:=]\s*(?:"""|\'\'\'|"|\')([\s\S]*?)(?:"""|\'\'\'|"|\')\s*\}?\s*$', raw_args)
            if not content_m:
                content_m = re.search(r'["\']content["\']\s*[:=]\s*(?:"""|\'\'\'|"|\')([\s\S]*)\s*\}?\s*$', raw_args)
            if path_m:
                rel_path = path_m.group(1)
                content_val = content_m.group(1) if content_m else ""
                content_val = re.sub(r'(?:"""|\'\'\'|"|\')\s*\}?\s*$', '', content_val)
                return tool_name, {"relative_path": rel_path, "content": content_val}
        except Exception:
            pass

        # 5. Regex-based key=value extractor — handles multiline string values
        try:
            arguments = {}
            pattern = re.compile(
                r"""(\w+)\s*=\s*(?:"""
                r""""((?:[^"\\]|\\.)*)"|"""   # double-quoted string
                r"""'((?:[^'\\]|\\.)*)'|"""   # single-quoted string
                r"""(\d+(?:\.\d+)?)|"""        # number
                r"""(True|False|None)"""       # bare keywords
                r""")""",
                re.DOTALL,
            )
            for m in pattern.finditer(raw_args):
                key = m.group(1)
                if m.group(2) is not None:
                    val: Any = m.group(2).replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n").replace("\\t", "\t")
                elif m.group(3) is not None:
                    val = m.group(3).replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n").replace("\\t", "\t")
                elif m.group(4) is not None:
                    raw_num = m.group(4)
                    val = float(raw_num) if "." in raw_num else int(raw_num)
                else:
                    bare = m.group(5)
                    val = {"True": True, "False": False, "None": None}[bare]
                arguments[key] = val
            if arguments:
                return tool_name, arguments
        except Exception:
            pass

        # 6. Last resort — hand the raw string to the wrapper as 'value'
        return tool_name, {"value": raw_args}

    def _build_task_notification(self, result_text: str, status: str) -> str:
        task_id = self.task_id or "unknown"
        result_summary = result_text[:1000] if len(result_text) > 1000 else result_text
        return (
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{self.name}</agent>\n"
            f"  <status>{status}</status>\n"
            f"  <result>{result_summary}</result>\n"
            f"</task-notification>"
        )

    async def _listen_for_notifications(self):
        """
        Background listener that subscribes to the team EventBus and
        collects <task-notification> messages from worker agents.
        """
        topic = f"team:{self.team_id}"
        queue = await event_bus.subscribe(topic)

        try:
            while self._listening:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=2.0)

                    # Check if this is a task-notification from a worker
                    if (
                        event.get("type") == "message"
                        and event.get("is_task_notification")
                        and event.get("sender_id") != self.agent_id
                    ):
                        text = event.get("text", "")
                        notifications = self.parse_task_notifications(text)
                        for notif in notifications:
                            notif["agent"] = event.get("sender_name", "unknown")
                            self._worker_results.append(notif)
                            self._log.info(
                                "Collected notification from %s: task_id=%s status=%s",
                                notif.get("agent", "?"),
                                notif.get("task_id", "?"),
                                notif.get("status", "?"),
                            )

                    queue.task_done()
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            await event_bus.unsubscribe(topic, queue)

    async def collect_pending_notifications(self, timeout: float = 30.0) -> List[Dict[str, str]]:
        """
        Waits up to `timeout` seconds for worker notifications to arrive.
        Returns a list of parsed notification dicts.
        Used when the agent explicitly needs to wait for worker results.
        """
        collected = []
        # FIX: Use asyncio.get_running_loop() — asyncio.get_event_loop() is
        # deprecated in Python 3.10+ and raises DeprecationWarning.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while loop.time() < deadline:
            if self._worker_results:
                # Drain all pending results
                collected.extend(self._worker_results)
                self._worker_results.clear()
                break
            await asyncio.sleep(1.0)

        return collected

    def parse_task_notifications(self, text: str) -> List[Dict[str, str]]:
        """Parses <task-notification> XML blocks from worker messages."""
        notifications = []
        pattern = r"<task-notification>(.*?)</task-notification>"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            notification = {}
            for field in ["task_id", "agent", "status", "result", "tokens_used"]:
                field_match = re.search(f"<{field}>(.*?)</{field}>", match, re.DOTALL)
                if field_match:
                    notification[field] = field_match.group(1).strip()
            if notification:
                notifications.append(notification)

        return notifications

    async def _execute_tool(self, name: str, args: Dict[str, Any], permissions: Dict[str, str], token: Optional[CancellationToken] = None) -> str:
        # Safety: if agent was deleted mid-run, deny all non-safe tools
        if permissions.get("__deny_non_safe__"):
            from core.tools.tool_registry import ToolRegistry
            spec = ToolRegistry.get(name)
            if spec and spec.permission_default != "safe":
                self._log.warning(
                    "Denying tool '%s' (permission=%s) — agent record was deleted.",
                    name, spec.permission_default
                )
                return f"✗ Tool '{name}' denied: agent record no longer exists in the database."

        async def emit_progress(msg: str):
            self._current_reasoning_buffer += f"⏳ {msg}\n"
            await event_bus.publish(self.topic, {
                "type": "tool_progress",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "tool_name": name,
                "progress": msg
            })

        exec_context = ToolExecutionContext(
            agent_id=self.agent_id,
            agent_name=self.name,
            team_id=self.team_id,
            cancellation_token=token or CancellationToken(),
            emit_progress=emit_progress,
            active_message_id=self.active_message_id
        )
        
        # Build permission context
        perm_context = ToolPermissionContext(
            always_allow=set(),
            always_deny=set()
        )
        # Assuming permissions dict could have always_allow/always_deny lists
        if "always_allow" in permissions:
            perm_context.always_allow = set(permissions["always_allow"]) # type: ignore
        if "always_deny" in permissions:
            perm_context.always_deny = set(permissions["always_deny"]) # type: ignore

        from core.tools.tool_executor import tool_executor
        return await tool_executor.execute(
            tool_name=name, arguments=args,
            agent_id=self.agent_id, agent_name=self.name,
            team_id=self.team_id, permissions=permissions,
            active_message_id=self.active_message_id,
            context=exec_context,
            permission_context=perm_context
        )
