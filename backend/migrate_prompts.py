import asyncio
from sqlalchemy import select
from core.memory.database import async_session
from core.memory.models import Agent
from core.prompts import build_agent_system_prompt

async def migrate_prompts():
    async with async_session() as db:
        result = await db.execute(select(Agent))
        agents = result.scalars().all()
        for agent in agents:
            new_prompt = build_agent_system_prompt(agent.name, agent.role, agent.personality or "professional")
            if agent.custom_instructions:
                new_prompt += f"\n\nSPECIAL CUSTOM INSTRUCTIONS:\n{agent.custom_instructions}"
            if agent.skills and len(agent.skills) > 0:
                skills_text = "\n".join(f"- {s}" for s in agent.skills)
                new_prompt += f"\n\nSPECIALIZED SKILLS & TOOLKITS:\n{skills_text}"
            
            agent.system_prompt = new_prompt
            print(f"Updated prompt for agent {agent.name}")
        await db.commit()

if __name__ == "__main__":
    asyncio.run(migrate_prompts())
