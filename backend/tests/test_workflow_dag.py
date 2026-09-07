import pytest
import uuid
from core.agent.workflow_dag import WorkflowDAG, DAGCycleError
from core.tools.task_tools import task_tools
from core.tools.tool_executor import tool_executor
from core.tools.context import ToolExecutionContext, CancellationToken
from core.memory.database import async_session
from core.memory.models import User, Project, Team, Agent, Task
from core.memory.auto_dream import auto_dream_worker


def test_dag_cycle_detection_unit():
    """Verify cycle detection handles acyclic trees and identifies cycle loops."""
    # 1. Linear graph: 3 -> 2 -> 1
    dep_map = {
        "task_1": [],
        "task_2": ["task_1"],
        "task_3": ["task_2"],
    }
    WorkflowDAG.validate_acyclic(dep_map)

    # 2. Diamond graph
    diamond_map = {
        "A": [],
        "B": ["A"],
        "C": ["A"],
        "D": ["B", "C"],
    }
    WorkflowDAG.validate_acyclic(diamond_map)

    # 3. Direct self-cycle
    with pytest.raises(DAGCycleError) as exc_info:
        WorkflowDAG.validate_acyclic({"A": ["A"]})
    assert "cycle" in str(exc_info.value).lower()

    # 4. Multi-node cycle: A -> B -> C -> A
    cycle_map = {
        "A": ["C"],
        "B": ["A"],
        "C": ["B"],
    }
    with pytest.raises(DAGCycleError) as exc_info:
        WorkflowDAG.validate_acyclic(cycle_map)
    assert "cycle" in str(exc_info.value).lower()


def test_dag_execution_waves():
    """Verify execution wave calculation organizes tasks topologically into parallel tiers."""
    tasks = [
        {"id": "A", "depends_on": []},
        {"id": "B", "depends_on": []},
        {"id": "C", "depends_on": ["A"]},
        {"id": "D", "depends_on": ["A", "B"]},
        {"id": "E", "depends_on": ["C", "D"]},
    ]

    waves = WorkflowDAG.get_execution_waves(tasks)
    assert len(waves) == 3

    wave_ids = [[node["id"] for node in w] for w in waves]
    # Wave 0: independent root tasks
    assert set(wave_ids[0]) == {"A", "B"}
    # Wave 1: dependent on A/B
    assert set(wave_ids[1]) == {"C", "D"}
    # Wave 2: dependent on C/D
    assert set(wave_ids[2]) == {"E"}


def test_dag_ready_tasks_and_cascade_failure():
    """Verify ready task resolution and cascade failure unrolling."""
    tasks = [
        {"id": "A", "status": "done", "depends_on": []},
        {"id": "B", "status": "in_progress", "depends_on": []},
        {"id": "C", "status": "blocked", "depends_on": ["A", "B"]},
        {"id": "D", "status": "blocked", "depends_on": ["A"]},
    ]

    # D is ready because A is done. C is NOT ready because B is in_progress.
    ready = WorkflowDAG.get_ready_tasks(tasks)
    ready_ids = [WorkflowDAG._get_field(t, "id").lower() for t in ready]
    assert "d" in ready_ids
    assert "c" not in ready_ids

    # Cascade failure: if A fails/blocks, both C and D are downstream of A
    cascade = WorkflowDAG.propagate_cascade_failure("A", tasks)
    cascade_ids = [WorkflowDAG._get_field(item[0], "id").lower() for item in cascade]
    assert set(cascade_ids) == {"c", "d"}


