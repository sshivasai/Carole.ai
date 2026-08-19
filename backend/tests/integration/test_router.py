import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import MultiModelRouter
from core.memory.models import TokenUsage, User, Project, Team, Agent


@pytest.mark.asyncio
async def test_router_usage_logging(db_session: AsyncSession):
    router = MultiModelRouter()

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_id = uuid.uuid4()
    agent_id = uuid.uuid4()

    user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
    db_session.add(user)
    await db_session.flush()

    project = Project(id=project_id, name="Test Project", owner_id=user_id)
    db_session.add(project)
    await db_session.flush()

    team = Team(id=team_id, name="Test Team", project_id=project_id)
    db_session.add(team)
    await db_session.flush()

    agent = Agent(
        id=agent_id, team_id=team_id, name="Test Agent",
        role="Test", model="openrouter/free", system_prompt="Test"
    )
    db_session.add(agent)
    await db_session.commit()

    # Log usage using TestSession
    from unittest.mock import patch
    from tests.conftest import TestSession

    with patch("core.memory.database.async_session", TestSession):
        await router._log_usage(
            provider="openai",
            model="gpt-4o-mini",
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Hello, test."}],
            response_text="Hello! How can I help?",
            project_id=str(project_id),
            team_id=str(team_id),
            agent_id=str(agent_id),
            agent_name="Test Agent"
        )

    # Verify token usage record
    result = await db_session.execute(
        select(TokenUsage).where(TokenUsage.project_id == project_id)
    )
    usage = result.scalars().first()
    assert usage is not None
    assert usage.model == "gpt-4o-mini"
    assert int(usage.total_tokens) > 0
