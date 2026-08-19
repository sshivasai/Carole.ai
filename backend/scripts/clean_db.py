import asyncio
import sys
import os

# Ensure backend root is in sys.path when executed directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete
from core.memory.database import async_session
from core.memory.models import Message

async def clean():
    async with async_session() as db:
        await db.execute(delete(Message).where(Message.is_intermediate == True))
        await db.commit()
        print("Cleaned intermediate messages!")

if __name__ == "__main__":
    asyncio.run(clean())
