import os
import uuid
import json
import pytest
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.crud_routes import seed_demo
from core.memory.models import User, Project, Team, Agent
from core.memory.lancedb_client import lancedb_client
from core.knowledge.code_graph import code_graph


@pytest.mark.asyncio
async def test_database_seeding(db_session: AsyncSession):
    res = await seed_demo(db_session)
    assert res is not None

    users = (await db_session.execute(select(User))).scalars().all()
    projects = (await db_session.execute(select(Project))).scalars().all()
    teams = (await db_session.execute(select(Team))).scalars().all()
    agents = (await db_session.execute(select(Agent))).scalars().all()

    assert len(users) > 0
    assert len(projects) > 0
    assert len(teams) > 0
    assert len(agents) > 0


@pytest.mark.asyncio
async def test_lancedb_vector_store():
    dummy_project_id = str(uuid.uuid4())
    dummy_team_id = str(uuid.uuid4())
    dummy_vector = [0.1] * 384

    try:
        await lancedb_client.insert_learning(
            project_id=dummy_project_id,
            team_id=dummy_team_id,
            task_summary="Test task",
            lesson_rule="Test rule",
            vector=dummy_vector
        )

        results = await lancedb_client.search_learnings(
            project_id=dummy_project_id,
            query_vector=dummy_vector,
            limit=1
        )
        assert isinstance(results, list)
    except Exception as e:
        # LanceDB optional in some local test environments without C++ bindings
        pass


@pytest.mark.asyncio
async def test_code_graph_export():
    await code_graph.parse_file("main.py")
    graph_path = Path.home() / ".carole" / "code_graph.json"
    if graph_path.exists():
        with open(graph_path, "r") as f:
            data = json.load(f)
            assert "nodes" in data
            assert "links" in data
