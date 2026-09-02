import pytest
import uuid
from unittest.mock import patch
from core.tools.task_tools import task_tools
from core.memory.database import async_session
from core.memory.models import User, Project, Team, Agent, Task, Message
from core.chat.message_router import message_router

@pytest.mark.asyncio
async def test_pattern_1_unblock_engine_wakes_sherlock():
    """Verify Pattern 1: Completing Task 1 unblocks Task 2 and wakes Sherlock."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_id = uuid.uuid4()
    nova_id = uuid.uuid4()
    sherlock_id = uuid.uuid4()

    async with async_session() as db:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()

        project = Project(id=project_id, name="Travey Project", owner_id=user_id)
        db.add(project)
        await db.flush()

        team = Team(id=team_id, name="Swarm Team", project_id=project_id)
        db.add(team)
        await db.flush()

        nova = Agent(
            id=nova_id, team_id=team_id, name="Nova",
            role="Coder", model="openrouter/free", system_prompt="Coder"
        )
        sherlock = Agent(
            id=sherlock_id, team_id=team_id, name="Sherlock",
            role="Code Inspector", model="openrouter/free", system_prompt="QA"
        )
        db.add_all([nova, sherlock])
        await db.flush()

        # Task 1 (Nova)
        task1 = Task(
            team_id=team_id,
            title="Build Travey itinerary planner",
            assigned_agent_id=nova_id,
            status="in_progress"
        )
        db.add(task1)
        await db.flush()

        # Task 2 (Sherlock, blocked by Task 1)
        task2 = Task(
            team_id=team_id,
            title="QA Travey itinerary planner",
            assigned_agent_id=sherlock_id,
            status="todo",
            blocked_by_task_id=task1.id
        )
        db.add(task2)
        await db.commit()
        task1_id = task1.id
        task2_id = task2.id

    enqueued = []
    async def _spy_enqueue(agent, prompt_text, *args, **kwargs):
        enqueued.append((agent.name, prompt_text))

    with patch.object(message_router, "_enqueue_agent", side_effect=_spy_enqueue):
        try:
            # Nova completes task1
            res = await task_tools.update_task(
                task_id=str(task1_id),
                status="done",
                agent_name="Nova"
            )
            assert "done" in res

            # Verify task2 is unblocked in DB
            async with async_session() as db:
                refreshed_task2 = await db.get(Task, task2_id)
                assert refreshed_task2.blocked_by_task_id is None

            # Verify Sherlock was enqueued with [TASK_UNBLOCKED]
            assert len(enqueued) == 1
            agent_name, msg_text = enqueued[0]
            assert agent_name == "Sherlock"
            assert "[TASK_UNBLOCKED]" in msg_text
            assert "@Sherlock" in msg_text
            assert "Build Travey itinerary planner" in msg_text
            assert "QA Travey itinerary planner" in msg_text
        finally:
            async with async_session() as db:
                from sqlalchemy import delete
                await db.execute(delete(Task).where(Task.team_id == team_id))
                await db.execute(delete(Agent).where(Agent.team_id == team_id))
                await db.execute(delete(Team).where(Team.id == team_id))
                await db.execute(delete(Project).where(Project.id == project_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()


@pytest.mark.asyncio
async def test_pattern_2_orchestrator_alert_when_no_blocked_tasks():
    """Verify Pattern 2: Completing a task with no blocked tasks alerts @Archer."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_id = uuid.uuid4()
    archer_id = uuid.uuid4()
    nova_id = uuid.uuid4()

    async with async_session() as db:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()

        project = Project(id=project_id, name="Travey Project", owner_id=user_id)
        db.add(project)
        await db.flush()

        team = Team(id=team_id, name="Swarm Team", project_id=project_id)
        db.add(team)
        await db.flush()

        archer = Agent(
            id=archer_id, team_id=team_id, name="Archer",
            role="Orchestrator", model="openrouter/free", system_prompt="Orchestrator"
        )
        nova = Agent(
            id=nova_id, team_id=team_id, name="Nova",
            role="Coder", model="openrouter/free", system_prompt="Coder"
        )
        db.add_all([archer, nova])
        await db.flush()

        task1 = Task(
            team_id=team_id,
            title="Build Travey itinerary planner",
            assigned_agent_id=nova_id,
            status="in_progress"
        )
        db.add(task1)
        await db.commit()
        task1_id = task1.id

    enqueued = []
    async def _spy_enqueue(agent, prompt_text, *args, **kwargs):
        enqueued.append((agent.name, prompt_text))

    with patch.object(message_router, "_enqueue_agent", side_effect=_spy_enqueue):
        try:
            # Nova completes task1
            res = await task_tools.update_task(
                task_id=str(task1_id),
                status="done",
                agent_name="Nova"
            )
            assert "done" in res

            # Verify Archer was enqueued with [TASK_DONE]
            assert len(enqueued) == 1
            agent_name, msg_text = enqueued[0]
            assert agent_name == "Archer"
            assert "[TASK_DONE]" in msg_text
            assert "@Archer" in msg_text
            assert "Build Travey itinerary planner" in msg_text
            assert "Nova" in msg_text
        finally:
            async with async_session() as db:
                from sqlalchemy import delete
                await db.execute(delete(Task).where(Task.team_id == team_id))
                await db.execute(delete(Agent).where(Agent.team_id == team_id))
                await db.execute(delete(Team).where(Team.id == team_id))
                await db.execute(delete(Project).where(Project.id == project_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()


@pytest.mark.asyncio
async def test_pattern_3_peer_to_peer_mention_handoff():
    """Verify Pattern 3: Nova directly hands off to Sherlock via @Sherlock in chat."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_id = uuid.uuid4()
    nova_id = uuid.uuid4()
    sherlock_id = uuid.uuid4()

    async with async_session() as db:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()

        project = Project(id=project_id, name="Travey Project", owner_id=user_id)
        db.add(project)
        await db.flush()

        team = Team(id=team_id, name="Swarm Team", project_id=project_id)
        db.add(team)
        await db.flush()

        nova = Agent(
            id=nova_id, team_id=team_id, name="Nova",
            role="Coder", model="openrouter/free", system_prompt="Coder"
        )
        sherlock = Agent(
            id=sherlock_id, team_id=team_id, name="Sherlock",
            role="Code Inspector", model="openrouter/free", system_prompt="QA"
        )
        db.add_all([nova, sherlock])
        await db.commit()

    enqueued = []
    async def _spy_enqueue(agent, prompt_text, *args, **kwargs):
        enqueued.append((agent.name, prompt_text))

    with patch.object(message_router, "_enqueue_agent", side_effect=_spy_enqueue):
        try:
            # Nova sends a message tagging Sherlock in the team chat
            peer_handoff_text = "Implementation is finished in travey/. @Sherlock please run the test suite and verify edge cases."
            await message_router.route_message(
                text=peer_handoff_text,
                sender_id=str(nova_id),
                team_id=str(team_id),
                sender_name="Nova"
            )

            # Verify Sherlock was enqueued with the peer handoff message
            assert len(enqueued) == 1
            agent_name, msg_text = enqueued[0]
            assert agent_name == "Sherlock"
            assert "@Sherlock please run the test suite" in msg_text
        finally:
            async with async_session() as db:
                from sqlalchemy import delete
                await db.execute(delete(Message).where(Message.team_id == team_id))
                await db.execute(delete(Agent).where(Agent.team_id == team_id))
                await db.execute(delete(Team).where(Team.id == team_id))
                await db.execute(delete(Project).where(Project.id == project_id))
                await db.execute(delete(User).where(User.id == user_id))
                await db.commit()
