# -*- coding: utf-8 -*-
"""
backend/core/chat/message_router.py

This file defines the router that parses and directs incoming messages.

Responsibilities:
1. Parse incoming text for @name (group tag) and /@name (private tag) mentions.
2. Support multiple @mentions in a single message (fan-out to multiple agents).
3. If no @mention, optionally route to the Coordinator agent.
4. Persist messages to the DB and broadcast via EventBus.
5. Trigger target Agent ReACT loops via a per-agent FIFO sequential queue
   (Actor Model) - agents process their assigned tasks one at a time, in order,
   preventing race conditions on dependent tasks.
"""

import re
import uuid
import time
import asyncio
import logging
from typing import Optional, List, Set, Dict, Tuple, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("carole.message_router")

from core.chat.event_bus import event_bus
from core.memory.models import Agent, Message, Team, Project, User
from core.memory.database import async_session
from core.tools.context import CancellationToken
from core.config import MAX_QUEUE_SIZE

_SENTINEL = None  # Sent to a worker queue to signal graceful shutdown


class MessageRouter:
    def __init__(self):
        # Per-agent FIFO queues (Actor Model).
        # Each agent gets exactly ONE queue and ONE long-lived worker coroutine.
        self._queues: Dict[str, asyncio.Queue] = {}
        self._workers: Dict[str, asyncio.Task] = {}

        # Currently *executing* loop per agent - used for cancellation only.
        # Value is (asyncio.Task, CancellationToken) while running, None otherwise.
        self._running: Dict[str, Optional[Tuple[asyncio.Task, CancellationToken]]] = {}

        # Snapshot of pending prompts for queue introspection (REST /queue endpoint).
        self._pending: Dict[str, List[str]] = {}
        self._pending_keys: Dict[str, Set[str]] = {}
        
        # Locks to prevent race conditions when enqueuing to a new agent
        self._enqueue_locks: Dict[str, asyncio.Lock] = {}

    def _get_enqueue_lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._enqueue_locks:
            self._enqueue_locks[agent_id] = asyncio.Lock()
        return self._enqueue_locks[agent_id]

    async def shutdown(self):
        """Stop agent work before closing provider clients and the database."""
        running = [entry[0] for entry in self._running.values() if entry]
        for agent_id in list(self._running):
            self.cancel_agent(agent_id, cancel_all=True)
        workers = list(self._workers.values())
        for worker in workers:
            worker.cancel()
        if workers or running:
            await asyncio.gather(*workers, *running, return_exceptions=True)
        self._queues.clear()
        self._workers.clear()
        self._running.clear()
        self._pending.clear()
        self._pending_keys.clear()
        self._enqueue_locks.clear()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def cancel_agent(self, agent_id: str, cancel_all: bool = False) -> int:
        """
        Cancel the currently running agent loop.

        Args:
            agent_id:   Target agent.
            cancel_all: If True, also drain the entire queue so no further
                        tasks will execute. If False (default), only the
                        *current* execution is cancelled; queued tasks remain.

        Returns:
            Number of active loop tasks cancelled.
        """
        count = 0
        current = self._running.get(agent_id)
        if current:
            task, token = current
            if not task.done():
                token.cancel()
                task.cancel()
                count += 1

        if cancel_all:
            q = self._queues.get(agent_id)
            if q:
                # Drain the queue
                while not q.empty():
                    try:
                        q.get_nowait()
                        q.task_done()
                    except asyncio.QueueEmpty:
                        break
            if agent_id in self._pending:
                self._pending[agent_id].clear()
            else:
                self._pending[agent_id] = []
            self._pending_keys.setdefault(agent_id, set()).clear()
            logger.info("Cleared queue for agent %s", agent_id)

        logger.info("Cancelled %d running task(s) for agent %s (cancel_all=%s)",
                    count, agent_id, cancel_all)
        return count

    def get_queue_status(self, agent_id: str) -> dict:
        """Return queue depth and pending prompts for the REST /queue endpoint."""
        q = self._queues.get(agent_id)
        is_running = bool(
            self._running.get(agent_id) and
            not self._running[agent_id][0].done()  # type: ignore[index]
        )
        return {
            "agent_id": agent_id,
            "queue_depth": q.qsize() if q else 0,
            "is_running": is_running,
            "pending": list(self._pending.get(agent_id, [])),
        }

    async def route_message(
        self,
        text: str,
        sender_id: str,
        team_id: str,
        sender_name: Optional[str] = None,
        attachments: Optional[List[Dict]] = None,
    ):
        """
        Parses a raw incoming message, persists it, and triggers agent ReACT loops
        based on @mention and /@private mention patterns.
        Supports multiple @mentions in a single message (fan-out to multiple agents).

        Each targeted agent is woken via its personal FIFO queue rather than
        direct task spawning, guaranteeing sequential execution per agent.
        """
        is_private = False

        # Persist message to database
        async with async_session() as db:
            target_agents: List[Agent] = []
            recipient_id = None

            try:
                team_uuid = uuid.UUID(team_id)
            except (ValueError, AttributeError):
                logger.error("Invalid team_id in route_message: %s", team_id)
                return

            # Verify the team actually exists in the database and capture project_id
            stmt = select(Team.id, Team.project_id).where(Team.id == team_uuid)
            result = await db.execute(stmt)
            team_row = result.first()
            if team_row is None:
                logger.warning("Team %s not found. Dropping message from %s.", team_id, sender_id)
                return
            project_id = str(team_row.project_id) if team_row.project_id else ""
            if sender_id == "human" and attachments:
                from core.chat.attachments import normalize_chat_attachments
                attachments = await normalize_chat_attachments(attachments, team_id, project_id)

            # If sender_id is an agent UUID, verify that the agent belongs to this team
            if sender_id not in ("human", "system"):
                try:
                    sender_uuid = uuid.UUID(sender_id)
                    stmt = select(Agent.id).where(Agent.id == sender_uuid, Agent.team_id == team_uuid)
                    agent_res = await db.execute(stmt)
                    if agent_res.scalar_one_or_none() is None:
                        logger.warning("Sender agent %s does not belong to team %s. Dropping message.", sender_id, team_id)
                        return
                except ValueError:
                    logger.warning("Rejected non-UUID agent sender %r for team %s.", sender_id, team_id)
                    return

            # Resolve literal team member names so spaces and punctuation work. Every
            # public mention is a target; /@name keeps the message private to the
            # explicitly named recipients.
            if sender_id != "system":
                from core.tasks.board_service import resolve_mentions
                mentioned_agents = await resolve_mentions(db, team_uuid, text)
                private_agents = [
                    agent for agent in mentioned_agents
                    if re.search(rf"/@{re.escape(agent.name)}(?=$|[\s,.;:!?()\[\]{{}}])", text, re.IGNORECASE)
                ]
                is_private = bool(private_agents)
                candidates = private_agents if is_private else mentioned_agents
                target_agents.extend(agent for agent in candidates if str(agent.id) != sender_id)
                if is_private and len(target_agents) == 1:
                    recipient_id = str(target_agents[0].id)

            resolved_sender_name = sender_name
            if sender_id == "human" and not resolved_sender_name:
                # OPTIMIZATION: Single joined query to resolve user's full name from team_uuid
                stmt = (
                    select(User)
                    .join(Project, Project.owner_id == User.id)
                    .join(Team, Team.project_id == Project.id)
                    .where(Team.id == team_uuid)
                )
                res = await db.execute(stmt)
                user = res.scalar_one_or_none()
                if user:
                    first = user.first_name or ""
                    last = user.last_name or ""
                    resolved_sender_name = f"{first} {last}".strip()

            if not resolved_sender_name and sender_id == "human":
                resolved_sender_name = "You"
            elif not resolved_sender_name:
                resolved_sender_name = sender_id

            # If no agents mentioned, try to infer target from conversational context
            if not target_agents and sender_id == "human":
                # Find the most recent non-system message
                stmt = select(Message).where(
                    Message.team_id == team_uuid,
                    Message.sender_id != "system"
                ).order_by(Message.created_at.desc()).limit(1)
                res = await db.execute(stmt)
                last_msg = res.scalar_one_or_none()

                inferred_agent_id = None
                if last_msg:
                    if last_msg.sender_id != "human":
                        # Last message was from an agent, reply to them
                        inferred_agent_id = last_msg.sender_id
                    elif last_msg.recipient_id:
                        # Last message was from human to a specific agent
                        inferred_agent_id = last_msg.recipient_id

                if inferred_agent_id:
                    try:
                        stmt = select(Agent).where(Agent.id == uuid.UUID(inferred_agent_id))
                        res = await db.execute(stmt)
                        inferred_agent = res.scalar_one_or_none()
                        if inferred_agent:
                            target_agents.append(inferred_agent)
                            recipient_id = str(inferred_agent.id)
                    except ValueError:
                        pass # Invalid UUID

                # If still no target agents, route to Coordinator (if one exists)
                if not target_agents:
                    from sqlalchemy import func
                    stmt = select(Agent).where(
                        Agent.team_id == team_uuid,
                        func.lower(Agent.role).in_(["coordinator", "orchestrator"])
                    ).limit(1)
                    result = await db.execute(stmt)
                    coordinator = result.scalar_one_or_none()
                    if coordinator:
                        target_agents.append(coordinator)
                    else:
                        # Fallback: if no coordinator, route to all agents in the team
                        stmt = select(Agent).where(Agent.team_id == team_uuid)
                        result = await db.execute(stmt)
                        agents = result.scalars().all()
                        target_agents.extend(agents)

            # Save message to short-term memory
            db_msg = Message(
                team_id=team_uuid,
                sender_id=sender_id,
                sender_name=resolved_sender_name,
                recipient_id=recipient_id,
                is_private=is_private,
                text=text,
                attachments=attachments or []
            )
            db.add(db_msg)
            await db.commit()

            # Broadcast the message over the EventBus for all subscribers (UI + other agents)
            topic = f"team:{team_id}"

            created_at_str = None
            if db_msg.created_at:
                created_at_str = db_msg.created_at.isoformat()
                if "+" not in created_at_str and not created_at_str.endswith("Z"):
                    created_at_str += "Z"

            await event_bus.publish(topic, {
                "type": "message",
                "id": str(db_msg.id),
                "sender_id": sender_id,
                "sender_name": resolved_sender_name,
                "recipient_id": recipient_id,
                "text": text,
                "is_private": is_private,
                "attachments": attachments or [],
                "timestamp": created_at_str
            })

            # Enqueue all mentioned agents (sequential per-agent, parallel across agents)
            # System broadcasts never enqueue agent tasks.
            if sender_id != "system":
                trigger_message_id = str(db_msg.id)
                for agent in target_agents:
                    await self._enqueue_agent(
                        agent, text, db, attachments,
                        trigger_message_id=trigger_message_id,
                        project_id=project_id,
                    )

    # ------------------------------------------------------------------
    # Queue machinery  (internal)
    # ------------------------------------------------------------------

    async def _enqueue_agent(
        self,
        agent: Agent,
        prompt_text: str,
        db_session: AsyncSession,
        attachments: Optional[List[Dict]] = None,
        trigger_message_id: Optional[str] = None,
        parent_coordinator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_message_id: Optional[str] = None,
        project_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ):
        """
        Enqueue a prompt into the agent's personal FIFO queue.

        Creates the queue and starts the long-lived worker coroutine the first
        time it is called for a given agent.  Subsequent calls simply drop the
        item into the existing queue - the worker picks it up as soon as it
        finishes whatever it is currently doing.

        Deduplication: if the *exact same prompt* is already sitting in the
        pending list for this agent (common when two system messages fire for
        the same assignment), it is silently dropped to prevent the agent from
        working on the same wakeup twice.
        """
        agent_id = str(agent.id)
        team_id = str(agent.team_id)

        async with self._get_enqueue_lock(agent_id):
            # Deduplication - avoid enqueuing identical back-to-back wakeups inside lock
            pending = self._pending.setdefault(agent_id, [])
            pending_keys = self._pending_keys.setdefault(agent_id, set())
            effective_key = dedupe_key or f"prompt:{prompt_text}"
            if effective_key in pending_keys:
                logger.debug("Deduplicated duplicate wakeup for agent %s", agent.name)
                return False

            # Ensure queue + worker exist
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
                self._pending[agent_id] = []
                self._pending_keys[agent_id] = set()
                # Build context snapshot for the worker (avoids closing over db_session)
                agent_snapshot = _AgentSnapshot(agent, db_session, project_id=project_id)
                worker_task = asyncio.create_task(
                    self._agent_worker(agent_id, agent_snapshot),
                    name=f"worker:{agent.name}",
                )
                self._workers[agent_id] = worker_task

                def _on_worker_done(t: asyncio.Task):
                    if not t.cancelled() and t.exception():
                        logger.exception(
                            "Worker for agent '%s' died unexpectedly: %s",
                            agent.name, t.exception(), exc_info=t.exception()
                        )
                    # Remove stale entries so the worker is recreated fresh on next trigger
                    if self._workers.get(agent_id) is not t:
                        return
                    self._queues.pop(agent_id, None)
                    self._workers.pop(agent_id, None)
                    self._pending.pop(agent_id, None)
                    self._pending_keys.pop(agent_id, None)

                worker_task.add_done_callback(_on_worker_done)

            # Enqueue the work item safely with capacity check
            from core.agent.run_budget import root_budget_id
            try:
                self._queues[agent_id].put_nowait({
                    "prompt_text": prompt_text,
                    "attachments": attachments or [],
                    "trigger_msg_id": trigger_message_id,
                    "parent_coordinator_id": parent_coordinator_id,
                    "task_id": task_id,
                    "parent_message_id": parent_message_id,
                    "dedupe_key": effective_key,
                    "enqueued_at": time.time(),
                    "root_budget_id": root_budget_id.get(),
                })
                self._pending[agent_id].append(prompt_text)
                self._pending_keys[agent_id].add(effective_key)
            except asyncio.QueueFull:
                logger.warning(
                    "Queue full for agent '%s' (maxsize=%d). Dropping prompt.",
                    agent.name, self._queues[agent_id].maxsize
                )
                raise asyncio.QueueFull(f"Agent {agent_id} is busy; retry the wakeup")

        # Broadcast queue depth change to UI
        depth = self._queues[agent_id].qsize()
        await event_bus.publish(f"team:{team_id}", {
            "type": "agent_queue_update",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "queue_depth": depth,
        })
        logger.info("Enqueued task for agent '%s' (queue depth: %d)", agent.name, depth)
        return True

    async def _agent_worker(self, agent_id: str, snapshot: "_AgentSnapshot"):
        """
        Long-lived FIFO worker for a single agent.

        Blocks on its queue, runs the agent loop to full completion for each
        item, then pulls the next.  Never exits unless a None sentinel is
        received (shutdown) or the task itself is cancelled.

        Exceptions inside a single agent loop are caught and logged - the
        worker then continues draining the queue.

        B5 - Watchdog: each queue item is bounded by MAX_TASK_TIMEOUT seconds
        (default 30 min). A stuck tool (hanging subprocess, browser) won't
        block the queue forever.

        B2 - Auto-restart: if the worker coroutine itself crashes unexpectedly
        (not from a per-item exception), it is restarted with exponential
        backoff up to 3 times before giving up.
        """
        import time
        queue = self._queues[agent_id]
        logger.info("Worker started for agent '%s'", snapshot.name)
        # Max time in seconds a single agent loop item may take (30 minutes)
        _MAX_TASK_TIMEOUT = 1800

        while True:
            try:
                item = await queue.get()
            except asyncio.CancelledError:
                logger.info("Worker for agent '%s' cancelled.", snapshot.name)
                break

            if item is _SENTINEL:
                queue.task_done()
                logger.info("Worker for agent '%s' received shutdown sentinel.", snapshot.name)
                break

            enqueued_at = None
            if isinstance(item, tuple):
                prompt_text, attachments, trigger_msg_id = item if len(item) == 3 else (item[0], item[1], None)
                parent_coordinator_id = None
                task_id = None
                parent_message_id = None
                dedupe_key = None
            else:
                prompt_text = item.get("prompt_text", "")
                attachments = item.get("attachments", [])
                trigger_msg_id = item.get("trigger_msg_id")
                parent_coordinator_id = item.get("parent_coordinator_id")
                task_id = item.get("task_id")
                parent_message_id = item.get("parent_message_id")
                dedupe_key = item.get("dedupe_key")
                enqueued_at = item.get("enqueued_at")

            if enqueued_at and task_id:
                queue_delay_ms = (time.time() - enqueued_at) * 1000
                try:
                    async with async_session() as db:
                        from core.tasks.board_service import record_task_metric
                        await record_task_metric(
                            db,
                            team_id=snapshot.team_id,
                            metric_type="queue_delay",
                            value=queue_delay_ms,
                            task_id=task_id,
                            agent_id=agent_id,
                            details={"delay_ms": round(queue_delay_ms, 2)},
                        )
                        await db.commit()
                except Exception as exc:
                    logger.debug("Could not record queue_delay metric: %s", exc)

            from core.agent.run_budget import root_budget_id
            budget_context = root_budget_id.set(item.get("root_budget_id") if isinstance(item, dict) else None)
            try:
                # B5: Watchdog timeout - prevent a single stuck task from
                # blocking the queue indefinitely.
                await asyncio.wait_for(
                    self._execute_agent_loop(
                        agent_id, snapshot, prompt_text, attachments, trigger_msg_id,
                        parent_coordinator_id, task_id, parent_message_id
                    ),
                    timeout=_MAX_TASK_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error(
                    "Watchdog: agent loop for '%s' exceeded %ds timeout. Killing task.",
                    snapshot.name, _MAX_TASK_TIMEOUT,
                )
            except Exception as exc:
                logger.exception(
                    "Unhandled exception in agent loop for '%s': %s",
                    snapshot.name, exc, exc_info=exc
                )
            finally:
                root_budget_id.reset(budget_context)
                # Remove from pending snapshot safely under lock
                async with self._get_enqueue_lock(agent_id):
                    pending = self._pending.get(agent_id, [])
                    if prompt_text in pending:
                        pending.remove(prompt_text)
                    if dedupe_key:
                        self._pending_keys.get(agent_id, set()).discard(dedupe_key)

                queue.task_done()

                # Broadcast updated queue depth
                remaining = queue.qsize()
                await event_bus.publish(f"team:{snapshot.team_id}", {
                    "type": "agent_queue_update",
                    "agent_id": agent_id,
                    "agent_name": snapshot.name,
                    "queue_depth": remaining,
                })

        logger.info("Worker exiting for agent '%s'", snapshot.name)


    async def _execute_agent_loop(
        self,
        agent_id: str,
        snapshot: "_AgentSnapshot",
        prompt_text: str,
        attachments: List[Dict],
        trigger_message_id: Optional[str] = None,
        parent_coordinator_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_message_id: Optional[str] = None,
    ):
        """
        Builds the ReACT agent instance and runs its loop to completion.
        Tracks the running task in self._running for external cancellation.
        """
        # Lazily resolve project_id if not captured at snapshot time
        project_id = snapshot.project_id
        if not project_id:
            async with async_session() as _db:
                stmt = select(Team).where(Team.id == uuid.UUID(snapshot.team_id))
                result = await _db.execute(stmt)
                team = result.scalar_one_or_none()
                project_id = str(team.project_id) if team else ""

        if snapshot.role.lower() in ("orchestrator", "coordinator") or "orchestrator" in snapshot.role.lower():
            from core.agent.coordinator import CoordinatorAgent
            react = CoordinatorAgent(
                agent_id=agent_id,
                team_id=snapshot.team_id,
                project_id=project_id,
                name=snapshot.name,
                role=snapshot.role,
                model=snapshot.model,
                system_prompt=snapshot.system_prompt,
                fallback_model=snapshot.fallback_model,
                reasoning_effort=snapshot.reasoning_effort,
                parent_coordinator_id=parent_coordinator_id,
                task_id=task_id,
            )
        else:
            from core.agent.react_agent import ReACTAgent
            react = ReACTAgent(
                agent_id=agent_id,
                team_id=snapshot.team_id,
                project_id=project_id,
                name=snapshot.name,
                role=snapshot.role,
                model=snapshot.model,
                system_prompt=snapshot.system_prompt,
                fallback_model=snapshot.fallback_model,
                reasoning_effort=snapshot.reasoning_effort,
                parent_coordinator_id=parent_coordinator_id,
                task_id=task_id,
                parent_message_id=parent_message_id,
            )

        if trigger_message_id:
            react.active_message_id = trigger_message_id

        token = CancellationToken()
        if parent_coordinator_id:
            from core.llm.config_manager import load_config
            if load_config().get("context_optimization", {}).get("worker_isolation", True):
                react.history_mode = "isolated"

        async def _run():
            async with async_session() as agent_db:
                await react.run_loop(agent_db, prompt_text, attachments, token, trigger_message_id=trigger_message_id)

        task = asyncio.create_task(_run(), name=f"loop:{snapshot.name}")
        self._running[agent_id] = (task, token)

        try:
            await task
        except asyncio.CancelledError:
            logger.info("Agent loop for '%s' was cancelled.", snapshot.name)
        finally:
            self._running[agent_id] = None

    # ------------------------------------------------------------------
    # Backward-compat shim kept for callers that still use _trigger_agent
    # directly (crud_routes.py create_task / update_task).
    # ------------------------------------------------------------------

    async def _trigger_agent(
        self,
        agent: Agent,
        prompt_text: str,
        db_session: AsyncSession,
        attachments: Optional[List[Dict]] = None,
        project_id: Optional[str] = None,
    ):
        """Thin shim - delegates to _enqueue_agent for sequential execution."""
        await self._enqueue_agent(agent, prompt_text, db_session, attachments, project_id=project_id)


class _AgentSnapshot:
    """
    Lightweight immutable snapshot of agent attributes needed to build the
    ReACT instance inside the worker.  Captured once at enqueue time so the
    worker doesn't need to hold a reference to the SQLAlchemy Agent ORM object
    (which may be detached from its session by the time the worker runs).
    """
    __slots__ = (
        "agent_id", "team_id", "project_id", "name", "role",
        "model", "system_prompt", "fallback_model", "reasoning_effort",
    )

    def __init__(self, agent: Agent, db_session: Optional[AsyncSession] = None, project_id: Optional[str] = None):
        self.agent_id = str(agent.id)
        self.team_id = str(agent.team_id)
        self.name = agent.name
        self.role = agent.role
        self.model = agent.model
        self.system_prompt = agent.system_prompt
        self.fallback_model = getattr(agent, "fallback_model", None)
        self.reasoning_effort = getattr(agent, "reasoning_effort", "none") or "none"
        self.project_id = str(project_id) if project_id else ""


# Singleton
message_router = MessageRouter()
