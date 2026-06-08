"""
# backend/core/tools/memory_tools.py

Tools for managing an agent's long-term memory (Learning records).
"""

import uuid
import logging
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import async_session
from core.memory.models import Learning
from core.llm.multi_model_router import llm_router
from core.memory.lancedb_client import lancedb_client

logger = logging.getLogger("carole.memory_tools")


class MemoryTools:
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


# Singleton
memory_tools = MemoryTools()
