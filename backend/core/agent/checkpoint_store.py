"""Optimistic checkpoint ownership: slow summaries cannot replace newer ones."""
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError


async def checkpoint_version(scope: str) -> int:
    from core.memory.database import async_session
    from core.memory.models import ContextCheckpointHead
    async with async_session() as db:
        version = await db.scalar(select(ContextCheckpointHead.version).where(ContextCheckpointHead.scope == scope))
        if version is not None:
            return version
        db.add(ContextCheckpointHead(scope=scope, version=0))
        try:
            await db.commit()
            return 0
        except IntegrityError:
            await db.rollback()
            return await db.scalar(select(ContextCheckpointHead.version).where(ContextCheckpointHead.scope == scope))


async def claim_checkpoint(db, scope: str, expected: int) -> bool:
    """Commit this update in the SAME transaction as the checkpoint insert."""
    from core.memory.models import ContextCheckpointHead
    result = await db.execute(update(ContextCheckpointHead).where(
        ContextCheckpointHead.scope == scope, ContextCheckpointHead.version == expected
    ).values(version=expected + 1))
    return result.rowcount == 1
