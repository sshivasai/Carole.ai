"""
# backend/core/chat/message_router.py

This file defines the router that parses and directs incoming messages.

Responsibilities:
1. Parse incoming text for @name (group tag) and /@name (private tag) mentions.
2. Support multiple @mentions in a single message (fan-out to multiple agents).
3. If no @mention, optionally route to the Coordinator agent.
4. Persist messages to the DB and broadcast via EventBus.
5. Trigger target Agent ReACT loops via a per-agent FIFO sequential queue
   (Actor Model) — agents process their assigned tasks one at a time, in order,
   preventing race conditions on dependent tasks.
"""

import re
import uuid
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

# Type alias for a queue item: (prompt_text, attachments)
_QueueItem = Tuple[str, List[Dict]]
_SENTINEL = None  # Sent to a worker queue to signal graceful shutdown


class MessageRouter:
    def __init__(self):
        # Per-agent FIFO queues (Actor Model).
        # Each agent gets exactly ONE queue and ONE long-lived worker coroutine.
        self._queues: Dict[str, asyncio.Queue] = {}
        self._workers: Dict[str, asyncio.Task] = {}

        # Currently *executing* loop per agent — used for cancellation only.
        # Value is (asyncio.Task, CancellationToken) while running, None otherwise.
        self._running: Dict[str, Optional[Tuple[asyncio.Task, CancellationToken]]] = {}

        # Snapshot of pending prompts for queue introspection (REST /queue endpoint).
        self._pending: Dict[str, List[str]] = {}
        
        # Locks to prevent race conditions when enqueuing to a new agent
        self._enqueue_locks: Dict[str, asyncio.Lock] = {}

    def _get_enqueue_lock(self, agent_id: str) -> asyncio.Lock:
        if agent_id not in self._enqueue_locks:
            self._enqueue_locks[agent_id] = asyncio.Lock()
        return self._enqueue_locks[agent_id]

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
            self._pending[agent_id] = []
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
        # Find all private mentions (/@name) and public mentions (@name)
        private_matches = re.findall(r"/\@(\w+)", text)
        public_matches = re.findall(r"(?<!/)@(\w+)", text)

        is_private = len(private_matches) > 0
        mentioned_names = private_matches if is_private else public_matches

        # Persist message to database
        async with async_session() as db:
            target_agents: List[Agent] = []
            recipient_id = None

            try:
                team_uuid = uuid.UUID(team_id)
            except (ValueError, AttributeError):
                logger.error("Invalid team_id in route_message: %s", team_id)
                return

            # Verify the team actually exists in the database
            stmt = select(Team.id).where(Team.id == team_uuid)
            result = await db.execute(stmt)
            if result.scalar_one_or_none() is None:
                logger.warning("Team %s not found. Dropping message from %s.", team_id, sender_id)
                return

            # OPTIMIZATION: Resolve all mentioned agents in a single query
            # System broadcasts (e.g. member joined, task done) are informational logs and NEVER wake agents.
            if mentioned_names and sender_id != "system":
                from sqlalchemy import func
                stmt = select(Agent).where(
                    Agent.team_id == team_uuid,
                    func.lower(Agent.name).in_([n.lower() for n in mentioned_names])
                )
                result = await db.execute(stmt)
                agents = result.scalars().all()
                # Exclude the sender themselves from being triggered by self-mentions
                valid_targets = [a for a in agents if str(a.id) != sender_id]
                
                if valid_targets:
                    # Multi-mention Routing: Coordinator Priority
                    # If any mentioned agent is a coordinator, route ONLY to them.
                    coordinator = next((a for a in valid_targets if a.role.lower() in ["coordinator", "orchestrator"]), None)
                    
                    if coordinator:
                        target_agents.append(coordinator)
                        recipient_id = str(coordinator.id)
                    else:
                        # Fallback: Route ONLY to the first valid mentioned agent
                        for mention in mentioned_names:
                            primary_agent = next((a for a in valid_targets if a.name.lower() == mention.lower()), None)
                            if primary_agent:
                                target_agents.append(primary_agent)
                                recipient_id = str(primary_agent.id)
                                break

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
                    await self._enqueue_agent(agent, text, db, attachments, trigger_message_id=trigger_message_id)

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
    ):
        """
        Enqueue a prompt into the agent's personal FIFO queue.

        Creates the queue and starts the long-lived worker coroutine the first
        time it is called for a given agent.  Subsequent calls simply drop the
        item into the existing queue — the worker picks it up as soon as it
        finishes whatever it is currently doing.

        Deduplication: if the *exact same prompt* is already sitting in the
        pending list for this agent (common when two system messages fire for
        the same assignment), it is silently dropped to prevent the agent from
        working on the same wakeup twice.
        """
        agent_id = str(agent.id)
        team_id = str(agent.team_id)

        # Deduplication — avoid enqueuing identical back-to-back wakeups
        pending = self._pending.setdefault(agent_id, [])
        if prompt_text in pending:
            logger.debug("Deduplicated duplicate wakeup for agent %s", agent.name)
            return

        async with self._get_enqueue_lock(agent_id):
            # Ensure queue + worker exist
            if agent_id not in self._queues:
                self._queues[agent_id] = asyncio.Queue()
                self._pending[agent_id] = []
                # Build context snapshot for the worker (avoids closing over db_session)
                agent_snapshot = _AgentSnapshot(agent, db_session)
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
                    self._queues.pop(agent_id, None)
                    self._workers.pop(agent_id, None)
                    self._pending.pop(agent_id, None)

                worker_task.add_done_callback(_on_worker_done)

            # Enqueue the work item
            self._pending[agent_id].append(prompt_text)
            await self._queues[agent_id].put({
                "prompt_text": prompt_text,
                "attachments": attachments or [],
                "trigger_msg_id": trigger_message_id,
                "parent_coordinator_id": parent_coordinator_id,
                "task_id": task_id,
            })

        # Broadcast queue depth change to UI
        depth = self._queues[agent_id].qsize()
        await event_bus.publish(f"team:{team_id}", {
            "type": "agent_queue_update",
            "agent_id": agent_id,
            "agent_name": agent.name,
            "queue_depth": depth,
        })
        logger.info("Enqueued task for agent '%s' (queue depth: %d)", agent.name, depth)

    async def _agent_worker(self, agent_id: str, snapshot: "_AgentSnapshot"):
        """
        Long-lived FIFO worker for a single agent.

        Blocks on its queue, runs the agent loop to full completion for each
        item, then pulls the next.  Never exits unless a None sentinel is
        received (shutdown) or the task itself is cancelled.

        Exceptions inside a single agent loop are caught and logged — the
        worker then continues draining the queue.

        B5 — Watchdog: each queue item is bounded by MAX_TASK_TIMEOUT seconds
        (default 30 min). A stuck tool (hanging subprocess, browser) won't
        block the queue forever.

        B2 — Auto-restart: if the worker coroutine itself crashes unexpectedly
        (not from a per-item exception), it is restarted with exponential
        backoff up to 3 times before giving up.
        """
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

            if isinstance(item, tuple):
                prompt_text, attachments, trigger_msg_id = item if len(item) == 3 else (item[0], item[1], None)
                parent_coordinator_id = None
                task_id = None
            else:
                prompt_text = item.get("prompt_text", "")
                attachments = item.get("attachments", [])
                trigger_msg_id = item.get("trigger_msg_id")
                parent_coordinator_id = item.get("parent_coordinator_id")
                task_id = item.get("task_id")

            try:
                # B5: Watchdog timeout — prevent a single stuck task from
                # blocking the queue indefinitely.
                await asyncio.wait_for(
                    self._execute_agent_loop(
                        agent_id, snapshot, prompt_text, attachments, trigger_msg_id,
                        parent_coordinator_id, task_id
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
                # Remove from pending snapshot
                pending = self._pending.get(agent_id, [])
                if prompt_text in pending:
                    pending.remove(prompt_text)

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

        if snapshot.role == "Coordinator":
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
            )

        if trigger_message_id:
            react.active_message_id = trigger_message_id

        token = CancellationToken()

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
    ):
        """Thin shim — delegates to _enqueue_agent for sequential execution."""
        await self._enqueue_agent(agent, prompt_text, db_session, attachments)


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

    def __init__(self, agent: Agent, db_session: AsyncSession):
        self.agent_id = str(agent.id)
        self.team_id = str(agent.team_id)
        self.name = agent.name
        self.role = agent.role
        self.model = agent.model
        self.system_prompt = agent.system_prompt
        self.fallback_model = getattr(agent, "fallback_model", None)
        self.reasoning_effort = getattr(agent, "reasoning_effort", "none") or "none"
        # project_id is resolved lazily inside _execute_agent_loop
        self.project_id = ""


# Singleton
message_router = MessageRouter()
