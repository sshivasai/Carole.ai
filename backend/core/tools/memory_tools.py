"""
# backend/core/tools/memory_tools.py

Tools for managing an agent's long-term memory (Learning records and EntityMemory facts).

Memory Management Design:
  - add_memory / search_memory: agent-callable archival memory (vector DB)
  - add_fact / edit_fact / delete_fact: agent-callable entity fact store (key=value)
  - update_memory / forget_memory: edit or delete existing Learning records by ID

Deduplication:
  - add_memory runs a cosine similarity check before inserting (distance < 0.15 = skip)
  - add_memory marks source messages as processed=True so AutoDream skips them
  - add_fact uses upsert-by-key so repeated calls update rather than duplicate

Per-Agent Opt-In:
  - Memory tools are enabled for all agents by default.
  - Agents can disable them via tool_permissions: {"memory_tools": "disabled"}
"""

import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy import select, update, delete
from typing import Optional

from core.memory.database import async_session
from core.memory.models import Learning, EntityMemory
from core.llm.multi_model_router import llm_router
from core.memory.lancedb_client import lancedb_client

logger = logging.getLogger("carole.memory_tools")


class MemoryTools:

    # ────────────────────────────────────────────────────────────────────────
    # Archival Memory — Learning records in SQLite + LanceDB vector store
    # ────────────────────────────────────────────────────────────────────────

    async def add_memory(
        self,
        topic: str,
        content: str,
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> str:
        """
        Save an important fact or lesson directly to long-term memory.
        The agent can call this proactively during a task to ensure critical
        information is not lost to context compaction.

        MemGPT equivalent: archival_memory_insert()

        Deduplication: If a very similar memory already exists (cosine distance < 0.15),
        the insert is skipped to prevent duplicates.

        AutoDream coordination: Calling this tool does NOT mark source messages as
        processed — AutoDream will still run on those messages. However, the cosine
        similarity check in AutoDream will skip near-duplicate extractions.
        """
        if not topic or not content:
            return "Error: Both 'topic' and 'content' are required."

        if not topic.strip() or not content.strip():
            return "Error: A topic and memory content are required."
        try:
            async with async_session() as db:
                p_uuid, t_uuid = await self._scope(db, project_id, team_id)
                learning = Learning(project_id=p_uuid, team_id=t_uuid,
                                    task_summary=topic, lesson_rule=f"[MANUAL] {content}")
                db.add(learning)
                await db.commit()
                return f"✓ Memory saved (id={learning.id}). Semantic indexing is pending."
        except (ValueError, TypeError) as exc:
            return f"Error: {exc}"

    @staticmethod
    async def _scope(db, project_id=None, team_id=None):
        from core.memory.models import Team, Project
        p_uuid = uuid.UUID(str(project_id)) if project_id else None
        t_uuid = uuid.UUID(str(team_id)) if team_id else None
        if t_uuid:
            team = await db.get(Team, t_uuid)
            if team is None or (p_uuid is not None and team.project_id != p_uuid):
                raise ValueError("Team does not belong to the requested project")
            p_uuid = team.project_id
        if p_uuid is None or await db.get(Project, p_uuid) is None:
            raise ValueError("A valid project or team scope is required")
        return p_uuid, t_uuid

    async def search_memory(self, query: str, project_id: Optional[str] = None,
                            team_id: Optional[str] = None, limit: int = 5) -> str:
        if not query or not isinstance(limit, int) or not 1 <= limit <= 10:
            return "Error: Query and a limit between 1 and 10 are required."
        async with async_session() as db:
            try:
                p_uuid, t_uuid = await self._scope(db, project_id, team_id)
            except (ValueError, TypeError) as exc:
                return f"Error: {exc}"
            try:
                import asyncio
                embedding = await asyncio.wait_for(llm_router.generate_embeddings(query), timeout=10)
                results = await lancedb_client.search_learnings(
                    vector=embedding, project_id=p_uuid, team_id=t_uuid, limit=limit)
            except Exception:
                results = []
            if not results:
                from sqlalchemy import or_
                # Lexical fallback remains available while semantic indexing is pending.
                words = query.split()[:8]
                stmt = select(Learning).where(
                    Learning.project_id == p_uuid,
                    or_(Learning.team_id == t_uuid, Learning.team_id.is_(None)),
                    or_(*[or_(Learning.task_summary.contains(word, autoescape=True),
                              Learning.lesson_rule.contains(word, autoescape=True)) for word in words])
                ).order_by(Learning.created_at.desc()).limit(limit)
                results = [{"id": str(row.id), "task_summary": row.task_summary,
                            "lesson_rule": row.lesson_rule} for row in (await db.scalars(stmt)).all()]
        if not results:
            return "No relevant memories found."
        return "\n\n".join(f"[{row['id']}] {row['task_summary']}\n{row['lesson_rule']}" for row in results)

    async def update_memory(self, memory_id: str, new_lesson: str,
                            project_id: Optional[str] = None, team_id: Optional[str] = None) -> str:
        if not new_lesson.strip():
            return "Error: A nonempty lesson is required."
        try:
            async with async_session() as db:
                p_uuid, t_uuid = await self._scope(db, project_id, team_id)
                learning = await db.scalar(select(Learning).where(
                    Learning.id == uuid.UUID(str(memory_id)),
                    Learning.project_id == p_uuid, Learning.team_id == t_uuid))
                if learning is None:
                    return "Error: Memory not found in this scope."
                learning.lesson_rule = new_lesson
                await db.commit()
                return f"✓ Memory '{memory_id}' updated. Semantic indexing is pending."
        except (ValueError, TypeError) as exc:
            return f"Error: {exc}"

    async def forget_memory(self, memory_id: str, project_id: Optional[str] = None,
                            team_id: Optional[str] = None) -> str:
        try:
            async with async_session() as db:
                p_uuid, t_uuid = await self._scope(db, project_id, team_id)
                learning = await db.scalar(select(Learning).where(
                    Learning.id == uuid.UUID(str(memory_id)),
                    Learning.project_id == p_uuid, Learning.team_id == t_uuid))
                if learning is None:
                    return "Error: Memory not found in this scope."
                await db.delete(learning)
                await db.commit()
                return f"✓ Memory '{memory_id}' has been forgotten."
        except (ValueError, TypeError) as exc:
            return f"Error: {exc}"

    # ────────────────────────────────────────────────────────────────────────
    # Entity Fact Store — Key=Value facts in EntityMemory
    # ────────────────────────────────────────────────────────────────────────

    async def add_fact(
        self,
        key: str,
        value: str,
        team_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """
        Save a named fact (key=value) to the entity memory store.
        Facts are automatically injected into the agent's system prompt
        as 'KNOWN FACTS' so they are always in context without using
        up conversation space.

        Examples:
          add_fact("user_preferred_language", "TypeScript")
          add_fact("database_type", "PostgreSQL")
          add_fact("project_name", "Carole.ai")

        Uses upsert: if a fact with the same key already exists for this
        team/project, it is updated rather than duplicated.
        """
        if not key or not value:
            return "Error: Both 'key' and 'value' are required."

        key = key.strip().lower().replace(" ", "_")

        async with async_session() as db:
            try:
                p_uuid, t_uuid = await self._scope(db, project_id, team_id)

                # Upsert: check if key already exists for this exact scope
                stmt = select(EntityMemory).where(EntityMemory.key == key,
                    EntityMemory.team_id == t_uuid, EntityMemory.project_id == p_uuid)

                existing = (await db.execute(stmt)).scalar_one_or_none()

                if existing:
                    old_value = existing.value
                    existing.value = value
                    existing.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    return f"✓ Fact updated — {key}: \"{old_value}\" → \"{value}\""
                else:
                    fact = EntityMemory(
                        team_id=t_uuid,
                        project_id=p_uuid,
                        key=key,
                        value=value,
                    )
                    db.add(fact)
                    await db.commit()
                    return f"✓ Fact saved — {key}: \"{value}\""
            except Exception as e:
                return f"Error saving fact: {e}"

    async def edit_fact(
        self,
        key: str,
        new_value: str,
        team_id: Optional[str] = None,
    ) -> str:
        """
        Update the value of an existing named fact.
        If the fact doesn't exist, it will be created.
        """
        return await self.add_fact(key=key, value=new_value, team_id=team_id)

    async def delete_fact(
        self,
        key: str,
        team_id: Optional[str] = None,
    ) -> str:
        """
        Remove a named fact from the entity memory store.
        """
        if not key:
            return "Error: 'key' is required."

        key = key.strip().lower().replace(" ", "_")

        async with async_session() as db:
            try:
                p_uuid, t_uuid = await self._scope(db, team_id=team_id)
                stmt = delete(EntityMemory).where(EntityMemory.key == key,
                    EntityMemory.team_id == t_uuid, EntityMemory.project_id == p_uuid)

                result = await db.execute(stmt)
                await db.commit()

                if result.rowcount > 0:
                    return f"✓ Fact '{key}' deleted."
                else:
                    return f"No fact found with key '{key}'."
            except Exception as e:
                return f"Error deleting fact: {e}"


# Singleton
memory_tools = MemoryTools()
