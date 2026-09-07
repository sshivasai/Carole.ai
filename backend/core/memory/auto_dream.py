"""
# backend/core/memory/auto_dream.py

Background 'Dream' worker for memory consolidation.

Responsibilities:
1. Run periodically in the background (every N minutes).
2. Read UNPROCESSED public conversation messages from the DB.
3. Pass messages to a cheap LLM to extract key lessons/decisions.
4. Generate vector embeddings and insert into LanceDB + Learning table.
5. Mark processed messages so they are NOT re-analyzed in future cycles.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Set, List, Tuple
from sqlalchemy import select, update, case, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Message, Learning, Team, EntityMemory
from core.memory.lancedb_client import lancedb_client
from core.llm.multi_model_router import llm_router
import core.config
from core.config import CONSOLIDATION_PROMPT

logger = logging.getLogger("carole.dream")

# Limit concurrent team consolidations to avoid overwhelming the LLM API
_CONSOLIDATION_SEMAPHORE = asyncio.Semaphore(3)


class AutoDreamWorker:
    """
    Background worker that runs periodically to consolidate old un-processed
    messages into dense vector embeddings (the 'Dream' cycle).
    """

    def __init__(self, interval_minutes: int = -1):
        self._interval_minutes = interval_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._in_flight_message_ids: Set[str] = set()
        self._in_flight_lock = asyncio.Lock()
        self._cycle_lock = asyncio.Lock()
        self._last_run_at: Optional[str] = None
        self._last_cycle_duration_secs: float = 0.0
        self._total_consolidated_learnings: int = 0
        self._total_entity_facts: int = 0
        self._last_error: Optional[str] = None

    @property
    def interval(self):
        # Dynamically evaluate agent_settings DREAM_INTERVAL_MINUTES from active config
        try:
            from core.llm.config_manager import load_config
            cfg = load_config()
            cfg_interval = cfg.get("agent_settings", {}).get("DREAM_INTERVAL_MINUTES")
            if cfg_interval is not None and int(cfg_interval) > 0:
                return int(cfg_interval)
        except Exception:
            pass
        return self._interval_minutes if self._interval_minutes > 0 else core.config.DREAM_INTERVAL_MINUTES

    def get_status(self) -> dict:
        """Returns operational telemetry for observability and monitoring."""
        return {
            "is_running": self._running,
            "running": self._running,
            "interval_minutes": self.interval,
            "interval_seconds": self.interval * 60,
            "last_run_at": self._last_run_at,
            "last_cycle_duration_secs": round(self._last_cycle_duration_secs, 2),
            "total_consolidated_learnings": self._total_consolidated_learnings,
            "total_entity_facts": self._total_entity_facts,
            "in_flight_messages": len(self._in_flight_message_ids),
            "last_error": self._last_error,
        }

    async def run_once(self, team_id: Optional[str] = None) -> dict:
        """Runs an immediate on-demand consolidation pass without waiting for background timer."""
        async with self._cycle_lock:
            start_time = time.monotonic()
            cycle_ts = datetime.now(timezone.utc).isoformat()
            self._last_run_at = cycle_ts
            self._last_error = None
            consolidated_teams = 0

            try:
                if team_id:
                    import uuid
                    team_uuid = uuid.UUID(str(team_id))
                    async with async_session() as db:
                        stmt = select(Team).where(Team.id == team_uuid)
                        team = (await db.execute(stmt)).scalar_one_or_none()
                        if not team:
                            return {"status": "error", "message": f"Team '{team_id}' not found"}
                        await self._consolidate_team(db, team)
                        consolidated_teams = 1
                else:
                    await self.consolidate_all_teams()
                    async with async_session() as db:
                        stmt = select(Team)
                        teams = (await db.execute(stmt)).scalars().all()
                        consolidated_teams = len(teams)

                duration = time.monotonic() - start_time
                self._last_cycle_duration_secs = duration
                return {
                    "status": "success",
                    "teams_processed": consolidated_teams,
                    "duration_secs": round(duration, 2),
                    "total_consolidated_learnings": self._total_consolidated_learnings,
                    "total_entity_facts": self._total_entity_facts,
                    "timestamp": cycle_ts,
                }
            except Exception as e:
                self._last_error = str(e)
                duration = time.monotonic() - start_time
                self._last_cycle_duration_secs = duration
                logger.exception("✗ [Dream Worker] Manual consolidation error: %s", e)
                return {
                    "status": "error",
                    "message": str(e),
                    "duration_secs": round(duration, 2),
                }

    async def start(self):
        """Starts the periodic consolidation loop as a background coroutine."""
        self._task = asyncio.current_task()
        self._running = True
        logger.info("💤 [Dream Worker] Started. Consolidating every %d minutes.", self.interval)

        try:
            while self._running:
                cycle_start = asyncio.get_running_loop().time()
                try:
                    await self.consolidate_all_teams()
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.exception("✗ [Dream Worker] Error during consolidation cycle: %s", e)

                if not self._running:
                    break

                # Sleep for the remainder of the interval, accounting for cycle duration
                elapsed = asyncio.get_running_loop().time() - cycle_start
                sleep_for = max(0.0, self.interval * 60 - elapsed)
                try:
                    await asyncio.sleep(sleep_for)
                except asyncio.CancelledError:
                    break
        except asyncio.CancelledError:
            logger.info("💤 [Dream Worker] Consolidation task cancelled.")
        finally:
            self._running = False
            logger.info("💤 [Dream Worker] Background loop exited.")

    def stop(self):
        """Gracefully stops the consolidation loop and cancels the sleeping worker task immediately.
        Supports both synchronous invocation (`worker.stop()`) and awaiting (`await worker.stop()`).
        """
        self._running = False
        task = self._task
        if task and not task.done():
            task.cancel()
        logger.info("💤 [Dream Worker] Stopped.")

        class _StopAwaitable:
            def __await__(self):
                async def _wait():
                    if task and not task.done():
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass
                return _wait().__await__()

        return _StopAwaitable()

    async def consolidate_all_teams(self):
        """Iterates all teams and consolidates unprocessed messages concurrently
        (up to 3 teams in parallel via semaphore)."""
        cycle_start = time.monotonic()
        async with async_session() as db:
            # Wave 5.4: Atomic confidence decay clamped at 0.0 (enforces ck_learnings_confidence)
            await db.execute(
                update(Learning).values(
                    confidence_score=case(
                        (Learning.confidence_score - 0.1 < 0.0, 0.0),
                        else_=Learning.confidence_score - 0.1,
                    )
                )
            )

            # Find and prune dead memories (confidence < 0.2) in a concurrency-safe manner
            stmt_prune = select(Learning.id).where(Learning.confidence_score < 0.2)
            prune_result = await db.execute(stmt_prune)
            prune_ids = prune_result.scalars().all()

            if prune_ids:
                await db.execute(delete(Learning).where(Learning.id.in_(prune_ids)))
                await db.commit()

                # Clean up vector database after DB commit succeeds
                for p_id in prune_ids:
                    try:
                        await lancedb_client.delete_learning(str(p_id))
                    except Exception as e:
                        logger.debug("💤 [Dream] LanceDB prune notice for %s: %s", p_id, e)
                logger.info("💤 [Dream] Pruned %d low-confidence memory rules.", len(prune_ids))
            else:
                await db.commit()

            result = await db.execute(select(Team))
            teams = result.scalars().all()

        team_count = len(teams)
        logger.info("💤 [Dream] Starting consolidation cycle for %d team(s).", team_count)

        async def _bounded_consolidate(team):
            async with _CONSOLIDATION_SEMAPHORE:
                async with async_session() as db:
                    try:
                        await self._consolidate_team(db, team)
                    except Exception as e:
                        logger.error("💤 [Dream] Error consolidating team '%s' (%s): %s", team.name, team.id, e)

        await asyncio.gather(*[_bounded_consolidate(team) for team in teams])

        elapsed = time.monotonic() - cycle_start
        self._last_run_at = datetime.now(timezone.utc).isoformat()
        self._last_cycle_duration_secs = elapsed
        logger.info("💤 [Dream] Consolidation cycle complete. Processed %d team(s) in %.2fs.", team_count, elapsed)

    async def _consolidate_team(self, db: AsyncSession, team):
        """
        Consolidates unprocessed public messages for a team into long-term memory.
        Locks in-flight messages so concurrent workers cannot process the same messages.
        Ensures atomic persistence across DB and LanceDB.
        """
        # Exclude messages currently in-flight across any worker
        async with self._in_flight_lock:
            in_flight_snapshot = set(self._in_flight_message_ids)

        stmt = (
            select(Message)
            .where(Message.team_id == team.id)
            .where(Message.is_private == False)    # Never leak private messages
            .where(Message.processed == False)     # Only unprocessed messages
            .where(Message.is_intermediate == False)
        )
        if in_flight_snapshot:
            stmt = stmt.where(~Message.id.in_(list(in_flight_snapshot)))

        stmt = stmt.order_by(Message.created_at).limit(50)
        result = await db.execute(stmt)
        messages = result.scalars().all()

        # Atomically claim messages to prevent concurrent workers from claiming them
        async with self._in_flight_lock:
            available_messages = [m for m in messages if m.id not in self._in_flight_message_ids]
            if len(available_messages) < 3:
                return
            claimed_ids = [m.id for m in available_messages]
            self._in_flight_message_ids.update(claimed_ids)

        try:
            await self._process_claimed_messages(db, team, available_messages, claimed_ids)
        finally:
            async with self._in_flight_lock:
                for mid in claimed_ids:
                    self._in_flight_message_ids.discard(mid)

    async def _process_claimed_messages(
        self,
        db: AsyncSession,
        team: Team,
        messages: List[Message],
        claimed_ids: List[str],
    ):
        """Processes a claimed batch of messages, extracting insights and coordinating writes."""
        # Build conversation log
        conversation_lines = [
            f"[{msg.sender_name or msg.sender_id}]: {msg.text}" for msg in messages
        ]
        conversation_text = "\n".join(conversation_lines)

        # Token budget guard
        _MAX_CONV_CHARS = 8000
        if len(conversation_text) > _MAX_CONV_CHARS:
            trimmed_lines = []
            running_len = 0
            for line in reversed(conversation_lines):
                if running_len + len(line) + 1 > _MAX_CONV_CHARS:
                    break
                trimmed_lines.append(line)
                running_len += len(line) + 1
            trimmed_lines.reverse()
            conversation_text = "\n".join(trimmed_lines)
            logger.debug(
                "💤 [Dream] Team '%s': Trimmed conversation to %d chars for LLM budget.",
                team.name, len(conversation_text),
            )

        # Extract lessons via LLM
        prompt = CONSOLIDATION_PROMPT.replace("{conversation}", conversation_text)
        try:
            extraction = await llm_router.generate_completion(
                model=getattr(core.config, "DEFAULT_FAST_MODEL", "openrouter/free"),
                system_prompt="You are a precise knowledge extraction engine.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error("💤 [Dream] Team '%s': LLM extraction failed: %s", team.name, e)
            # Do NOT mark messages as processed on LLM failure — leave them to be retried
            return

        # Check for structured NO_LESSONS response (avoiding false-positive substring matching)
        if self._is_no_lessons(extraction):
            logger.info("💤 [Dream] Team '%s': No actionable lessons found.", team.name)
            await db.execute(
                update(Message)
                .where(Message.id.in_(claimed_ids))
                .values(processed=True)
            )
            await db.commit()
            return

        # Parse structured lessons and entity facts
        lessons, entity_facts = self._parse_lessons(extraction)
        if not lessons and not entity_facts:
            logger.info("💤 [Dream] Team '%s': No actionable lessons parsed.", team.name)
            await db.execute(
                update(Message)
                .where(Message.id.in_(claimed_ids))
                .values(processed=True)
            )
            await db.commit()
            return

        # Coordinated writes: write to LanceDB and DB in tandem.
        # If persistence fails, roll back DB and delete any inserted LanceDB vectors.
        stored_lessons = 0
        stored_facts = 0
        inserted_lancedb_ids: List[str] = []

        try:
            for task_summary, lesson_rule in lessons:
                combined_text = f"{task_summary} | {lesson_rule}"
                embedding = await llm_router.generate_embeddings(combined_text)

                # Deduplication check in LanceDB
                existing = await lancedb_client.search_learnings(
                    vector=embedding,
                    project_id=team.project_id,
                    team_id=team.id,
                    limit=1,
                )
                if existing and existing[0].get("_distance", 1.0) < 0.15:
                    logger.debug("💤 [Dream] Team '%s': Skipping duplicate lesson", team.name)
                    continue

                learning = Learning(
                    project_id=team.project_id,
                    team_id=team.id,
                    task_summary=task_summary,
                    lesson_rule=lesson_rule,
                )
                db.add(learning)
                await db.flush()  # Populates learning.id

                await lancedb_client.insert_learning(
                    learning_id=str(learning.id),
                    project_id=str(team.project_id),
                    team_id=str(team.id),
                    task_summary=task_summary,
                    lesson_rule=lesson_rule,
                    vector=embedding,
                )
                inserted_lancedb_ids.append(str(learning.id))
                stored_lessons += 1

            for key, value in entity_facts:
                stmt = select(EntityMemory).where(
                    EntityMemory.key == key,
                    EntityMemory.team_id == team.id,
                    EntityMemory.project_id == team.project_id,
                )
                result = await db.execute(stmt)
                existing_fact = result.scalar_one_or_none()

                if existing_fact:
                    if existing_fact.value != value:
                        existing_fact.value = value
                        existing_fact.updated_at = datetime.now(timezone.utc)
                        stored_facts += 1
                else:
                    fact = EntityMemory(
                        project_id=team.project_id,
                        team_id=team.id,
                        key=key,
                        value=value,
                    )
                    db.add(fact)
                    stored_facts += 1

            # Only mark messages as processed IF all learnings and vectors have been persisted
            await db.execute(
                update(Message)
                .where(Message.id.in_(claimed_ids))
                .values(processed=True)
            )

            # Atomic commit of DB changes
            await db.commit()
            self._total_consolidated_learnings += stored_lessons
            self._total_entity_facts += stored_facts
            logger.info(
                "💤 [Dream] Team '%s': Successfully consolidated %d lessons and %d entity facts.",
                team.name, stored_lessons, stored_facts,
            )

        except Exception as exc:
            logger.error("💤 [Dream] Team '%s': Persistence failed during consolidation: %s", team.name, exc)
            # 1. Rollback DB session so no messages are marked processed and uncommitted learnings drop
            await db.rollback()

            # 2. Compensate LanceDB: delete any vectors inserted during this failed batch
            for v_id in inserted_lancedb_ids:
                try:
                    await lancedb_client.delete_learning(v_id)
                except Exception as del_err:
                    logger.warning("💤 [Dream] Failed to compensate LanceDB vector %s: %s", v_id, del_err)

            # Messages remain processed=False and will be retried in future cycles
            raise

    def _is_no_lessons(self, text: str) -> bool:
        """Determines if the LLM returned a structured NO_LESSONS answer without substring matching."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = [l for l in cleaned.splitlines() if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
        normalized = cleaned.strip("\"' \t\r\n").upper()
        return normalized in ("NO_LESSONS", "NO_LESSON", "NO-LESSONS", "NONE", "NO LESSONS")

    def _parse_lessons(self, text: str) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Parses JSON extraction output containing category, task_summary, and content."""
        lessons: List[Tuple[str, str]] = []
        entity_facts: List[Tuple[str, str]] = []

        cleaned = text.strip()

        # 1. Extract candidate blocks from markdown fences or raw text
        candidates = []
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fenced_match:
            candidates.append(fenced_match.group(1).strip())
        candidates.append(cleaned)

        parsed = None
        for candidate in candidates:
            # Direct parse
            try:
                parsed = json.loads(candidate)
                break
            except (json.JSONDecodeError, ValueError):
                pass

            # Slice outermost array [ ... ]
            start_arr = candidate.find("[")
            end_arr = candidate.rfind("]")
            if start_arr != -1 and end_arr != -1 and start_arr < end_arr:
                try:
                    parsed = json.loads(candidate[start_arr:end_arr + 1])
                    break
                except (json.JSONDecodeError, ValueError):
                    pass

            # Slice outermost object { ... }
            start_obj = candidate.find("{")
            end_obj = candidate.rfind("}")
            if start_obj != -1 and end_obj != -1 and start_obj < end_obj:
                try:
                    single = json.loads(candidate[start_obj:end_obj + 1])
                    parsed = [single] if isinstance(single, dict) else single
                    break
                except (json.JSONDecodeError, ValueError):
                    pass

        if parsed is None or not isinstance(parsed, list):
            return lessons, entity_facts

        for item in parsed:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "MEMORY")).strip().upper()

            if category == "ENTITY_FACT":
                key = item.get("key")
                value = item.get("value")
                if key and value and isinstance(key, str) and isinstance(value, str):
                    entity_facts.append((key.strip(), value.strip()))
            else:
                task_summary = item.get("task_summary")
                content = item.get("content")
                if task_summary and content and isinstance(task_summary, str) and isinstance(content, str):
                    ts_clean = task_summary.strip()
                    c_clean = content.strip()
                    if ts_clean and c_clean:
                        lesson_rule = f"[{category}] {c_clean}"
                        lessons.append((ts_clean, lesson_rule))

        return lessons, entity_facts


# Singleton
dream_worker = AutoDreamWorker()
auto_dream_worker = dream_worker
