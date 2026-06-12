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
import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Message, Learning, Team
from core.memory.lancedb_client import lancedb_client
from core.llm.multi_model_router import llm_router
from core.config import CONSOLIDATION_PROMPT, DEFAULT_FAST_MODEL, DREAM_INTERVAL_MINUTES

logger = logging.getLogger("carole.dream")

# Limit concurrent team consolidations to avoid overwhelming the LLM API
_CONSOLIDATION_SEMAPHORE = asyncio.Semaphore(3)


class AutoDreamWorker:
    def __init__(self, interval_minutes: int = DREAM_INTERVAL_MINUTES):
        self.interval = interval_minutes
        self._running = False

    async def start(self):
        """Starts the periodic consolidation loop as a background coroutine."""
        self._running = True
        logger.info("💤 [Dream Worker] Started. Consolidating every %d minutes.", self.interval)

        while self._running:
            try:
                await self.consolidate_all_teams()
            except Exception as e:
                logger.exception("✗ [Dream Worker] Error during consolidation cycle: %s", e)

            await asyncio.sleep(self.interval * 60)

    def stop(self):
        """Gracefully stops the consolidation loop."""
        self._running = False
        logger.info("💤 [Dream Worker] Stopped.")

    async def consolidate_all_teams(self):
        """Iterates all teams and consolidates unprocessed messages concurrently
        (up to 3 teams in parallel via semaphore)."""
        cycle_start = time.monotonic()
        async with async_session() as db:
            result = await db.execute(select(Team))
            teams = result.scalars().all()

        team_count = len(teams)
        logger.info("💤 [Dream] Starting consolidation cycle for %d team(s).", team_count)

        async def _bounded_consolidate(team):
            async with _CONSOLIDATION_SEMAPHORE:
                async with async_session() as db:
                    await self._consolidate_team(db, team)

        await asyncio.gather(*[_bounded_consolidate(team) for team in teams])

        elapsed = time.monotonic() - cycle_start
        logger.info("💤 [Dream] Consolidation cycle complete. Processed %d team(s) in %.2fs.", team_count, elapsed)

    async def _consolidate_team(self, db: AsyncSession, team):
        """
        Consolidates unprocessed public messages for a team into long-term memory.
        Only processes messages that have NOT been marked as processed yet.
        """
        # Fetch unprocessed public messages (up to 50 most recent)
        stmt = (
            select(Message)
            .where(Message.team_id == team.id)
            .where(Message.is_private == False)   # Never leak private messages
            .where(Message.processed == False)     # Only unprocessed messages
            .order_by(Message.created_at)
            .limit(50)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()

        if len(messages) < 3:
            # Not enough conversation to extract meaningful lessons
            return

        # Build conversation log
        conversation_text = "\n".join(
            f"[{msg.sender_name or msg.sender_id}]: {msg.text}" for msg in messages
        )

        # Extract lessons via LLM
        prompt = CONSOLIDATION_PROMPT.format(conversation=conversation_text)
        try:
            extraction = await llm_router.generate_completion(
                model=DEFAULT_FAST_MODEL,
                system_prompt="You are a precise knowledge extraction engine.",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error("💤 [Dream] Team '%s': LLM extraction failed: %s", team.name, e)
            return

        # Mark messages as processed REGARDLESS of whether lessons were extracted
        # so we don't keep retrying conversations that yield nothing useful
        message_ids = [msg.id for msg in messages]
        await db.execute(
            update(Message)
            .where(Message.id.in_(message_ids))
            .values(processed=True)
        )

        if "NO_LESSONS" in extraction:
            logger.info("💤 [Dream] Team '%s': No actionable lessons found.", team.name)
            await db.commit()
            return

        # Parse and store extracted lessons
        lessons = self._parse_lessons(extraction)
        if not lessons:
            await db.commit()
            return

        stored = 0
        for task_summary, lesson_rule in lessons:
            try:
                combined_text = f"{task_summary} | {lesson_rule}"
                embedding = await llm_router.generate_embeddings(combined_text)

                learning = Learning(
                    project_id=team.project_id,
                    team_id=team.id,
                    task_summary=task_summary,
                    lesson_rule=lesson_rule,
                )
                db.add(learning)

                await lancedb_client.insert_learning(
                    project_id=str(team.project_id),
                    team_id=str(team.id),
                    task_summary=task_summary,
                    lesson_rule=lesson_rule,
                    vector=embedding,
                )
                stored += 1
            except Exception as e:
                logger.error("💤 [Dream] Team '%s': Failed to store lesson: %s", team.name, e)
                continue

        await db.commit()
        logger.info(
            "💤 [Dream] Team '%s': Consolidated %d/%d lessons into long-term memory.",
            team.name, stored, len(lessons)
        )

    def _parse_lessons(self, text: str):
        """Parses TASK_SUMMARY/LESSON_RULE pairs from the LLM extraction output."""
        lessons = []
        lines = text.strip().split("\n")
        current_task = None

        for line in lines:
            line = line.strip()
            if line.startswith("TASK_SUMMARY:"):
                current_task = line[len("TASK_SUMMARY:"):].strip()
            elif line.startswith("LESSON_RULE:") and current_task:
                lesson_rule = line[len("LESSON_RULE:"):].strip()
                if current_task and lesson_rule:
                    lessons.append((current_task, lesson_rule))
                current_task = None

        return lessons


# Singleton
dream_worker = AutoDreamWorker()
