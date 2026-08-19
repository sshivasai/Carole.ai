import asyncio
import sys
import os

# Ensure backend root is in sys.path when executed directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.memory.database import engine
from core.memory.models import Base

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database tables initialized successfully.")

if __name__ == "__main__":
    asyncio.run(main())
