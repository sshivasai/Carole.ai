"""SQL-backed, retryable invalidation of the derived memory vector index.

Jobs commit in the same transaction as source edits. A job reads the latest SQL
row, so retries cannot resurrect old content. Readers also verify SQL scope and
content before using a vector result (including after bulk SQL deletes).
"""
import asyncio
import logging

from sqlalchemy import select

from core.memory.database import async_session
from core.memory.models import Learning, MemoryIndexJob

logger = logging.getLogger("carole.memory_index")
_drain_lock = asyncio.Lock()


async def drain_memory_index(limit: int = 25) -> dict:
    from core.llm.multi_model_router import llm_router
    from core.memory.lancedb_client import lancedb_client

    completed = failed = 0
    async with _drain_lock:
        async with async_session() as db:
            jobs = list((await db.scalars(select(MemoryIndexJob).order_by(
                MemoryIndexJob.attempts, MemoryIndexJob.created_at, MemoryIndexJob.id).limit(limit))).all())
            for job in jobs:
                try:
                    row = await db.get(Learning, job.learning_id, populate_existing=True)
                    if row is None:
                        await lancedb_client.delete_learning(str(job.learning_id))
                    else:
                        embedding = await asyncio.wait_for(llm_router.generate_embeddings(
                            f"{row.task_summary} | {row.lesson_rule}"), timeout=20)
                        await lancedb_client.insert_learning(
                            learning_id=str(row.id), project_id=row.project_id,
                            team_id=row.team_id, task_summary=row.task_summary,
                            lesson_rule=row.lesson_rule, vector=embedding)
                    await db.delete(job)
                    completed += 1
                except Exception as exc:
                    job.attempts += 1
                    failed += 1
                    logger.warning("Memory indexing pending (%s)", type(exc).__name__)
                    # An unavailable embedding provider affects the entire batch.
                    await db.commit()
                    break
                await db.commit()
    return {"completed": completed, "failed": failed}


async def run_memory_index_worker():
    while True:
        try:
            await drain_memory_index()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Memory index worker cycle failed")
        await asyncio.sleep(30)
