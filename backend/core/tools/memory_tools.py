"""
# backend/core/tools/memory_tools.py

Tools for managing an agent's long-term memory.
"""
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.database import async_session
from core.memory.models import Learning
from core.llm.multi_model_router import llm_router

class MemoryTools:
    async def update_memory(self, memory_id: str, new_lesson: str) -> str:
        """
        Updates the lesson_rule of a specific memory record in the pgvector database,
        and regenerates its semantic embedding.
        """
        async with async_session() as db:
            stmt = select(Learning).where(Learning.id == memory_id)
            result = await db.execute(stmt)
            learning = result.scalar_one_or_none()

            if not learning:
                return f"Error: No memory record found with ID '{memory_id}'."

            # Generate new embedding
            combined_text = f"{learning.task_summary} | {new_lesson}"
            try:
                new_embedding = await llm_router.generate_embeddings(combined_text)
                learning.lesson_rule = new_lesson
                learning.embedding = new_embedding
                await db.commit()
                return f"Success: Memory '{memory_id}' updated successfully."
            except Exception as e:
                return f"Error updating memory: {e}"

    async def forget_memory(self, memory_id: str) -> str:
        """
        Deletes a specific memory record from the long-term pgvector database.
        """
        async with async_session() as db:
            stmt = select(Learning).where(Learning.id == memory_id)
            result = await db.execute(stmt)
            learning = result.scalar_one_or_none()

            if not learning:
                return f"Error: No memory record found with ID '{memory_id}'."

            await db.delete(learning)
            await db.commit()
            return f"Success: Memory '{memory_id}' has been forgotten."

# Singleton
memory_tools = MemoryTools()
