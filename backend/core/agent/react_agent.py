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
import html
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import llm_router
from core.chat.event_bus import event_bus
from core.memory.models import Message, Agent, Project, User, EntityMemory, CompactionEvent, GraphTriple
from core.tools.tool_registry import ToolRegistry
from core.tools.context import CancellationToken, ToolExecutionContext, ToolPermissionContext
from core.memory.lancedb_client import lancedb_client
import core
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
        self._modified_files: set = set()

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
                # Use explicit coverage boundary if recorded, else fallback to created_at
                compaction_after_dt = getattr(last_compaction, "covered_through_timestamp", None) or last_compaction.created_at
                compaction_summary_msg = {
                    "role": "user",
                    "content": (
                        f"[COMPACTED HISTORY — Context from before {compaction_after_dt.strftime('%Y-%m-%d %H:%M UTC')}]\n"
                        f"{last_compaction.summary}\n"
                        f"[/COMPACTED HISTORY]"
                    )
                }
                self._log.info(
                    "Compaction checkpoint found (covered through %s). Loading only post-compaction messages.",
                    compaction_after_dt.isoformat()
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
        # If there's a compaction checkpoint, only load messages after its coverage boundary
        if compaction_after_dt is not None:
            stmt = stmt.where(Message.created_at > compaction_after_dt)

        if exclude_msg_id:
            try:
                ex_uuid = uuid.UUID(exclude_msg_id) if isinstance(exclude_msg_id, str) else exclude_msg_id
                stmt = stmt.where(Message.id != ex_uuid)
            except Exception as e:
                self._log.debug("Invalid exclude_msg_id format: %s", e)
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
                "content": final_content,
                "id": str(msg.id),
                "created_at": msg.created_at,
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
        row = None
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
            except Exception as e:
                self._log.debug("Could not resolve project owner context: %s", e)
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
            valid_learnings = []
            for l in past_learnings:
                dist = l.get("_distance")
                if dist is not None and dist > 0.65:
                    continue  # Discard weak vector matches
                valid_learnings.append(l)

            if valid_learnings:
                learnings_block = (
                    "PAST EXPERIENCES & GENERAL HEURISTICS (Reference only to avoid repeating past engineering or tool mistakes. "
                    "Do NOT adopt file names, function signatures, or task parameters from past experiences unless explicitly requested by the user):\n"
                )
                for learning in valid_learnings:
                    learnings_block += f"- Past Situation: {learning.get('task_summary')}\n  Heuristic: {learning.get('lesson_rule')}\n"
                learnings_block += "\n"
            
        # 3.5 Format Entity Facts (with hard limit to prevent unbounded context growth)
        proj_uuid = uuid.UUID(str(self.project_id)) if self.project_id else None
        fact_conditions = [
            or_(
                EntityMemory.team_id == None,
                EntityMemory.team_id == team_uuid,
            )
        ]
        if proj_uuid:
            fact_conditions.append(
                or_(
                    EntityMemory.project_id == proj_uuid,
                    EntityMemory.project_id == None,
                )
            )
        fact_stmt = select(EntityMemory).where(and_(*fact_conditions)).limit(getattr(core.config, "ENTITY_FACTS_LIMIT", 40))
        fact_result = await db_session.execute(fact_stmt)
        entity_facts = fact_result.scalars().all()
        if entity_facts:
            learnings_block += "ENTITY FACTS (Explicit details you must know):\n"
            for fact in entity_facts:
                learnings_block += f"- {fact.key}: {fact.value}\n"
            learnings_block += "\n"

        # 3.6 Format Knowledge Graph Triples (Multi-Hop GraphRAG)
        triple_stmt = select(GraphTriple).where(
            or_(GraphTriple.team_id == team_uuid, GraphTriple.team_id == None)
        ).limit(30)
        triple_result = await db_session.execute(triple_stmt)
        triples = triple_result.scalars().all()
        if triples:
            learnings_block += "KNOWLEDGE GRAPH RELATIONS (Subject-Predicate-Object Triples):\n"
            for t in triples:
                learnings_block += f"- ({t.subject}) --[{t.predicate}]--> ({t.object_val})\n"
            learnings_block += "\n"

        capabilities_block += learnings_block

        # 3.7 Structural Repo Map (PageRank Context Map - Aider Pattern)
        try:
            from core.knowledge.code_graph import code_graph
            repo_map = await code_graph.generate_repo_map(project_id=self.project_id, max_tokens=800)
            if repo_map:
                capabilities_block += f"REPOSITORY SYMBOL MAP (Top Ranked Interfaces):\n{repo_map}\n\n"
        except Exception as e:
            self._log.debug("Could not generate repo map: %s", e)

        # 4. Dynamic Skills (Antigravity & Claude SKILL.md Standard + DB Skills)
        from core.skills.skill_manager import SkillManager
        from core.tools.file_tools import file_tools
        workspace_root = None
        try:
            workspace_root = await file_tools.get_workspace_root(str(self.project_id))
        except Exception:
            pass
        all_skills = await SkillManager.discover_all_skills(
            workspace_root=workspace_root,
            team_id=str(self.team_id),
            db=db_session
        )
        skills_block = SkillManager.build_skills_prompt_block(all_skills)
        if skills_block:
            capabilities_block += f"\n{skills_block}\n\n"

        # 5. Tool list
        tools_block = "AVAILABLE TOOLS:\n" + ToolRegistry.to_llm_prompt(team_id=str(self.team_id), agent_id=str(self.agent_id)) + "\n\n"
        capabilities_block += tools_block

        # 6. Worker reports
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
        except Exception as e:
            self._log.debug("Workspace slug resolution notice: %s", e)
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
            await self._run_loop_native(db_session, initial_prompt, attachments, token, trigger_message_id=trigger_message_id)
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
            # Guarantee terminal status publication so UI never remains stuck in "thinking"
            try:
                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "idle",
                })
            except Exception as idle_err:
                self._log.debug("Notice: failed to emit idle in finally: %s", idle_err)

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

    def _estimate_tokens(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Token counting via tiktoken (cl100k_base) with native tool support
        and role-aware fallback. Accounts for system instructions, tool schemas,
        tool_use inputs, and tool_results.
        """
        def _extract_text(content: Any) -> str:
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for p in content:
                    if not isinstance(p, dict):
                        parts.append(str(p))
                        continue
                    p_type = p.get("type")
                    if p_type == "text":
                        parts.append(p.get("text", ""))
                    elif p_type == "tool_use":
                        parts.append(f"{p.get('name', '')} {json.dumps(p.get('input', {}))}")
                    elif p_type == "tool_result":
                        parts.append(str(p.get("content", "")))
                    elif p_type == "image":
                        parts.append("[IMAGE_TOKEN_ESTIMATE_1600]")
                    else:
                        parts.append(str(p))
                return " ".join(parts)
            return str(content)

        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            total = 0
            if system_prompt:
                total += len(enc.encode(system_prompt, disallowed_special=())) + 4
            if tools:
                tools_json = json.dumps(tools)
                total += len(enc.encode(tools_json, disallowed_special=())) + 8

            for m in messages:
                text = _extract_text(m.get("content", ""))
                total += len(enc.encode(text, disallowed_special=())) + 4
            return total + 2
        except Exception:
            pass

        # Fallback heuristic: role-aware estimation
        total = 0
        if system_prompt:
            total += len(system_prompt) // 4 + 4
        if tools:
            total += len(json.dumps(tools)) // 4 + 8

        for m in messages:
            text = _extract_text(m.get("content", ""))
            if "tool_result" in text or "[OBSERVATION]" in text or "```" in text:
                total += len(text) // 3
            elif "[COMPACTED HISTORY" in text:
                total += len(text) // 3
            else:
                total += len(text) // 4
            total += 4
        return int(total * 1.05) + 2

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
            role = msg.get("role")
            content = msg.get("content", "")

            if role != "user":
                new_msgs.append(msg)
                continue

            changed = False
            is_historical = (num_msgs - idx) > 4

            if isinstance(content, list):
                new_blocks = []
                for b in content:
                    if not isinstance(b, dict):
                        new_blocks.append(b)
                        continue
                    b_type = b.get("type")
                    if b_type == "tool_result":
                        res_str = str(b.get("content", ""))
                        if is_historical and len(res_str) > 300:
                            lines = res_str.splitlines()
                            first_line = lines[0][:100] if lines else "Result"
                            b_copy = dict(b)
                            b_copy["content"] = f"{first_line} ...[{len(lines)} lines / {len(res_str)} chars compacted]"
                            new_blocks.append(b_copy)
                            changed = True
                        elif len(res_str) > max_chars:
                            half = max_chars // 2
                            dropped = len(res_str) - max_chars
                            b_copy = dict(b)
                            b_copy["content"] = f"{res_str[:half]}\n...[{dropped} chars truncated]...\n{res_str[-half:]}"
                            new_blocks.append(b_copy)
                            changed = True
                        else:
                            new_blocks.append(b)
                    elif b_type == "image" and is_historical:
                        # Strip base64 data payloads in older turns
                        lp = b.get("local_path")
                        if lp:
                            new_blocks.append({"type": "text", "text": f"[Image attached: {lp}]"})
                            changed = True
                        else:
                            new_blocks.append(b)
                    else:
                        new_blocks.append(b)

                if changed:
                    new_msg = dict(msg)
                    new_msg["content"] = new_blocks
                    new_msgs.append(new_msg)
                else:
                    new_msgs.append(msg)
                continue

            if not isinstance(content, str):
                new_msgs.append(msg)
                continue

            # String content processing
            # Strip base64 image payloads
            if "data:image" in content:
                content = re.sub(r'data:image/[^;]+;base64,[a-zA-Z0-9+/=]+', '[IMAGE_STRIPPED]', content)
                changed = True

            # Historical tool result micro-compaction
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

        from core.agent.context_condenser import ContextCondenser, WORKING_STATE_SYSTEM_PROMPT

        prefix_end, start = ContextCondenser.compute_pruning_bounds(messages, keep_recent)
        if start <= prefix_end:
            self._log.info("Rolling compact skipped — insufficient pruning range (%d <= %d).", start, prefix_end)
            return messages

        to_compact = messages[prefix_end:start]
        if not to_compact:
            return messages

        # Explicit coverage watermark: extract newest message being compacted
        last_compacted = to_compact[-1]
        covered_msg_id = last_compacted.get("id")
        covered_ts = last_compacted.get("created_at")

        # High-Density Identifier Preservation Pass
        pinned_block = ContextCondenser.extract_pinned_identifiers(to_compact)

        # Folded File Signatures Pass (AST-Aware symbol summaries)
        try:
            touched_files = list(self._modified_files) if hasattr(self, "_modified_files") and self._modified_files else []
            from core.tools.file_tools import file_tools
            workspace_root = await file_tools.get_workspace_root(self.project_id)
            folded_block = await ContextCondenser.generate_folded_signatures_async(touched_files, workspace_root=workspace_root)
            if folded_block:
                pinned_block = f"{pinned_block}{folded_block}" if pinned_block else folded_block
        except Exception as f_err:
            self._log.debug("Folded signatures pass notice: %s", f_err)

        # Pre-Compaction Memory Flush: extract facts & graph triples before truncation (team public only)
        if db_session is not None and not getattr(self, "is_private_response", False):
            try:
                await self._pre_compaction_memory_flush(to_compact, db_session)
            except Exception as flush_err:
                await db_session.rollback()
                self._log.warning("Pre-compaction memory flush error: %s", flush_err)

        self._log.info("Rolling compaction: summarizing %d messages (indices %d..%d).", len(to_compact), prefix_end, start)
        summary_prompt = COMPACTION_USER_PROMPT.format(context=json.dumps(to_compact, default=str))
        try:
            summary = await llm_router.generate_completion(
                model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                system_prompt=WORKING_STATE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.2,
                max_tokens=2500
            )
            full_summary = f"{pinned_block}{summary}" if pinned_block else summary
            compacted = ContextCondenser.apply_sliding_window_pruning(
                messages=messages,
                checkpoint_card=full_summary,
                keep_recent_turns=keep_recent
            )
            self._log.info("Rolling compaction complete. %d → %d messages.", len(messages), len(compacted))

            # Persist CompactionEvent only for shared team chats (never leak private chats into team context)
            if db_session is not None and not getattr(self, "is_private_response", False):
                try:
                    team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
                    cov_uuid = uuid.UUID(str(covered_msg_id)) if covered_msg_id else None
                    cp_event = CompactionEvent(
                        team_id=team_uuid,
                        summary=full_summary,
                        message_count_before=len(messages),
                        triggered_by=triggered_by,
                        covered_through_message_id=cov_uuid,
                        covered_through_timestamp=covered_ts,
                    )
                    db_session.add(cp_event)
                    await db_session.commit()
                    cp_event_id = str(cp_event.id)
                    self._log.info("Compaction checkpoint persisted (id=%s, triggered_by=%s).", cp_event_id, triggered_by)

                    # Emit SSE so the UI renders a visible compaction divider
                    await event_bus.publish(self.topic, {
                        "type": "compaction_event",
                        "id": cp_event_id,
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "triggered_by": triggered_by,
                        "message_count_before": len(messages),
                        "summary_preview": full_summary[:300] + "..." if len(full_summary) > 300 else full_summary,
                        "is_private": False,
                    })
                except Exception as persist_err:
                    await db_session.rollback()
                    self._log.warning("Could not persist CompactionEvent: %s", persist_err)

            return compacted
        except Exception as e:
            self._log.warning("Rolling compaction failed, continuing with full context: %s", e)
            return messages

    async def _pre_compaction_memory_flush(self, messages_to_flush: list, db_session: AsyncSession):
        """
        Pre-Compaction Memory Flush:
        Extracts durable facts, user preferences, and graph triples from raw messages
        before compaction replaces them with a high-level summary.
        Saves extracted facts into EntityMemory and GraphTriple tables.
        """
        if not messages_to_flush or db_session is None or getattr(self, "is_private_response", False):
            return

        try:
            flush_prompt = (
                "You are an expert knowledge extraction system. Analyze the following conversation turns "
                "that are about to be compacted and truncated.\n\n"
                "Extract any durable facts, permanent user preferences, environment constants, ports, "
                "or architectural dependencies.\n"
                "CRITICAL: Never extract passwords, API keys, authentication tokens, credentials, or secrets.\n"
                "Format your response strictly as a JSON object with two arrays:\n"
                "{\n"
                '  "facts": [{"key": "short_snake_case_key", "value": "detailed fact description"}],\n'
                '  "triples": [{"subject": "EntityA", "predicate": "connects_to|uses|prefers", "object": "EntityB"}]\n'
                "}\n"
                "If no durable facts or relations are found, return {\"facts\": [], \"triples\": []}.\n\n"
                f"Conversation:\n{json.dumps(messages_to_flush, default=str)[:6000]}"
            )

            res = await llm_router.generate_completion(
                model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                system_prompt="You extract structured durable memory and knowledge graph triples before context compaction.",
                messages=[{"role": "user", "content": flush_prompt}],
                temperature=0.0,
                max_tokens=600,
            )

            json_str = res.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```", 1)[1].split("```", 1)[0].strip()

            parsed = json.loads(json_str)
            team_uuid = uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id
            proj_uuid = uuid.UUID(str(self.project_id)) if self.project_id else None

            saved_facts = 0
            for item in parsed.get("facts", []):
                k = item.get("key", "").strip()
                v = item.get("value", "").strip()
                if k and v:
                    entity = EntityMemory(
                        team_id=team_uuid,
                        project_id=proj_uuid,
                        key=k[:255],
                        value=v
                    )
                    db_session.add(entity)
                    saved_facts += 1

            saved_triples = 0
            for t in parsed.get("triples", []):
                s = t.get("subject", "").strip()
                p = t.get("predicate", "").strip()
                o = t.get("object", "").strip()
                if s and p and o:
                    triple = GraphTriple(
                        team_id=team_uuid,
                        project_id=proj_uuid,
                        subject=s[:255],
                        predicate=p[:255],
                        object_val=o,
                        confidence_score=1.0
                    )
                    db_session.add(triple)
                    saved_triples += 1

            if saved_facts or saved_triples:
                await db_session.flush()
                self._log.info(
                    "Pre-compaction memory flush completed: extracted %d facts, %d graph triples.",
                    saved_facts, saved_triples
                )
        except Exception as flush_err:
            if db_session is not None:
                await db_session.rollback()
            self._log.warning("Pre-compaction memory flush error: %s", flush_err)

    @staticmethod
    def _detect_oscillating_loop(tool_signatures: List[str]) -> Optional[str]:
        """
        Sliding-window n-gram detector for oscillating multi-step loops (e.g. A->B->A->B or A->B->C->A->B->C).
        Returns explanation string if an oscillating loop cycle is confirmed, else None.
        """
        n = len(tool_signatures)
        for L in (2, 3, 4):
            if n >= 2 * L:
                block1 = tool_signatures[-2 * L : -L]
                block2 = tool_signatures[-L:]
                if block1 == block2:
                    cycle_names = [s.split(":")[0] for s in block2]
                    return f"Oscillating tool cycle ({' -> '.join(cycle_names)}) repeated identically"
        return None

    # ──────────────────────────────────────────────────────────────────────
    # Native Tool-Calling Loop (replaces _run_loop_inner)
    # ──────────────────────────────────────────────────────────────────────

    async def _run_loop_native(
        self,
        db_session: AsyncSession,
        initial_prompt: str,
        attachments: Optional[List[Dict]] = None,
        token: Optional["CancellationToken"] = None,
        trigger_message_id: Optional[str] = None,
    ):
        """
        Production-grade ReAct loop using native JSON tool calling.

        Key features:
        - Tools are passed as JSON schemas to the API.
        - Strict turn alternation and atomic tool-result batches via MessageHistory.
        - Sequential tool execution preserving causal order and file consistency.
        - Privacy propagation across traces, events, and compaction checkpoints.
        - Stuck-loop detection with argument and error fingerprinting.
        - Sliding-window n-gram oscillating loop detection & circuit breaker.
        - Token budget cap enforcement halts.
        - Observation cache preventing context explosion.
        - Single clean termination without double-finalization on max_loops.
        """
        import hashlib as _hs
        from core.agent.message_history import MessageHistory
        from core.agent.observation_cache import cache_observation
        from core.agent.context_condenser import ContextCondenser

        # ── Reset per-session state ───────────────────────────────────────────
        self._cached_system_prompt = None
        self._last_observation = ""
        self._no_progress_count = 0
        self._consecutive_tool_errors = 0
        self._modified_files = set()
        self.is_private_response = False
        self.reply_recipient_id = None
        self._current_thought_buffer = ""
        self._current_reasoning_buffer = ""
        self._tool_call_history: List[str] = []
        self._oscillating_warned: bool = False
        self._total_run_tokens: int = 0

        if trigger_message_id:
            self.active_message_id = trigger_message_id
            try:
                t_uuid = uuid.UUID(trigger_message_id) if isinstance(trigger_message_id, str) else trigger_message_id
                t_res = await db_session.execute(select(Message).where(Message.id == t_uuid))
                trigger_msg = t_res.scalar_one_or_none()
                if trigger_msg and trigger_msg.is_private:
                    self.is_private_response = True
                    self.reply_recipient_id = trigger_msg.sender_id
            except Exception as e:
                self._log.warning("Could not check trigger message privacy: %s", e)

        # ── Fetch agent config & permissions ─────────────────────────────────
        agent_uuid = uuid.UUID(self.agent_id) if isinstance(self.agent_id, str) else self.agent_id
        res = await db_session.execute(select(Agent).where(Agent.id == agent_uuid))
        db_agent = res.scalar_one_or_none()
        if db_agent is None:
            self._log.warning(
                "Agent record not found in DB during _run_loop_native — restricting to safe-only mode."
            )
            permissions = {"__deny_non_safe__": True}
        else:
            permissions = db_agent.tool_permissions or {}

        # ── Build system prompt & tool schemas ───────────────────────────────
        system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)

        # Select the right tool schema format for this model/provider and filter by permissions
        model = self.model
        if model.startswith("gemini"):
            all_tools = ToolRegistry.to_gemini_tools(team_id=self.team_id, agent_id=self.agent_id)
            if all_tools and "functionDeclarations" in all_tools[0]:
                filtered_decls = [
                    d for d in all_tools[0]["functionDeclarations"]
                    if permissions.get(d.get("name"), "allow") != "block"
                ]
                tools = [{"functionDeclarations": filtered_decls}]
            else:
                tools = all_tools
        elif (model.startswith("claude") or model.startswith("anthropic")) and getattr(llm_router, "anthropic_key", None):
            all_tools = ToolRegistry.to_anthropic_tools(team_id=self.team_id, agent_id=self.agent_id)
            tools = [t for t in all_tools if permissions.get(t.get("name"), "allow") != "block"]
        else:
            all_tools = ToolRegistry.to_openai_tools(team_id=self.team_id, agent_id=self.agent_id)
            tools = [t for t in all_tools if permissions.get(t.get("function", {}).get("name"), "allow") != "block"]

        # ── Load conversation history into MessageHistory ─────────────────────
        from core.llm.multi_model_router import get_model_context_window
        model_ctx = get_model_context_window(model)
        if model_ctx >= 500_000:
            history_limit = 50
        elif model_ctx >= 120_000:
            history_limit = 35
        elif model_ctx >= 32_000:
            history_limit = 20
        elif model_ctx >= 16_000:
            history_limit = 10
        else:
            history_limit = 4

        raw_history = await self._load_conversation_history(
            db_session, limit=history_limit, exclude_msg_id=trigger_message_id
        )
        history = MessageHistory(seed=raw_history)

        # Build the initial user message (with attachments if present)
        content: Any = initial_prompt
        if attachments:
            content_list = [{"type": "text", "text": initial_prompt}]
            for att in attachments:
                att_type = att.get("type", "")
                if att_type.startswith("image/"):
                    content_list.append({
                        "type": "image",
                        "local_path": att.get("local_path"),
                        "mime_type": att_type,
                    })
                elif att_type == "file_ref":
                    ref_path = att.get("path") or att.get("relative_path")
                    if ref_path:
                        try:
                            from core.tools.file_tools import file_tools as _ft
                            fc = await _ft.read_file(ref_path, self.project_id)
                            if fc.startswith("Error"):
                                content_list.append({"type": "text", "text": f"\n\n[Referenced file '{ref_path}' could not be read: {fc}]"})
                            else:
                                snippet = fc if len(fc) <= 8000 else fc[:8000] + "\n...[truncated]"
                                content_list.append({"type": "text", "text": f"\n\n--- Referenced file: {ref_path} ---\n{snippet}\n--- end ---"})
                        except Exception as ref_err:
                            self._log.warning("file_ref read failed for %s: %s", ref_path, ref_err)
                            content_list.append({"type": "text", "text": f"\n\n[Referenced file '{ref_path}' error: {ref_err}]"})
                elif att.get("content"):
                    fname = att.get("name") or att.get("filename") or "attachment"
                    c_snip = str(att["content"])[:8000]
                    content_list.append({"type": "text", "text": f"\n\n--- Attached file: {fname} ---\n{c_snip}\n--- end ---"})
            content = content_list

        history.add_user(content)

        # ── Emit active status ────────────────────────────────────────────────
        await event_bus.publish(self.topic, {
            "type": "agent_status",
            "sender_id": self.agent_id,
            "sender_name": self.name,
            "role": self.role,
            "status": "active",
        })

        loop_count = 0
        max_loops = getattr(core.config, "MAX_LOOPS", 25)
        terminated = False

        # Helper to redact sensitive credentials before broadcasting
        def _sanitize_tool_args(args: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(args, dict):
                return {}
            sanitized = {}
            for k, v in args.items():
                if re.search(r"password|token|secret|credential|authorization|api[_-]?key", str(k), re.I):
                    sanitized[k] = "[REDACTED]"
                elif isinstance(v, dict):
                    sanitized[k] = _sanitize_tool_args(v)
                else:
                    sanitized[k] = v
            return sanitized

        # ── Main ReAct loop ───────────────────────────────────────────────────
        while loop_count < max_loops:
            loop_count += 1

            # Invalidate/refresh system prompt if worker results arrived
            if self._cached_system_prompt is None:
                system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)

            await event_bus.publish(self.topic, {
                "type": "typing",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking",
            })

            # Apply compaction to the message list snapshot
            messages = self._micro_compact(history.get_messages())
            messages = self._snip_dead_ends(messages)

            cc = self._get_compaction_config()
            window_size = cc["context_window_size"]
            trigger_ratio = cc["token_trigger_ratio"]
            estimated_tokens = self._estimate_tokens(messages, system_prompt=system_prompt, tools=tools)

            await event_bus.publish(self.topic, {
                "type": "context_usage",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "model": model,
                "estimated_tokens": estimated_tokens,
                "context_window": window_size,
                "usage_percent": round((estimated_tokens / window_size) * 100, 1) if window_size > 0 else 0,
                "loop_count": loop_count,
                "max_loops": max_loops,
            })

            # Enforce cumulative run token budget circuit breaker
            self._total_run_tokens += estimated_tokens
            max_budget_tokens = getattr(core.config, "MAX_BUDGET_TOKENS", 150_000)
            if self._total_run_tokens > max_budget_tokens:
                self._log.warning("[native] Run token budget exceeded: %d > %d", self._total_run_tokens, max_budget_tokens)
                budget_note = f"\n\n*[System: Agent execution halted by Circuit Breaker — cumulative token budget of {max_budget_tokens:,} tokens reached.]*"
                final_text = (self._current_thought_buffer or "") + budget_note
                db_msg = Message(
                    team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                    sender_id=self.agent_id,
                    sender_name=self.name,
                    text=final_text,
                    reasoning_text=self._current_reasoning_buffer or None,
                    is_private=self.is_private_response,
                    recipient_id=self.reply_recipient_id,
                )
                db_session.add(db_msg)
                try:
                    await db_session.commit()
                except Exception:
                    await db_session.rollback()
                await event_bus.publish(self.topic, {
                    "type": "message",
                    "id": str(db_msg.id),
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": final_text,
                    "is_private": self.is_private_response,
                    "recipient_id": self.reply_recipient_id,
                })
                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "idle",
                })
                terminated = True
                break

            if ContextCondenser.is_under_context_pressure(estimated_tokens, window_size, trigger_ratio):
                self._log.warning(
                    "Context at %.0f%%. Triggering rolling compaction...",
                    (estimated_tokens / window_size) * 100,
                )
                messages = await self._rolling_compact(messages, db_session=db_session, triggered_by="auto")
                history = MessageHistory(seed=messages)
                messages = history.get_messages()

            # Graceful degradation at loop_count == max_loops - 2
            if loop_count == max_loops - 2:
                self._log.warning(
                    "Approaching loop limit (%d/%d). Injecting graceful degradation note.",
                    loop_count, max_loops,
                )
                history.add_context_note(
                    "[SYSTEM INSTRUCTION — GRACEFUL DEGRADATION]\n"
                    "You are running low on execution loops. You have 2 loops remaining.\n"
                    "If you cannot complete the task, produce a structured summary of:\n"
                    "  1. What you attempted  2. What errors you encountered  3. What partial progress was made\n"
                    "Then deliver your best possible answer to the user right now."
                )
                messages = history.get_messages()

            # ── LLM call — stream text & collect tool calls ───────────────────
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking",
            })

            self._log.info("[native] Thinking... (loop %d/%d)", loop_count, max_loops)

            assistant_text = ""
            tool_uses: List[Dict[str, Any]] = []
            stop_reason: Optional[str] = None
            had_error = False

            for attempt in range(3):
                assistant_text = ""
                tool_uses = []
                stop_reason = None
                self._current_thought_buffer = ""

                if attempt > 0:
                    await event_bus.publish(self.topic, {
                        "type": "thought_reset",
                        "sender_id": self.agent_id,
                    })

                try:
                    async for event in llm_router.generate_with_tools(
                        model=model,
                        system_prompt=system_prompt,
                        messages=messages,
                        tools=tools,
                        temperature=0.4,
                        max_tokens=8192,
                        tool_choice="auto",
                        team_id=self.team_id,
                        agent_id=self.agent_id,
                        agent_name=self.name,
                        project_id=self.project_id,
                        fallback_model=self.fallback_model,
                        reasoning_effort=self.reasoning_effort if self.reasoning_effort != "none" else None,
                    ):
                        etype = event.get("type", "")

                        if etype == "text_delta":
                            chunk = event["delta"]
                            assistant_text += chunk
                            self._current_thought_buffer = assistant_text
                            await event_bus.publish(self.topic, {
                                "type": "thought_delta",
                                "sender_id": self.agent_id,
                                "sender_name": self.name,
                                "role": self.role,
                                "delta": chunk,
                            })

                        elif etype == "reasoning_delta":
                            r_chunk = event.get("delta", "")
                            if r_chunk:
                                if len(self._current_reasoning_buffer) < 35000:
                                    self._current_reasoning_buffer += r_chunk
                                elif not self._current_reasoning_buffer.endswith("...[Reasoning trace truncated]"):
                                    self._current_reasoning_buffer += "\n...[Reasoning trace truncated]"
                                await event_bus.publish(self.topic, {
                                    "type": "stream_reasoning",
                                    "sender_id": self.agent_id,
                                    "sender_name": self.name,
                                    "role": self.role,
                                    "chunk": r_chunk,
                                })

                        elif etype == "tool_use":
                            tool_uses.append(event)

                        elif etype == "message_stop":
                            stop_reason = event.get("stop_reason")

                    break  # Success — exit retry loop

                except Exception as e:
                    from core.llm.multi_model_router import LLMProviderError
                    if isinstance(e, LLMProviderError):
                        had_error = True
                        error_msg = f"⚠️ {e.message}"
                        self._log.error("[native] LLM Provider Error: %s", e.message)
                        await event_bus.publish(self.topic, {
                            "type": "llm_error",
                            "sender_id": self.agent_id,
                            "error": e.to_dict(),
                        })
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=error_msg,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        db_session.add(db_msg)
                        try:
                            await db_session.commit()
                        except Exception:
                            await db_session.rollback()
                        break

                    error_str = str(e).lower()
                    is_context_limit = ("413" in error_str or "too long" in error_str or "context_length" in error_str)
                    if is_context_limit:
                        self._log.error("[native] API hit context limit! Forcing emergency rolling compaction (attempt %d).", attempt + 1)
                        messages = await self._rolling_compact(messages, db_session=db_session, triggered_by="emergency")
                        history = MessageHistory(seed=messages)
                        messages = history.get_messages()
                        continue

                    if attempt < 2:
                        wait = (2 ** attempt) * 2
                        self._log.warning("[native] LLM error (attempt %d): %s. Retrying in %ds...", attempt + 1, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        had_error = True
                        error_msg = f"⚠️ LLM API error after 3 retries: {str(e)}"
                        self._log.error("[native] %s", error_msg)
                        db_msg = Message(
                            team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                            sender_id=self.agent_id,
                            sender_name=self.name,
                            text=error_msg,
                            is_private=self.is_private_response,
                            recipient_id=self.reply_recipient_id,
                        )
                        db_session.add(db_msg)
                        try:
                            await db_session.commit()
                        except Exception:
                            await db_session.rollback()
                        await event_bus.publish(self.topic, {
                            "type": "message",
                            "id": str(db_msg.id),
                            "sender_id": self.agent_id,
                            "sender_name": self.name,
                            "role": self.role,
                            "text": error_msg,
                        })

            if had_error:
                await event_bus.publish(self.topic, {
                    "type": "agent_status",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "status": "idle",
                })
                terminated = True
                break

            # Strip any name prefix hallucination from assistant text
            assistant_text = re.sub(r'^\[[^\]]+\]:\s*', '', assistant_text, count=1)

            # Accumulate assistant text into reasoning trace (for UI display)
            if assistant_text:
                self._current_reasoning_buffer += f"\n{assistant_text}"

            # Record this turn in MessageHistory
            tool_use_blocks = [
                {"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]}
                for t in tool_uses
            ]

            # ── Termination check: no tool calls = model is done ─────────────
            if not tool_uses:
                if stop_reason in ("max_tokens", "length"):
                    self._log.warning("[native] Model stopped due to length/max_tokens truncation.")

                if not assistant_text.strip():
                    if loop_count < max_loops - 1:
                        self._log.warning("[native] Empty assistant text received without tool calls; requesting output.")
                        history.add_context_note(
                            "[SYSTEM NOTE: Your response was completely empty. Please provide your answer or next action.]"
                        )
                        continue
                    else:
                        assistant_text = "Task processing completed."

                history.add_assistant_text(text=assistant_text, tool_uses=None)
                self._log.info("[native] No tool calls in response — agent finished after %d loop(s).", loop_count)

                # Collapse streaming thought to reasoning panel
                await event_bus.publish(self.topic, {
                    "type": "collapse_to_reasoning",
                    "sender_id": self.agent_id,
                })

                # Subagent notification wrapping
                is_temporary_subagent = self.name.startswith("Sub-")
                coordinator_notification = None
                if self.parent_coordinator_id:
                    coordinator_notification = self._build_task_notification(assistant_text, "completed")
                    if is_temporary_subagent:
                        assistant_text = coordinator_notification

                attachments_list = []
                if self.parent_message_id:
                    attachments_list.append({"type": "parent_message", "id": self.parent_message_id})

                db_msg = Message(
                    team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                    sender_id=self.agent_id,
                    sender_name=self.name,
                    text=assistant_text,
                    reasoning_text=self._current_reasoning_buffer or None,
                    is_private=self.is_private_response,
                    recipient_id=self.reply_recipient_id,
                    attachments=attachments_list,
                )
                db_session.add(db_msg)
                try:
                    await db_session.commit()
                except Exception as commit_err:
                    await db_session.rollback()
                    self._log.warning("[native] Could not commit final message: %s", commit_err)
                self.active_message_id = str(db_msg.id)

                # Wake up parent coordinator if present
                if self.parent_coordinator_id and coordinator_notification:
                    try:
                        from core.chat.message_router import message_router
                        parent_uuid = uuid.UUID(str(self.parent_coordinator_id))
                        stmt = select(Agent).where(Agent.id == parent_uuid)
                        p_res = await db_session.execute(stmt)
                        parent_agent = p_res.scalar_one_or_none()
                        if parent_agent:
                            await message_router._enqueue_agent(
                                agent=parent_agent,
                                prompt_text=coordinator_notification,
                                db_session=db_session,
                                attachments=[],
                                trigger_message_id=str(db_msg.id),
                            )
                    except Exception as notify_err:
                        self._log.exception("Failed to notify parent coordinator: %s", notify_err)

                await event_bus.publish(self.topic, {
                    "type": "message",
                    "id": str(db_msg.id),
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": assistant_text,
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
                terminated = True
                break

            history.add_assistant_text(text=assistant_text, tool_uses=tool_use_blocks)

            # ── Execute tools SEQUENTIALLY to preserve causality ──────────────
            await event_bus.publish(self.topic, {
                "type": "collapse_to_reasoning",
                "sender_id": self.agent_id,
            })

            async def _exec_single_tool(tc: Dict[str, Any]):
                """Execute a single tool call and return (id, name, observation, is_error)."""
                tool_id = tc["id"]
                tool_name = tc["name"]
                tool_args = tc.get("input", {})
                is_error = False

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
                    "arguments": _sanitize_tool_args(tool_args),
                    "is_private": self.is_private_response,
                    "recipient_id": self.reply_recipient_id,
                })

                try:
                    observation = await self._execute_tool(
                        name=tool_name, args=tool_args,
                        permissions=permissions, token=token,
                    )
                    if str(observation).startswith("✗") or "Error" in str(observation):
                        is_error = True
                    else:
                        if tool_name in ("write_file", "edit_file", "append_file", "delete_file"):
                            fpath = tool_args.get("path") or tool_args.get("relative_path") or tool_args.get("file_path")
                            if fpath:
                                self._modified_files.add(str(fpath))
                except Exception as e:
                    observation = f"✗ Tool Error: {str(e)}"
                    is_error = True
                    self._log.error("[native] Tool '%s' raised exception: %s", tool_name, e)

                if is_error:
                    self._consecutive_tool_errors += 1
                    obs_lower = str(observation).lower()
                    hint = ""
                    if "modulenotfounderror" in obs_lower or "importerror" in obs_lower:
                        hint = "\n\n💡 Hint: A Python module is missing. Try installing it with execute_command({\"command\": \"pip install <module_name>\"})."
                    elif "command not found" in obs_lower or "not recognized" in obs_lower:
                        hint = "\n\n💡 Hint: Command not found. Check installation or use the full path."
                    elif "permission denied" in obs_lower:
                        hint = "\n\n💡 Hint: Permission denied. The file may be read-only."
                    elif "no such file or directory" in obs_lower or "filenotfounderror" in obs_lower:
                        hint = "\n\n💡 Hint: File or directory not found. Use list_directory to verify the path."
                    elif "target_content not found" in obs_lower or "no match found" in obs_lower:
                        hint = "\n\n💡 Hint: edit_file target_content didn't match. Use read_file to see exact current content."
                    if hint:
                        observation = str(observation) + hint

                    if self._consecutive_tool_errors >= 3:
                        observation = str(observation) + (
                            f"\n\n🛑 [SYSTEM WARNING: {self._consecutive_tool_errors} consecutive tool failures. "
                            "STOP repeating the same action. Diagnose the root cause and try a completely different approach.]"
                        )
                else:
                    self._consecutive_tool_errors = 0

                observation = cache_observation(tool_name, str(observation))
                return tool_id, tool_name, observation, is_error

            results = []
            for tc in tool_uses:
                res = await _exec_single_tool(tc)
                results.append(res)

            # Persist and broadcast tool traces
            for tool_id, tool_name, observation, is_err in results:
                display_obs = observation if len(observation) <= 4000 else observation[:4000] + "\n... [output truncated]"

                await event_bus.publish(self.topic, {
                    "type": "tool_end",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "observation": display_obs,
                    "is_private": self.is_private_response,
                    "recipient_id": self.reply_recipient_id,
                })

                try:
                    args_str = json.dumps(
                        next((t["input"] for t in tool_uses if t["id"] == tool_id), {}),
                        indent=2,
                    )
                except Exception:
                    args_str = "{}"

                intermediate_trace = (
                    f"🛠️ **{tool_name}**\n```json\n{args_str}\n```\n"
                    f"📄 **Result:**\n```\n{display_obs}\n```"
                )
                self._current_reasoning_buffer += f"\n{intermediate_trace}\n"

                attachments_list = []
                if self.parent_message_id:
                    attachments_list.append({"type": "parent_message", "id": self.parent_message_id})

                db_trace_msg_id = None
                try:
                    db_trace = Message(
                        team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                        sender_id=self.agent_id,
                        sender_name=self.name,
                        text=intermediate_trace,
                        is_intermediate=True,
                        is_private=self.is_private_response,
                        recipient_id=self.reply_recipient_id,
                        attachments=attachments_list,
                    )
                    db_session.add(db_trace)
                    await db_session.commit()
                    db_trace_msg_id = str(db_trace.id)
                except Exception as persist_err:
                    await db_session.rollback()
                    self._log.warning("[native] Failed to persist tool trace: %s", persist_err)

                await event_bus.publish(self.topic, {
                    "type": "tool_trace",
                    "id": db_trace_msg_id,
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": intermediate_trace,
                    "is_intermediate": True,
                    "is_private": self.is_private_response,
                    "recipient_id": self.reply_recipient_id,
                    "attachments": attachments_list,
                })

            # Atomic commit of tool results batch to history
            history.add_tool_results([
                {
                    "tool_use_id": r_id,
                    "content": r_obs,
                    "tool_name": r_name,
                    "is_error": r_err,
                }
                for r_id, r_name, r_obs, r_err in results
            ])

            # ── No-progress guard ─────────────────────────────────────────────
            fp_parts = []
            any_mutations = False
            for r_id, r_name, r_obs, r_err in results:
                if not r_err and r_name in ("write_file", "edit_file", "append_file", "delete_file", "write_scratchpad"):
                    any_mutations = True
                tc_input = next((t["input"] for t in tool_uses if t["id"] == r_id), {})
                sorted_args = json.dumps(tc_input, sort_keys=True, default=str)
                norm_obs = re.sub(r'\s+', ' ', re.sub(
                    r'\b(\d{4}-\d{2}-\d{2}|0x[0-9a-f]+|\d+\.\d+\s*(?:ms|s|sec))\b', '', str(r_obs)
                )).strip()[:400]
                fp_parts.append(f"{r_name}:{sorted_args}:{norm_obs}:{r_err}")

            obs_fp = _hs.md5("|".join(fp_parts).encode("utf-8")).hexdigest()

            # Record signatures for sliding-window n-gram loop detection
            for r_id, r_name, r_obs, r_err in results:
                tc_input = next((t["input"] for t in tool_uses if t["id"] == r_id), {})
                input_hash = _hs.md5(json.dumps(tc_input, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:6]
                self._tool_call_history.append(f"{r_name}:{input_hash}")

            # ── Sliding-window oscillating loop circuit breaker ──────────────
            osc_loop = self._detect_oscillating_loop(self._tool_call_history)
            if osc_loop:
                self._log.warning("[native] Oscillating loop detected: %s", osc_loop)
                if not self._oscillating_warned:
                    self._oscillating_warned = True
                    history.add_context_note(
                        f"[CIRCUIT BREAKER WARNING: {osc_loop}. "
                        "You are trapped in an oscillating action cycle. Cease executing this tool sequence. "
                        "Switch to a new approach or conclude your response immediately.]"
                    )
                else:
                    self._log.warning("[native] Halting execution due to repeating oscillating cycle.")
                    halt_note = f"\n\n*[System: Execution halted by Circuit Breaker — {osc_loop}.]*"
                    final_text = (assistant_text or "") + halt_note
                    db_msg = Message(
                        team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                        sender_id=self.agent_id,
                        sender_name=self.name,
                        text=final_text,
                        reasoning_text=self._current_reasoning_buffer or None,
                        is_private=self.is_private_response,
                        recipient_id=self.reply_recipient_id,
                    )
                    db_session.add(db_msg)
                    try:
                        await db_session.commit()
                    except Exception:
                        await db_session.rollback()
                    await event_bus.publish(self.topic, {
                        "type": "message",
                        "id": str(db_msg.id),
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "text": final_text,
                        "is_private": self.is_private_response,
                        "recipient_id": self.reply_recipient_id,
                    })
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                    await self._auto_save_failure_lesson(
                        initial_prompt=initial_prompt,
                        messages=history.get_messages(),
                        reason=f"oscillating-loop ({osc_loop})",
                    )
                    terminated = True
                    return

            if obs_fp == self._last_observation and not any_mutations:
                self._no_progress_count += 1
                if self._no_progress_count >= 2:
                    self._log.warning("[native] No-progress guard triggered after %d identical observations.", self._no_progress_count)
                    stuck_note = (
                        "\n\n*[System: Agent loop stopped — the last 3 tool calls returned identical results. "
                        "This usually means the tool is stuck or the target resource is unavailable. "
                        "Please review the tool output above and try a different approach.]*"
                    )
                    final_text = (assistant_text or "") + stuck_note
                    db_msg = Message(
                        team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                        sender_id=self.agent_id,
                        sender_name=self.name,
                        text=final_text,
                        reasoning_text=self._current_reasoning_buffer or None,
                        is_private=self.is_private_response,
                        recipient_id=self.reply_recipient_id,
                    )
                    db_session.add(db_msg)
                    try:
                        await db_session.commit()
                    except Exception:
                        await db_session.rollback()
                    await event_bus.publish(self.topic, {
                        "type": "message",
                        "id": str(db_msg.id),
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "text": final_text,
                        "is_private": self.is_private_response,
                        "recipient_id": self.reply_recipient_id,
                    })
                    await event_bus.publish(self.topic, {
                        "type": "agent_status",
                        "sender_id": self.agent_id,
                        "sender_name": self.name,
                        "role": self.role,
                        "status": "idle",
                    })
                    await self._auto_save_failure_lesson(
                        initial_prompt=initial_prompt,
                        messages=history.get_messages(),
                        reason="no-progress (identical observations without mutation)",
                    )
                    terminated = True
                    return
            else:
                self._no_progress_count = 0
            self._last_observation = obs_fp

            # Invalidate cached system prompt if new worker results arrived
            if self._worker_results:
                self._invalidate_system_prompt_cache()

        # ── Hit max_loops (only if not cleanly terminated) ───────────────────
        if not terminated and loop_count >= max_loops:
            self._log.warning("[native] Agent hit max loop limit (%d). Terminating.", max_loops)
            final_note = f"\n\n*[System: Agent reached maximum loop limit of {max_loops}.]*"
            final_text = (self._current_thought_buffer or "") + final_note
            db_msg = Message(
                team_id=uuid.UUID(self.team_id) if isinstance(self.team_id, str) else self.team_id,
                sender_id=self.agent_id,
                sender_name=self.name,
                text=final_text,
                reasoning_text=self._current_reasoning_buffer or None,
                is_private=self.is_private_response,
                recipient_id=self.reply_recipient_id,
            )
            db_session.add(db_msg)
            try:
                await db_session.commit()
            except Exception:
                await db_session.rollback()
            await event_bus.publish(self.topic, {
                "type": "message",
                "id": str(db_msg.id),
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "text": final_text,
                "is_private": self.is_private_response,
                "recipient_id": self.reply_recipient_id,
            })
            await event_bus.publish(self.topic, {
                "type": "agent_status",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "idle",
            })
            await self._auto_save_failure_lesson(
                initial_prompt=initial_prompt,
                messages=history.get_messages(),
                reason=f"max_loops ({max_loops})",
            )

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
                raw_c = msg.get("content", "")
                if isinstance(raw_c, list):
                    block_texts = []
                    for c in raw_c:
                        if isinstance(c, dict):
                            btype = c.get("type")
                            if btype == "text":
                                block_texts.append(c.get("text", ""))
                            elif btype == "tool_use":
                                block_texts.append(f"[Tool Call: {c.get('name')}({json.dumps(c.get('input', {}), default=str)[:150]})]")
                            elif btype == "tool_result":
                                block_texts.append(f"[Tool Result: {str(c.get('content', ''))[:200]}]")
                    c_text = " ".join(block_texts)
                else:
                    c_text = str(raw_c)
                if len(c_text) > 500:
                    c_text = c_text[:500] + "..."
                summary_lines.append(f"[{role}]: {c_text}")
            context_block = "\n".join(summary_lines)

            extraction_prompt = (
                "An AI agent was attempting the following task but got terminated due to: "
                f"{reason}.\n\n"
                f"Original user request: {initial_prompt[:300]}\n\n"
                f"Last conversation context:\n{context_block}\n\n"
                "Extract exactly ONE concise, abstract tool-engineering rule the agent should remember.\n\n"
                "CRITICAL RULES FOR EXTRACTION:\n"
                "- NEVER extract user requirements, specific application logic, file paths (e.g. 'calc.py'), or method signatures (e.g. 'add(a, b)') as a lesson!\n"
                "- ONLY extract abstract tool-usage failure rules (e.g. 'Always check if directory exists before creating nested files', 'Do not retry the same failing bash command repeatedly').\n"
                "- If the task simply timed out or the agent didn't finish coding, output NO_LESSON.\n\n"
                "Output format:\n"
                "TASK: <one-line abstract category of operation>\n"
                "LESSON: <one-line actionable tool heuristic>\n\n"
                "Output exactly NO_LESSON (nothing else) if ANY of these are true:\n"
                "- The failure was simply running out of loops or partial implementation\n"
                "- The failure was caused by external factors (API downtime, rate limits, network errors)\n"
                "- The lesson would merely restate user requirements or code specifications\n"
                "- There is no clear, generalizable tool usage mistake to correct"
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
            # Guard against dummy placeholder invocations (e.g. model literally copying [ACTION]tool_name(...)[/ACTION])
            if tool_name.lower() in ("tool_name", "toolname", "placeholder", "example_tool", "your_tool", "some_tool"):
                return None
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
                    except Exception as e:
                        self._log.debug("Positional arg literal_eval notice: %s", e)
                if pos_vals:
                    arguments["_positional_args"] = pos_vals
                    # Intelligently map single positional arg to tool's primary expected parameter
                    if len(pos_vals) == 1:
                        val = pos_vals[0]
                        if any(k in tool_name for k in ("read_file", "view_file", "get_file_outline")):
                            arguments["relative_path"] = val
                        elif any(k in tool_name for k in ("search", "find", "grep")):
                            arguments["query"] = val
                        elif any(k in tool_name for k in ("command", "terminal", "bash", "execute")):
                            arguments["command"] = val
                        elif any(k in tool_name for k in ("navigate", "fetch", "url")):
                            arguments["url"] = val
                        elif "symbol" in tool_name:
                            arguments["symbol_name"] = val
                        else:
                            arguments["value"] = val
            for kw in getattr(tree.body, "keywords", []):  # type: ignore[attr-defined]
                try:
                    arguments[kw.arg] = _ast.literal_eval(kw.value)
                except Exception as e:
                    self._log.debug("Keyword arg literal_eval notice: %s", e)
            if arguments:
                return tool_name, arguments
        except Exception as e:
            self._log.debug("AST call parse attempt notice: %s", e)

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
        import html
        task_id = html.escape(str(self.task_id or "unknown"))
        agent_name = html.escape(str(self.name))
        status_esc = html.escape(str(status))
        result_summary = result_text[:1500] if len(result_text) > 1500 else result_text
        result_esc = html.escape(result_summary)
        files_block = ""
        if hasattr(self, "_modified_files") and self._modified_files:
            files_block = "  <files_modified>\n" + "\n".join(f"    <file>{html.escape(str(f))}</file>" for f in sorted(self._modified_files)) + "\n  </files_modified>\n"
        return (
            f"<task-notification>\n"
            f"  <task_id>{task_id}</task_id>\n"
            f"  <agent>{agent_name}</agent>\n"
            f"  <status>{status_esc}</status>\n"
            f"{files_block}"
            f"  <result>{result_esc}</result>\n"
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
                            self._invalidate_system_prompt_cache()
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
        import html
        notifications = []
        pattern = r"<task-notification>(.*?)</task-notification>"
        matches = re.findall(pattern, text, re.DOTALL)

        for match in matches:
            notification = {}
            for field in ["task_id", "agent", "status", "result", "tokens_used"]:
                field_match = re.search(f"<{field}>(.*?)</{field}>", match, re.DOTALL)
                if field_match:
                    notification[field] = html.unescape(field_match.group(1).strip())
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
            active_message_id=self.active_message_id,
            agent_role=self.role,
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
