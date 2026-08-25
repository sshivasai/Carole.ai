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
from datetime import datetime, timezone
from sqlalchemy import select, update
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

    @property
    def interval(self):
        return self._interval_minutes if self._interval_minutes > 0 else core.config.DREAM_INTERVAL_MINUTES

    async def start(self):
        """Starts the periodic consolidation loop as a background coroutine.

        FIX B3: Uses absolute time scheduling so cycles run every N minutes
        from the START of each cycle, not N minutes after the cycle completes.
        A 2-minute consolidation run with a 15-minute interval will trigger
        at t=0, t=15, t=30 — not t=0, t=17, t=34.
        """
        self._running = True
        logger.info("💤 [Dream Worker] Started. Consolidating every %d minutes.", self.interval)

        while self._running:
            cycle_start = asyncio.get_running_loop().time()
            try:
                await self.consolidate_all_teams()
            except Exception as e:
                logger.exception("✗ [Dream Worker] Error during consolidation cycle: %s", e)

            # Sleep for the remainder of the interval, accounting for cycle duration
            elapsed = asyncio.get_running_loop().time() - cycle_start
            sleep_for = max(0.0, self.interval * 60 - elapsed)
            await asyncio.sleep(sleep_for)

    def stop(self):
        """Gracefully stops the consolidation loop."""
        self._running = False
        logger.info("💤 [Dream Worker] Stopped.")

    async def consolidate_all_teams(self):
        """Iterates all teams and consolidates unprocessed messages concurrently
        (up to 3 teams in parallel via semaphore)."""
        cycle_start = time.monotonic()
        async with async_session() as db:
            from core.memory.models import Learning
            from sqlalchemy import update, delete
            
            # Wave 5.4: Confidence decay (reduce by 0.1 each cycle)
            await db.execute(update(Learning).values(confidence_score=Learning.confidence_score - 0.1))
            
            # Find and prune dead memories (confidence < 0.2)
            stmt_prune = select(Learning.id).where(Learning.confidence_score < 0.2)
            prune_result = await db.execute(stmt_prune)
            prune_ids = prune_result.scalars().all()
            
            if prune_ids:
                from core.memory.lancedb_client import lancedb_client
                for p_id in prune_ids:
                    await lancedb_client.delete_learning(str(p_id))
                await db.execute(delete(Learning).where(Learning.id.in_(prune_ids)))
                logger.info("💤 [Dream] Pruned %d low-confidence memory rules.", len(prune_ids))
                
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
        conversation_lines = [
            f"[{msg.sender_name or msg.sender_id}]: {msg.text}" for msg in messages
        ]
        conversation_text = "\n".join(conversation_lines)

        # FIX H4: Token budget guard — cheap fast models (e.g. GPT-3.5, free OpenRouter
        # models) have context windows as small as ~4k tokens (~16k chars). Cap the
        # conversation text at ~8000 chars (≈2k tokens), trimming from the OLDEST
        # messages to preserve the most recent context for lesson extraction.
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

        # Parse and store extracted lessons and facts
        lessons, entity_facts = self._parse_lessons(extraction)
        if not lessons and not entity_facts:
            await db.commit()
            return

        stored = 0
        for task_summary, lesson_rule in lessons:
            try:
                combined_text = f"{task_summary} | {lesson_rule}"
                embedding = await llm_router.generate_embeddings(combined_text)

                # Deduplication check
                existing = await lancedb_client.search_learnings(
                    vector=embedding,
                    project_id=team.project_id,
                    team_id=team.id,
                    limit=1
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

        stored_facts = 0
        for key, value in entity_facts:
            try:
                # Deduplicate: Check if a fact with this key already exists for this team/project
                stmt = select(EntityMemory).where(
                    EntityMemory.key == key,
                    EntityMemory.team_id == team.id,
                    EntityMemory.project_id == team.project_id
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
                        value=value
                    )
                    db.add(fact)
                    stored_facts += 1
            except Exception as e:
                logger.error("💤 [Dream] Team '%s': Failed to store entity fact: %s", team.name, e)
                continue
                
        if stored_facts > 0:
            await db.commit()
            logger.info("💤 [Dream] Team '%s': Consolidated %d entity facts.", team.name, stored_facts)

    def _parse_lessons(self, text: str):
        """Parses JSON extraction output containing category, task_summary, and content."""
        import json
        
        import re
        
        text = text.strip()
        
        # Try to find a JSON array block if there is conversational filler
        match = re.search(r'\[\s*\{.*?\}\s*\]', text, re.DOTALL)
        if match:
            text = match.group(0)
        else:
            # Fallback for codeblock stripping
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        lessons = []
        entity_facts = []
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                return lessons, entity_facts
                
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                category = item.get("category", "MEMORY")
                
                if category == "ENTITY_FACT":
                    key = item.get("key")
                    value = item.get("value")
                    if key and value:
                        entity_facts.append((key, value))
                else:
                    task_summary = item.get("task_summary")
                    content = item.get("content")
                    
                    if task_summary and content:
                        # We store the category explicitly in the lesson_rule text
                        lesson_rule = f"[{category.upper()}] {content}"
                        lessons.append((task_summary, lesson_rule))
        except json.JSONDecodeError as e:
            logger.error("💤 [Dream] Failed to parse JSON extraction: %s\nText: %s", e, text)

        return lessons, entity_facts


# Singleton
dream_worker = AutoDreamWorker()
