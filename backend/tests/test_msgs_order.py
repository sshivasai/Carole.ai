import asyncio
from core.memory.database import async_session
from sqlalchemy import select
from core.memory.models import Message, Team

async def test():
    async with async_session() as db:
        team = (await db.execute(select(Team).limit(1))).scalar_one_or_none()
        if not team:
            print("no teams")
            return
        
        # Copied from list_messages
        limit = 50
        stmt = (
            select(Message)
            .where(Message.team_id == team.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        res = await db.execute(stmt)
        msgs = res.scalars().all()
        msgs.reverse()

        for m in msgs:
            print(f"{m.created_at} | {m.is_intermediate} | {m.text[:30] if m.text else None}")

asyncio.run(test())
