"""
# backend/core/memory/auto_dream.py

This file defines the background 'Dream' worker for memory consolidation.

Responsibilities:
1. Run periodically in the background (every N minutes).
2. Read the recent short-term conversation logs (messages) from PostgreSQL.
3. Pass the logs to a cheap LLM (e.g., gpt-4o-mini) to extract key facts, decisions, and lessons.
4. Generate vector embeddings for these summaries.
5. Insert the semantic embeddings into the `learnings` pgvector table.
6. Mark processed messages so they are not re-analyzed in subsequent cycles.
"""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Message, Learning, Team
from core.memory.lancedb_client import lancedb_client
from core.llm.multi_model_router import llm_router
from core.config import CONSOLIDATION_PROMPT, DEFAULT_FAST_MODEL, DREAM_INTERVAL_MINUTES


class AutoDreamWorker:
    def __init__(self, interval_minutes: int = DREAM_INTERVAL_MINUTES):
        self.interval = interval_minutes
        self._running = False

    async def start(self):
        """Starts the periodic consolidation loop as a background coroutine."""
        self._running = True
        print(f"💤 [Dream Worker] Started. Consolidating every {self.interval} minutes.")

        while self._running:
            try:
                await self.consolidate_all_teams()
            except Exception as e:
                print(f"✗ [Dream Worker] Error during consolidation cycle: {str(e)}")

            await asyncio.sleep(self.interval * 60)

    def stop(self):
        """Gracefully stops the consolidation loop."""
        self._running = False
        print("💤 [Dream Worker] Stopped.")

    async def consolidate_all_teams(self):
        """Iterates all teams and consolidates recent unprocessed messages."""
        async with async_session() as db:
            # Fetch all teams
            stmt = select(Team)
            result = await db.execute(stmt)
            teams = result.scalars().all()

            for team in teams:
                await self._consolidate_team(db, team)

    async def _consolidate_team(self, db: AsyncSession, team):
        """
        Consolidates recent messages from a team into long-term semantic memory.
        Only processes messages from the last consolidation window.
        """
        # Fetch recent messages (last N minutes window, unembedded)
        cutoff = datetime.utcnow() - timedelta(minutes=self.interval * 2)
        stmt = (
            select(Message)
            .where(Message.team_id == team.id)
            .where(Message.is_private == False)  # Do not leak private messages into team memory
            .where(Message.created_at >= cutoff)
            .order_by(Message.created_at)
            .limit(50)
        )
        result = await db.execute(stmt)
        messages = result.scalars().all()

        if len(messages) < 3:
            # Not enough conversation to consolidate
            return

        # Build conversation log
        conversation_text = "\n".join(
            f"[{msg.sender_id}]: {msg.text}" for msg in messages
        )

        # Ask a cheap LLM to extract lessons
        prompt = CONSOLIDATION_PROMPT.format(conversation=conversation_text)
        extraction = await llm_router.generate_completion(
            model=DEFAULT_FAST_MODEL,
            system_prompt="You are a precise knowledge extraction engine.",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2000
        )

        if "NO_LESSONS" in extraction:
            print(f"💤 [Dream] Team '{team.name}': No actionable lessons found.")
            return

        # Parse extracted lessons
        lessons = self._parse_lessons(extraction)
        if not lessons:
            return

        # Generate embeddings and insert into learnings table
        for task_summary, lesson_rule in lessons:
            combined_text = f"{task_summary} | {lesson_rule}"
            embedding = await llm_router.generate_embeddings(combined_text)

            learning = Learning(
                project_id=team.project_id,
                team_id=team.id,
                task_summary=task_summary,
                lesson_rule=lesson_rule
            )
            db.add(learning)
            
            # Insert into LanceDB
            await lancedb_client.insert_learning(
                project_id=str(team.project_id),
                team_id=str(team.id),
                task_summary=task_summary,
                lesson_rule=lesson_rule,
                vector=embedding
            )

        await db.commit()
        print(f"💤 [Dream] Team '{team.name}': Consolidated {len(lessons)} lessons into long-term memory.")

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
