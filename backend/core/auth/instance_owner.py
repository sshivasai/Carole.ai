"""Authority for capabilities that operate on the shared host.

For the local, single-user installation the first account is the instance
owner.  ``CAROLE_OWNER_ID`` remains an optional operator override for recovery
and tests.  Project ownership is still not an OS sandbox: only the instance
owner may install host code, change instance policy, or open a host shell.
"""
import os
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.auth.auth_middleware import require_auth
from core.memory.database import get_db
from core.memory.models import User


async def assert_instance_owner(user: dict, db: AsyncSession) -> None:
    owner_id = os.getenv("CAROLE_OWNER_ID", "").strip()
    if not owner_id:
        # UUID is a deterministic tie-breaker for databases imported with
        # identical/missing creation timestamps.
        owner_id = await db.scalar(
            select(User.id).order_by(User.created_at.asc(), User.id.asc()).limit(1)
        )
        owner_id = str(owner_id) if owner_id else ""
    if not owner_id:
        raise HTTPException(503, "Host capabilities require an account to be created first")
    if str(user.get("sub", user.get("id", ""))) != owner_id:
        raise HTTPException(403, "This operation requires the instance owner")


async def require_instance_owner(
    user: dict = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await assert_instance_owner(user, db)
    return user


async def assert_project_instance_owner(project_id: str) -> None:
    import uuid
    from sqlalchemy import select
    from core.memory.database import async_session
    from core.memory.models import Project, User
    async with async_session() as db:
        owner = await db.scalar(select(User.id).join(Project, Project.owner_id == User.id)
            .where(Project.id == uuid.UUID(str(project_id)), User.is_active.is_(True)))
        await assert_instance_owner({"sub": str(owner) if owner else ""}, db)


async def assert_team_instance_owner(team_id: str) -> None:
    import uuid
    from sqlalchemy import select
    from core.memory.database import async_session
    from core.memory.models import Team, Project, User
    async with async_session() as db:
        owner = await db.scalar(select(User.id).join(Project, Project.owner_id == User.id)
            .join(Team, Team.project_id == Project.id)
            .where(Team.id == uuid.UUID(str(team_id)), User.is_active.is_(True)))
        await assert_instance_owner({"sub": str(owner) if owner else ""}, db)
