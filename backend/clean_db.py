import asyncio
from sqlalchemy import delete
from core.memory.database import async_session
from core.memory.models import Message

async def clean():
    async with async_session() as db:
        await db.execute(delete(Message).where(Message.is_intermediate == True))
        await db.commit()
        print('Cleaned!')

if __name__ == "__main__":
    asyncio.run(clean())