@pytest.mark.asyncio
async def test_task_tools_dag_lifecycle_and_unblocking():
    """Verify end-to-end task creation with depends_on, cycle rejection, and multi-dependency unblocking."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_uuid = uuid.uuid4()

    async with async_session() as db:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()
        project = Project(id=project_id, name="DAG Test Project", owner_id=user_id)
        db.add(project)
        await db.flush()
        team = Team(id=team_uuid, name="DAG Test Team", project_id=project_id)
        db.add(team)
        await db.commit()

    try:
        # Create Task A
        res_a = await task_tools.create_task(
            team_id=str(team_uuid),
            title="Task A",
            description="Root Task A",
        )
        assert "✓ Task created" in res_a
        id_a = res_a.split("ID: ")[1].split(")")[0]

        # Create Task B
        res_b = await task_tools.create_task(
            team_id=str(team_uuid),
            title="Task B",
            description="Root Task B",
        )
        assert "✓ Task created" in res_b
        id_b = res_b.split("ID: ")[1].split(")")[0]

        # Create Task C depending on [A, B]
        res_c = await task_tools.create_task(
            team_id=str(team_uuid),
            title="Task C",
            description="Child Task C depending on A and B",
            depends_on=[id_a, id_b],
        )
        assert "✓ Task created" in res_c
        id_c = res_c.split("ID: ")[1].split(")")[0]

        # Verify C is initially "blocked" because dependencies A & B are not done
        async with async_session() as db:
            task_c = await db.get(Task, uuid.UUID(id_c))
            assert task_c is not None
            assert task_c.status == "blocked"
            assert set(task_c.depends_on) == {id_a, id_b}

        # Attempt to create cycle: Task A depends on Task C -> should fail
        res_cycle = await task_tools.update_task(
            task_id=id_a,
            depends_on=[id_c],
        )
        assert "Cannot update task dependencies" in res_cycle or "cycle" in res_cycle.lower()

        # Complete Task A: Task C should STILL be blocked because Task B is unfinished
        res_done_a = await task_tools.update_task(
            task_id=id_a,
            status="done",
        )
        assert "updated:" in res_done_a
        async with async_session() as db:
            task_c = await db.get(Task, uuid.UUID(id_c))
            assert task_c.status == "blocked"

        # Complete Task B: All dependencies are now done -> Task C should automatically unblock to "todo"
        res_done_b = await task_tools.update_task(
            task_id=id_b,
            status="done",
        )
        assert "updated:" in res_done_b

        async with async_session() as db:
            task_c = await db.get(Task, uuid.UUID(id_c))
            assert task_c.status == "todo"

    finally:
        async with async_session() as db:
            from sqlalchemy import delete
            await db.execute(delete(Task).where(Task.team_id == team_uuid))
            await db.execute(delete(Team).where(Team.id == team_uuid))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


@pytest.mark.asyncio
async def test_plan_approval_guard():
    """Verify tool_executor blocks mutating tools when an agent's task plan is awaiting_approval."""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    team_uuid = uuid.uuid4()
    agent_uuid = uuid.uuid4()
    agent_id = str(agent_uuid)
    task_id = uuid.uuid4()

    async with async_session() as db:
        user = User(id=user_id, email=f"{user_id}@test.com", hashed_password="pw")
        db.add(user)
        await db.flush()
        project = Project(id=project_id, name="Plan Guard Project", owner_id=user_id)
        db.add(project)
        await db.flush()
        team = Team(id=team_uuid, name="Plan Guard Team", project_id=project_id)
        db.add(team)
        await db.flush()

        agent = Agent(
            id=agent_uuid,
            team_id=team_uuid,
            name="Nova",
            role="Coder",
            model="gpt-4o",
            system_prompt="You are Nova, a software developer.",
        )
        db.add(agent)
        await db.flush()

        task = Task(
            id=task_id,
            team_id=team_uuid,
            title="Guarded Plan Task",
            status="in_progress",
            assigned_agent_id=agent_uuid,
            plan_status="awaiting_approval",
        )
        db.add(task)
        await db.commit()

    try:
        exec_context = ToolExecutionContext(
            agent_id=agent_id,
            agent_name="Nova",
            team_id=str(team_uuid),
            cancellation_token=CancellationToken(),
            agent_role="Coder",
        )

        # 1. Attempt write_file while plan is awaiting approval -> must be blocked
        res_write = await tool_executor.execute(
            tool_name="write_file",
            arguments={"relative_path": "guarded.py", "content": "print('blocked')"},
            agent_id=agent_id,
            agent_name="Nova",
            team_id=str(team_uuid),
            permissions={},
            context=exec_context,
        )
        assert "AWAITING HUMAN APPROVAL" in res_write
        assert "Guarded Plan Task" in res_write

        # 2. Attempt execute_command while plan is awaiting approval -> must be blocked
        res_cmd = await tool_executor.execute(
            tool_name="execute_command",
            arguments={"command": "dir"},
            agent_id=agent_id,
            agent_name="Nova",
            team_id=str(team_uuid),
            permissions={},
            context=exec_context,
        )
        assert "AWAITING HUMAN APPROVAL" in res_cmd

        # 3. Read/view tool should NOT be blocked
        res_view = await tool_executor.execute(
            tool_name="read_file",
            arguments={"relative_path": "non_existent_file.py"},
            agent_id=agent_id,
            agent_name="Nova",
            team_id=str(team_uuid),
            permissions={},
            context=exec_context,
        )
        # Should not have the plan guard pause message
        assert "AWAITING HUMAN APPROVAL" not in res_view

        # 4. Now approve the plan and verify write is no longer blocked by the plan guard
        async with async_session() as db:
            task_db = await db.get(Task, task_id)
            task_db.plan_status = "approved"
            await db.commit()

        res_unblocked = await tool_executor.execute(
            tool_name="write_file",
            arguments={"relative_path": "test_unblocked.txt", "content": "hello"},
            agent_id=agent_id,
            agent_name="Nova",
            team_id=str(team_uuid),
            permissions={},
            context=exec_context,
        )
        # It shouldn't be paused by the plan guard anymore
        assert "AWAITING HUMAN APPROVAL" not in res_unblocked

    finally:
        async with async_session() as db:
            from sqlalchemy import delete
            await db.execute(delete(Task).where(Task.team_id == team_uuid))
            await db.execute(delete(Agent).where(Agent.id == agent_uuid))
            await db.execute(delete(Team).where(Team.id == team_uuid))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


@pytest.mark.asyncio
async def test_dream_worker_telemetry_and_manual_trigger():
    """Verify AutoDreamWorker telemetry status and run_once consolidation execution."""
    status = auto_dream_worker.get_status()
    assert "is_running" in status or "running" in status
    assert "interval_seconds" in status
    assert "total_consolidated_learnings" in status
    assert "total_entity_facts" in status

    # Run once without team_id -> full consolidation
    result = await auto_dream_worker.run_once()
    assert "status" in result
    assert result["status"] == "success"
    assert "teams_processed" in result

    # Check updated status
    updated_status = auto_dream_worker.get_status()
    assert updated_status["last_run_at"] is not None
