import asyncio
from core.memory.database import async_session
from core.api.file_routes import get_file_logs

async def run():
    async with async_session() as db:
        res = await get_file_logs(team_id="11111111-1111-1111-1111-111111111111", db=db)
        print("RESULT:", res)

asyncio.run(run())
