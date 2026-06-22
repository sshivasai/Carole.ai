import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.models import Skill

class SkillManager:
    """
    Manages CRUD operations and retrieval of dynamic skills.
    """

    @staticmethod
    async def get_team_skills(db: AsyncSession, team_id: str, active_only: bool = True) -> List[Skill]:
        """Retrieve all skills for a given team."""
        stmt = select(Skill).where(Skill.team_id == uuid.UUID(team_id))
        if active_only:
            stmt = stmt.where(Skill.is_active == True)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_skill(db: AsyncSession, skill_id: str) -> Optional[Skill]:
        """Retrieve a single skill by ID."""
        stmt = select(Skill).where(Skill.id == uuid.UUID(skill_id))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_skill(
        db: AsyncSession,
        team_id: str,
        name: str,
        description: str = "",
        system_prompt_addendum: str = "",
        tools: List[str] = None,
        mcp_servers: List[str] = None
    ) -> Skill:
        """Create a new skill."""
        new_skill = Skill(
            team_id=uuid.UUID(team_id),
            name=name,
            description=description,
            system_prompt_addendum=system_prompt_addendum,
            tools=tools or [],
            mcp_servers=mcp_servers or [],
            is_active=True
        )
        db.add(new_skill)
        await db.commit()
        await db.refresh(new_skill)
        return new_skill

    @staticmethod
    async def update_skill(
        db: AsyncSession,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt_addendum: Optional[str] = None,
        tools: Optional[List[str]] = None,
        mcp_servers: Optional[List[str]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Skill]:
        """Update an existing skill."""
        skill = await SkillManager.get_skill(db, skill_id)
        if not skill:
            return None

        if name is not None:
            skill.name = name
        if description is not None:
            skill.description = description
        if system_prompt_addendum is not None:
            skill.system_prompt_addendum = system_prompt_addendum
        if tools is not None:
            skill.tools = tools
        if mcp_servers is not None:
            skill.mcp_servers = mcp_servers
        if is_active is not None:
            skill.is_active = is_active

        await db.commit()
        await db.refresh(skill)
        return skill

    @staticmethod
    async def delete_skill(db: AsyncSession, skill_id: str) -> bool:
        """Delete a skill permanently."""
        skill = await SkillManager.get_skill(db, skill_id)
        if not skill:
            return False
        
        await db.delete(skill)
        await db.commit()
        return True
