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

        combined_text = f"{topic} | {content}"
        try:
            embedding = await llm_router.generate_embeddings(combined_text)
        except Exception as e:
            return f"Error generating embedding: {e}"

        # Deduplication check
        try:
            existing = await lancedb_client.search_learnings(
                vector=embedding,
                project_id=project_id,
                team_id=team_id,
                limit=1,
            )
            if existing and existing[0].get("_distance", 1.0) < 0.15:
                return (
                    f"✓ Memory not added — a very similar memory already exists: "
                    f"\"{existing[0].get('task_summary', '')[:100]}\""
                )
        except Exception:
            pass  # If dedup check fails, proceed with insert

        async with async_session() as db:
            try:
                p_uuid = uuid.UUID(project_id) if project_id else None
                t_uuid = uuid.UUID(team_id) if team_id else None
                a_uuid = uuid.UUID(agent_id) if agent_id else None

                learning = Learning(
                    project_id=p_uuid,
                    team_id=t_uuid,
                    agent_id=a_uuid,
                    task_summary=topic,
                    lesson_rule=f"[MANUAL] {content}",
                )
                db.add(learning)
                await db.commit()
                await db.refresh(learning)
                learning_id = str(learning.id)
            except Exception as e:
                return f"Error saving memory to database: {e}"

        try:
            await lancedb_client.insert_learning(
                learning_id=learning_id,
                project_id=project_id or "",
                team_id=team_id,
                task_summary=topic,
                lesson_rule=f"[MANUAL] {content}",
                vector=embedding,
            )
        except Exception as e:
            logger.warning("LanceDB insert failed for add_memory: %s", e)

        return f"✓ Memory saved (id={learning_id[:8]}): \"{topic[:60]}\""

    async def search_memory(
        self,
        query: str,
        project_id: Optional[str] = None,
        team_id: Optional[str] = None,
        limit: int = 5,
    ) -> str:
        """
        Search long-term memory for relevant past learnings.
        The agent can call this when it needs to recall past context that
        has been compacted out of its active conversation window.

        MemGPT equivalent: archival_memory_search()

        Returns the top matching memories ranked by semantic similarity.
        """
        if not query:
            return "Error: 'query' is required."

        try:
            embedding = await llm_router.generate_embeddings(query)
        except Exception as e:
            return f"Error generating search embedding: {e}"

        try:
            results = await lancedb_client.search_learnings(
                vector=embedding,
                project_id=project_id,
                team_id=team_id,
                limit=min(limit, 10),
            )
        except Exception as e:
            return f"Error searching memory: {e}"

        if not results:
            return "No relevant memories found."

        lines = [f"Found {len(results)} relevant memories:\n"]
        for i, r in enumerate(results, 1):
            dist = r.get("_distance", "?")
            similarity = f"{(1 - float(dist)) * 100:.0f}%" if isinstance(dist, (int, float)) else "?"
            lines.append(
                f"{i}. [{similarity} match] Context: {r.get('task_summary', 'N/A')}\n"
                f"   Lesson: {r.get('lesson_rule', 'N/A')}"
            )

        return "\n".join(lines)

    async def update_memory(self, memory_id: str, new_lesson: str) -> str:
        """
        Updates the lesson_rule of a specific memory record in the database
        and regenerates its semantic embedding in LanceDB.
        """
        try:
            mem_uuid = uuid.UUID(memory_id)
        except (ValueError, AttributeError):
            return f"Error: '{memory_id}' is not a valid memory ID."

        async with async_session() as db:
            stmt = select(Learning).where(Learning.id == mem_uuid)
            result = await db.execute(stmt)
            learning = result.scalar_one_or_none()

            if not learning:
                return f"Error: No memory record found with ID '{memory_id}'."

            # Generate new embedding for the updated lesson
            combined_text = f"{learning.task_summary} | {new_lesson}"
            try:
                new_embedding = await llm_router.generate_embeddings(combined_text)
            except Exception as e:
                return f"Error generating embedding: {e}"

            # Update SQLite record
            learning.lesson_rule = new_lesson
            await db.commit()

            # Update LanceDB record — delete old and re-insert
            try:
                await lancedb_client.delete_learning(memory_id)
                await lancedb_client.insert_learning(
                    learning_id=memory_id,
                    project_id=str(learning.project_id),
                    team_id=str(learning.team_id) if learning.team_id else None,
                    task_summary=learning.task_summary,
                    lesson_rule=new_lesson,
                    vector=new_embedding,
                )
            except Exception as e:
                logger.warning("LanceDB update failed for memory %s: %s", memory_id, e)
                # SQLite record is already updated — partial success

            return f"✓ Memory '{memory_id[:8]}' updated successfully."

    async def forget_memory(self, memory_id: str) -> str:
        """
        Deletes a specific memory record from the long-term database.
        """
        try:
            mem_uuid = uuid.UUID(memory_id)
        except (ValueError, AttributeError):
            return f"Error: '{memory_id}' is not a valid memory ID."

        async with async_session() as db:
            stmt = select(Learning).where(Learning.id == mem_uuid)
            result = await db.execute(stmt)
            learning = result.scalar_one_or_none()

            if not learning:
                return f"Error: No memory record found with ID '{memory_id}'."

            await db.delete(learning)
            await db.commit()

        # Also remove from vector store
        try:
            await lancedb_client.delete_learning(memory_id)
        except Exception as e:
            logger.warning("LanceDB delete failed for memory %s: %s", memory_id, e)

        return f"✓ Memory '{memory_id[:8]}' has been forgotten."

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
                t_uuid = uuid.UUID(team_id) if team_id else None
                p_uuid = uuid.UUID(project_id) if project_id else None

                # Upsert: check if key already exists for this exact scope
                stmt = select(EntityMemory).where(EntityMemory.key == key)
                if t_uuid:
                    stmt = stmt.where(EntityMemory.team_id == t_uuid)
                elif p_uuid:
                    stmt = stmt.where(EntityMemory.project_id == p_uuid)
                else:
                    stmt = stmt.where(EntityMemory.team_id.is_(None), EntityMemory.project_id.is_(None))

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
                stmt = delete(EntityMemory).where(EntityMemory.key == key)
                if t_uuid:
                    stmt = stmt.where(EntityMemory.team_id == t_uuid)
                else:
                    stmt = stmt.where(EntityMemory.team_id.is_(None))

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
