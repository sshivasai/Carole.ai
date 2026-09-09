"""Regression tests using production modules, real SQL, files and LanceDB."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import numpy as np
import pytest
from sqlalchemy import delete, select

from core.agent.message_history import MessageHistory
from core.agent.react_agent import ReACTAgent
from core.knowledge.ast_parser import ASTChunk
from core.knowledge.hybrid_search import BM25Index, ProjectIndex, StaticCodeEmbedder
from core.llm.multi_model_router import MultiModelRouter, llm_router
from core.memory.auto_dream import AutoDreamWorker
from core.memory.embedding import EmbeddingVector
from core.memory.lancedb_client import LanceDBClient
from core.memory.models import User, Project, Team, Message, Learning, MemoryIndexJob, CompactionEvent
from core.tools.file_tools import FileTools, _validate_code_syntax
from core.tools.context import file_read_scope
from core.tools.memory_tools import memory_tools


@pytest.fixture
async def scope(db_session):
    user = User(email=f"reliability-{uuid.uuid4()}@example.com", hashed_password="unused")
    db_session.add(user)
    await db_session.flush()
    project = Project(name="Reliability", owner_id=user.id)
    db_session.add(project)
    await db_session.flush()
    team = Team(name="Tests", project_id=project.id)
    db_session.add(team)
    await db_session.commit()
    return project, team


def test_history_preserves_metadata_and_rejects_orphans_atomically():
    history = MessageHistory([{"role": "user", "content": "Goal", "id": "source", "created_at": "2026-09-08"}])
    assert history.get_messages()[0]["id"] == "source"
    history.add_assistant_text("", [{"id": "a", "name": "read_file", "input": {}}])
    before = history.get_messages()
    with pytest.raises(ValueError):
        history.add_tool_results([{"tool_use_id": "wrong", "content": "not requested"}])
    assert history.get_messages() == before
    history.add_tool_results([{"tool_use_id": "a", "content": "file contents"}])
    with pytest.raises(ValueError):
        history.add_tool_results([{"tool_use_id": "a", "content": "duplicate"}])
    with pytest.raises(ValueError):
        history.add_assistant_text("", [{"id": "a", "name": "read_file", "input": {}}])


def test_google_tool_roundtrip_and_schema_conversion():
    router = object.__new__(MultiModelRouter)
    history = MessageHistory([{"role": "user", "content": "read file"}])
    history.add_assistant_text("", [{"id": "call-a", "name": "read_file", "input": {"path": "a.py"}}])
    history.add_tool_results([{"tool_use_id": "call-a", "content": "return 1"}])
    formatted = router._format_messages_for_provider(history.get_messages(), "google")
    assert formatted[1]["parts"][0]["functionCall"]["args"] == {"path": "a.py"}
    assert formatted[2]["parts"][0]["functionResponse"]["name"] == "read_file"
    original = [{"type": "function", "function": {"name": "read_file", "description": "Read",
                 "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]
    for provider in ("anthropic", "google", "openai"):
        converted = router._adapt_tool_schemas(original, provider)
        assert router._adapt_tool_schemas(converted, "openai") == original


def chunk(path, code="return 1"):
    return ASTChunk("calculate", "function", path, 1, 2, code)


def test_search_does_not_return_nonmatches_or_lose_partial_vectors(monkeypatch):
    index = BM25Index()
    index.index_chunks([chunk("a.py")])
    assert index.search("unrelatedZebra") == []
    vectors = iter([np.array([[1., 0.]]), None])
    monkeypatch.setattr(StaticCodeEmbedder, "encode", lambda texts: next(vectors))
    project = ProjectIndex("test")
    project.update_file("a.py", [chunk("a.py")])
    project.update_file("b.py", [chunk("b.py")])
    project.sync_index()
    monkeypatch.setattr(StaticCodeEmbedder, "encode", lambda texts: np.array([[1., 0.]]))
    assert project.search_vectors("calculate")[0][0] == 0
    assert project.update_file("a.py", [chunk("a.py")]) is False
    assert project.update_file("a.py", [chunk("a.py", "x" * 120 + "changed")]) is True
    assert project.update_file("a.py", [chunk("a.py", "x" * 120 + "changed again")]) is True


@pytest.mark.parametrize("path,source", [
    ("regular.js", r"const pattern = /[)]/;"),
    ("template.ts", 'const value: string = `hello ${"world"}`;'),
    ("component.tsx", 'const View = () => <div>{/[/]/.test("/")}</div>;'),
])
def test_syntax_gate_accepts_valid_language_constructs(path, source):
    assert _validate_code_syntax(path, source) is None


async def test_file_reads_are_scoped_and_ranges_recover_omitted_content(tmp_path):
    files = FileTools()
    files.workspace_root = tmp_path
    (tmp_path / "large.txt").write_text("\n".join(str(i) for i in range(2000)), encoding="utf-8")
    token = file_read_scope.set("agent-one:run-one")
    try:
        assert "1999" in await files.read_file("large.txt")
        assert await files.read_file("large.txt") == files.FILE_UNCHANGED_STUB
    finally:
        file_read_scope.reset(token)
    token = file_read_scope.set("agent-two:run-two")
    try:
        assert "1999" in await files.read_file("large.txt")
        assert (await files.read_file("large.txt", force=True, start_line=1001, end_line=1002)).strip() == "1000\n1001"
    finally:
        file_read_scope.reset(token)


async def test_lancedb_idempotent_index_identity_and_sql_authority(scope, db_session, tmp_path):
    project, team = scope
    row = Learning(project_id=project.id, team_id=team.id, task_summary="Testing", lesson_rule="Run the tests")
    db_session.add(row)
    await db_session.commit()
    vectors = LanceDBClient(str(tmp_path / "vectors"))
    kwargs = dict(learning_id=str(row.id), project_id=project.id, team_id=team.id,
                  task_summary=row.task_summary, lesson_rule=row.lesson_rule)
    vector = EmbeddingVector([1., 0., 0.], "model-a")
    await vectors.insert_learning(**kwargs, vector=vector)
    await vectors.insert_learning(**kwargs, vector=vector)
    results = await vectors.search_learnings(vector, project.id, team.id)
    assert len(results) == 1
    assert await vectors.search_learnings(EmbeddingVector([1., 0., 0.], "model-b"), project.id, team.id) == []
    row.lesson_rule = "Updated lesson, indexing not yet complete"
    await db_session.commit()
    assert await vectors.search_learnings(vector, project.id, team.id) == []
    await db_session.execute(delete(Learning).where(Learning.id == row.id))
    await db_session.commit()
    assert await vectors.search_learnings(vector, project.id, team.id) == []


async def test_memory_survives_embedding_outage_and_cross_team_mutation_is_denied(scope, db_session, monkeypatch):
    project, team = scope
    monkeypatch.setattr(llm_router, "generate_embeddings", AsyncMock(side_effect=RuntimeError("offline")))
    result = await memory_tools.add_memory("deployment", "Run smoke tests", team_id=str(team.id))
    assert "Memory saved" in result
    row = await db_session.scalar(select(Learning).where(Learning.team_id == team.id))
    assert await db_session.scalar(select(MemoryIndexJob.id).where(MemoryIndexJob.learning_id == row.id))
    assert "Run smoke tests" in await memory_tools.search_memory("deployment", team_id=str(team.id))
    other = Team(name="Other", project_id=project.id)
    db_session.add(other)
    await db_session.commit()
    assert "Error" in await memory_tools.update_memory(str(row.id), "corrupt", team_id=str(other.id))
    assert "Error" in await memory_tools.forget_memory(str(row.id), team_id=str(other.id))
    await db_session.refresh(row)
    assert row.lesson_rule == "[MANUAL] Run smoke tests"


async def test_dream_does_not_discard_oversized_or_invalid_extractions(scope, db_session, monkeypatch):
    project, team = scope
    message = Message(team_id=team.id, sender_id="human", text="A" * 16000 + "TAIL_SENTINEL")
    db_session.add(message)
    await db_session.commit()
    worker = AutoDreamWorker()
    completion = AsyncMock(side_effect=["NO_LESSONS", "NO_LESSONS", "invalid output"])
    monkeypatch.setattr(llm_router, "generate_completion", completion)
    with pytest.raises(ValueError, match="Invalid memory extraction"):
        await worker._process_claimed_messages(db_session, team, [message], [message.id])
    await db_session.refresh(message)
    assert message.processed is False
    assert "TAIL_SENTINEL" in completion.call_args.kwargs["messages"][0]["content"]
    completion.side_effect = None
    completion.return_value = "NO_LESSONS"
    await worker._process_claimed_messages(db_session, team, [message], [message.id])
    await db_session.refresh(message)
    assert message.processed is True


async def test_public_history_excludes_private_messages_and_keeps_original_goal(scope, db_session):
    project, team = scope
    agent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    private = Message(team_id=team.id, sender_id=agent_id, text="PRIVATE_SENTINEL", is_private=True)
    original = Message(team_id=team.id, sender_id="human", text="ORIGINAL_GOAL", created_at=now - timedelta(minutes=2))
    recent = Message(team_id=team.id, sender_id="human", text="RECENT_REQUEST", created_at=now)
    db_session.add_all([private, original, recent])
    await db_session.flush()
    checkpoint = CompactionEvent(team_id=team.id, summary="Only summarized the middle", triggered_by="auto",
                                 created_at=now, covered_through_timestamp=now - timedelta(minutes=1))
    db_session.add(checkpoint)
    await db_session.commit()
    agent = ReACTAgent(agent_id, str(team.id), str(project.id), "Tester", "developer", "openrouter/free", "")
    history = await agent._load_conversation_history(db_session)
    text = json.dumps(history, default=str)
    assert "PRIVATE_SENTINEL" not in text
    assert "ORIGINAL_GOAL" in text and "RECENT_REQUEST" in text


async def test_embedding_outage_never_silently_changes_vector_space(monkeypatch):
    import core.config
    monkeypatch.setattr(core.config, "DEFAULT_EMBEDDING_MODEL", "openai/text-embedding-3-small")
    router = object.__new__(MultiModelRouter)
    router._embeddings_openai = AsyncMock(return_value=None)
    router._embeddings_gemini = AsyncMock(return_value=[1., 0.])
    with pytest.raises(RuntimeError, match="Embedding provider unavailable"):
        await router.generate_embeddings("test")
    router._embeddings_gemini.assert_not_called()


async def test_checkpoint_restart_preserves_goal_and_recent_evidence(scope, db_session, monkeypatch):
    project, team = scope
    agent = ReACTAgent(str(uuid.uuid4()), str(team.id), str(project.id), "Tester", "developer", "openrouter/free", "")
    now = datetime.now(timezone.utc)
    rows = [Message(team_id=team.id, sender_id="human" if i % 2 == 0 else agent.agent_id,
                    text="ORIGINAL_GOAL" if i == 0 else f"evidence-{i}",
                    created_at=now + timedelta(seconds=i)) for i in range(8)]
    db_session.add_all(rows)
    await db_session.commit()
    history = await agent._load_conversation_history(db_session)
    monkeypatch.setattr(agent, "_get_compaction_config", lambda: {"recent_messages_to_keep": 2})
    monkeypatch.setattr(agent, "_pre_compaction_memory_flush", AsyncMock())
    monkeypatch.setattr(llm_router, "generate_completion", AsyncMock(return_value="Completed the middle steps; recent verification is retained."))
    pruned = await agent._rolling_compact(history, db_session, triggered_by="emergency")
    assert len(pruned) < len(history)
    saved = await db_session.scalar(select(CompactionEvent).where(CompactionEvent.team_id == team.id))
    assert saved and saved.snapshot and saved.triggered_by == "auto"
    restarted = ReACTAgent(agent.agent_id, str(team.id), str(project.id), "Tester", "developer", "openrouter/free", "")
    loaded = json.dumps(await restarted._load_conversation_history(db_session), default=str)
    assert "ORIGINAL_GOAL" in loaded
    assert "evidence-6" in loaded and "evidence-7" in loaded
    assert "PRIVATE" not in loaded


async def test_provider_usage_wins_and_unknown_price_is_not_free(scope, db_session):
    from core.memory.models import TokenUsage
    project, team = scope
    await llm_router._log_usage("openrouter", "unknown/price-model", "a", [], "b",
                               str(project.id), str(team.id), None, None,
                               reported_usage={"prompt_tokens": 800, "completion_tokens": 120})
    usage = await db_session.scalar(select(TokenUsage).where(TokenUsage.team_id == team.id))
    assert usage.prompt_tokens == 800 and usage.completion_tokens == 120
    assert usage.total_tokens == 920 and usage.estimated_cost_usd is None


async def test_cross_user_http_memory_browser_and_process_access_is_denied(client, monkeypatch):
    from core.tools.shell_tools import process_registry
    accounts = []
    for _ in range(2):
        account = (await client.post("/api/auth/signup", json={"email": f"{uuid.uuid4()}@example.com", "password": "Password123!"})).json()
        headers = {"Authorization": "Bearer " + account["token"]}
        project = (await client.post("/api/projects", json={"name": "Same project name"}, headers=headers)).json()
        team = (await client.post("/api/teams", json={"name": "Same team name", "project_id": project["id"]}, headers=headers)).json()
        accounts.append((headers, project, team))
    owner, project, team = accounts[0]
    outsider, other_project, other_team = accounts[1]
    assert project["custom_workspace_path"] != other_project["custom_workspace_path"]
    projects = (await client.get("/api/projects", headers=outsider)).json()
    assert all(row["id"] != project["id"] for row in projects)
    agent = (await client.post("/api/agents", json={"name": "Owned", "role": "developer", "team_id": team["id"], "model": "openrouter/free"}, headers=owner)).json()
    memory = (await client.post("/api/learnings", json={"project_id": project["id"], "team_id": team["id"], "task_summary": "Private", "lesson_rule": "Owner data"}, headers=owner)).json()
    assert (await client.put(f"/api/learnings/{memory['id']}", json={"lesson_rule": "corrupt"}, headers=outsider)).status_code == 403
    assert (await client.delete(f"/api/learnings/{memory['id']}", headers=outsider)).status_code == 403
    assert (await client.get(f"/api/browser/screenshot?agent_id={agent['id']}", headers=outsider)).status_code == 403
    assert (await client.get(f"/api/observability/code-graph?project_id={project['id']}", headers=outsider)).status_code == 403
    from core.memory.auto_dream import dream_worker
    dream = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(dream_worker, "run_once", dream)
    assert (await client.post("/api/memory/dream/run", json={"team_id": team["id"]}, headers=outsider)).status_code == 403
    dream.assert_not_called()
    assert (await client.get(f"/api/skills/discovered?team_id={team['id']}", headers=outsider)).status_code == 403
    own_skill = await client.post("/api/skills/discovered", json={"team_id": team["id"], "name": "owned-skill", "content": "Use owned project instructions"}, headers=owner)
    assert own_skill.status_code == 200, own_skill.text
    assert (await client.post("/api/skills/toggle", json={"team_id": team["id"], "name": "owned-skill", "is_active": False}, headers=owner)).status_code == 200
    catalog = (await client.get(f"/api/skills/discovered?team_id={team['id']}", headers=owner)).json()
    assert next(s for s in catalog if s["name"] == "owned-skill")["is_active"] is False
    monkeypatch.setattr(process_registry, "list_processes", lambda **kwargs: [{"pid": 991, "team_id": team["id"]}])
    kill = AsyncMock()
    monkeypatch.setattr(process_registry, "kill_process", kill)
    assert (await client.post("/api/tasks/991/kill", headers=outsider)).status_code == 403
    kill.assert_not_called()
    result = await client.post(f"/api/scratchpad/{team['id']}", json={"agent_name": "C:escape", "content": "bad"}, headers=owner)
    assert result.status_code == 422
    for headers, _, owned_team in accounts:
        await client.post(f"/api/scratchpad/{owned_team['id']}", json={"target": "team", "content": owned_team["id"], "mode": "overwrite"}, headers=headers)
    pad = (await client.get(f"/api/scratchpad/{team['id']}/team", headers=owner)).json()
    assert team["id"] in pad["content"] and other_team["id"] not in pad["content"]


def test_browser_websocket_rejects_unauthenticated_stream():
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from main import app
    with pytest.raises(WebSocketDisconnect) as error:
        with TestClient(app).websocket_connect("/api/browser/stream?agent_id=global"):
            pass
    assert error.value.code == 4001


def test_skill_catalog_is_bounded_and_loads_instructions_on_demand():
    from core.skills.skill_manager import SkillManager
    from core.skills.skill_parser import SkillDefinition
    skills = [SkillDefinition(name=f"skill-{i}", description="Useful " * 50, instructions="LONG_INSTRUCTIONS" * 1000) for i in range(100)]
    block = SkillManager.build_skills_prompt_block(skills)
    assert len(block) < 6100
    assert "LONG_INSTRUCTIONS" not in block and "read_skill" in block


def test_skills_are_persistent_and_namesakes_are_independent(tmp_path):
    from core.skills.skill_manager import SkillManager
    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        SkillManager.save_skill_package("shared-name", "Follow project rules", workspace_root=root)
    SkillManager.toggle_skill_state("shared-name", False, first)
    assert not next(s for s in SkillManager.discover_filesystem_skills(first) if s.name == "shared-name").is_active
    assert next(s for s in SkillManager.discover_filesystem_skills(second) if s.name == "shared-name").is_active
    assert SkillManager.delete_filesystem_skill("shared-name", first)
    assert SkillManager.get_skill_content("shared-name", second)
    with pytest.raises(ValueError):
        SkillManager.delete_filesystem_skill("../", second)
    with pytest.raises(ValueError):
        SkillManager.save_skill_package("bad-name", "---\nname: different-name\n---\nInstructions", workspace_root=second)
    assert not (second / ".carole/skills/bad-name/SKILL.md").exists()


def test_code_ingestion_preserves_globals_decorators_and_bounds_chunks():
    from core.knowledge.knowledge_ingestor import _chunk_code, _chunk_markdown_and_docs
    code = "import os\nLIMIT = 7\n\n@decorator\ndef run():\n" + "    result = 1\n" * 1000 + "\nprint(LIMIT)\n"
    chunks = _chunk_code("module.py", code, max_words=50)
    joined = "\n".join(text for _, text in chunks)
    assert "import os" in joined and "LIMIT = 7" in joined
    assert "@decorator" in joined and "print(LIMIT)" in joined
    assert "".join(text for _, text in chunks).count("result = 1") == 1000
    assert all(len(text.split()) <= 50 for _, text in chunks)
    with pytest.raises(ValueError):
        _chunk_markdown_and_docs("a.md", "Words", max_words=10, overlap_words=10)


async def test_invalid_pdf_is_not_saved_as_knowledge(scope, db_session):
    from core.knowledge.knowledge_ingestor import ingest_file
    from core.memory.models import Learning
    project, team = scope
    result = await ingest_file(db_session, str(project.id), str(team.id), "broken.pdf", b"not a PDF document at all")
    assert "error" in result
    assert await db_session.scalar(select(Learning).where(Learning.project_id == project.id)) is None


def test_observation_cache_preserves_full_output_and_handles_unwritable_directory(tmp_path, monkeypatch):
    import core.agent.observation_cache as cache
    content = "head\n" + "middle output\n" * 2000 + "tail survives"
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "observations")
    preview = cache.cache_observation("read_file", content)
    files = list(cache.CACHE_DIR.glob("*.txt"))
    assert len(files) == 1 and files[0].read_text(encoding="utf-8") == content
    assert str(files[0]) in preview and "tail survives" in preview
    scoped = cache.cache_observation("read_file", content, scope="team:agent")
    artifact = next(cache._scope_dir("team:agent").glob("*.txt"))
    assert artifact.name in scoped
    excerpt = cache.read_observation(artifact.name, "team:agent", offset=len(content) - 13)
    assert "tail survives" in excerpt
    with pytest.raises(FileNotFoundError):
        cache.read_observation(artifact.name, "team:other-agent")
    with pytest.raises(ValueError):
        cache.read_observation("../escape.txt", "team:agent")
    occupied = tmp_path / "file"
    occupied.write_text("occupied")
    monkeypatch.setattr(cache, "CACHE_DIR", occupied / "invalid")
    assert "cache write failed" in cache.cache_observation("read_file", content)


async def test_code_graph_refreshes_partial_indexes_and_external_changes(tmp_path, monkeypatch):
    from core.knowledge.code_graph import CodeGraph
    from core.knowledge.hybrid_search import hybrid_code_search
    monkeypatch.setattr(CodeGraph, "start_listening_task", lambda self: None)
    monkeypatch.setattr(hybrid_code_search, "update_file_chunks", lambda *args, **kwargs: True)
    monkeypatch.setattr(hybrid_code_search, "remove_file", lambda *args, **kwargs: True)
    (tmp_path / "first.py").write_text("def first():\n    return 1\n")
    (tmp_path / "second.py").write_text("def second():\n    return 2\n")
    graph = CodeGraph(str(tmp_path))
    await graph.get_file_outline("first.py")
    assert {c.name for c in await graph.get_all_chunks()} >= {"first", "second"}
    (tmp_path / "second.py").write_text("def replacement():\n    return 'new'\n")
    (tmp_path / "first.py").unlink()
    names = {c.name for c in await graph.get_all_chunks()}
    assert "replacement" in names and "first" not in names and "second" not in names
    with pytest.raises(ValueError):
        await graph.parse_file("../outside.py")


async def test_message_pagination_keeps_same_timestamp_rows(client, owned_browser, db_session):
    from core.memory.models import Agent, Message
    agent = await db_session.get(Agent, uuid.UUID(owned_browser["agent_id"]))
    expected = set()
    for index in range(7):
        row = Message(team_id=agent.team_id, sender_id="human", text=f"pagination-{index}",
                      created_at=datetime(2020, 1, 1, tzinfo=timezone.utc), sequence=5)
        db_session.add(row)
        await db_session.flush()
        expected.add(str(row.id))
    await db_session.commit()
    seen = []
    before = None
    for _ in range(10):
        response = await client.get(f"/api/messages/{agent.team_id}", params={"limit": 3, **({"before": before} if before else {})}, headers=owned_browser["headers"])
        assert response.status_code == 200
        rows = response.json()
        if not rows:
            break
        seen.extend(row["id"] for row in rows)
        before = rows[0]["id"]
    assert expected <= set(seen)
    assert len(seen) == len(set(seen))


async def test_scheduler_advances_only_after_queue_accepts(scope, db_session, monkeypatch):
    from core.memory.models import Agent, ScheduledTask, Notification
    from core.agent.cron_worker import AgentCronWorker
    from core.chat.message_router import message_router
    project, team = scope
    agent = Agent(team_id=team.id, name="Scheduled", role="developer", model="openrouter/free", system_prompt="Work")
    db_session.add(agent)
    await db_session.flush()
    scheduled = ScheduledTask(team_id=team.id, agent_id=agent.id, name="Check", prompt="Run tests", cron_expression="* * * * *")
    db_session.add(scheduled)
    await db_session.commit()
    worker = AgentCronWorker()
    enqueue = AsyncMock(return_value=False)
    monkeypatch.setattr(message_router, "_enqueue_agent", enqueue)
    now = datetime.now(timezone.utc)
    await worker._trigger_agent(db_session, scheduled, now)
    assert scheduled.last_run_at is None
    enqueue.return_value = True
    await worker._trigger_agent(db_session, scheduled, now)
    assert scheduled.last_run_at == now
    assert enqueue.call_args.kwargs["agent"].id == agent.id
    assert enqueue.call_args.kwargs["trigger_message_id"]
    notice = await db_session.scalar(select(Notification).where(Notification.user_id == str(project.owner_id)))
    assert notice is not None


@pytest.mark.parametrize("versioned", [True, False])
async def test_database_upgrade_adds_snapshots_without_losing_messages(tmp_path, monkeypatch, versioned):
    import asyncio
    from alembic.config import Config
    from alembic import command
    from pathlib import Path
    from sqlalchemy import text, inspect
    from sqlalchemy.ext.asyncio import create_async_engine
    import core.memory.database as database
    url = f"sqlite+aiosqlite:///{(tmp_path / 'upgrade.db').as_posix()}"
    engine = create_async_engine(url)
    backend = Path(__file__).resolve().parents[1]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(database.Base.metadata.create_all)
            await connection.execute(text("ALTER TABLE compaction_events DROP COLUMN snapshot"))
            await connection.execute(text("ALTER TABLE compaction_events DROP COLUMN owner_agent_id"))
            await connection.execute(text("CREATE TABLE migration_sentinel (content TEXT)"))
            await connection.execute(text("INSERT INTO migration_sentinel VALUES ('preserve-me')"))
        cfg = Config(str(backend / "alembic.ini"))
        cfg.set_main_option("script_location", str(backend / "alembic"))
        cfg.set_main_option("sqlalchemy.url", url)
        if versioned:
            await asyncio.to_thread(command.stamp, cfg, "f3b8c2d1e4a5")
        monkeypatch.setattr(database, "engine", engine)
        monkeypatch.setattr(database, "DATABASE_URL", url)
        await database.init_db()
        async with engine.connect() as connection:
            columns = await connection.run_sync(lambda c: {row["name"] for row in inspect(c).get_columns("compaction_events")})
            assert {"snapshot", "owner_agent_id"} <= columns
            assert await connection.scalar(text("SELECT content FROM migration_sentinel")) == "preserve-me"
    finally:
        await engine.dispose()
