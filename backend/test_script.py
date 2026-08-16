import asyncio, uuid  
from sqlalchemy import select  
from core.memory.database import async_session  
from core.memory.models import ScheduledTask  
async def test():  
    async with async_session() as db:  
        stmt = select(ScheduledTask)  
        res = await db.execute(stmt)  
        task = res.scalars().first()  
        if task:  
            task.last_run_at = None  
            await db.commit()  
            try:  
                print(task.prompt)  
            except Exception as e:  
                print("ERROR:", type(e).__name__, e)  
asyncio.run(test())  
