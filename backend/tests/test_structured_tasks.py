import pytest
import uuid
from core.tools.task_tools import task_tools
from core.memory.database import async_session
from core.memory.models import Team, Task

@pytest.mark.asyncio
async def test_create_task_with_structured_spec():
    # Setup test team
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_uuid = uuid.uuid4()
    async with async_session() as db:
        from core.memory.models import User, Project
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()
        project = Project(id=project_id, name="Test Project", owner_id=user_id)
        db.add(project)
        await db.flush()
        team = Team(id=team_uuid, name="Test Team", project_id=project_id)
        db.add(team)
        await db.commit()

    try:
        res = await task_tools.create_task(
            team_id=str(team_uuid),
            title="Implement Itinerary Scorer",
            description="Build preference models and scoring logic.",
            priority="high",
            target_files=["travey/src/planner.py", "travey/src/models/schemas.py"],
            contract_spec="UserPreferences(budget: float, dates: tuple) -> ItineraryResult",
            verification_command="pytest tests/test_planner.py"
        )
        assert "✓ Task created" in res

        # Verify task in DB contains structured spec
        async with async_session() as db:
            task = (await db.get(Task, uuid.UUID(res.split("ID: ")[1].split(")")[0])))
            assert task is not None
            assert "### Task Specification:" in task.description
            assert "**Target Files**: `travey/src/planner.py`, `travey/src/models/schemas.py`" in task.description
            assert "**Contract / Interfaces**: UserPreferences" in task.description
            assert "**Verification**: `pytest tests/test_planner.py`" in task.description
    finally:
        async with async_session() as db:
            from sqlalchemy import delete
            from core.memory.models import User, Project
            await db.execute(delete(Task).where(Task.team_id == team_uuid))
            await db.execute(delete(Team).where(Team.id == team_uuid))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
