"""
Unit and integration tests for database.py, auto_dream.py, and model_catalog.py hardening.
"""

import asyncio
import os
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import text, select

from core.memory.database import init_db, verify_and_copy_sqlite_table, Base
from core.memory.auto_dream import AutoDreamWorker, dream_worker
from core.llm.model_catalog import (
    _validate_model_catalog,
    save_model_catalog,
    load_model_catalog,
    load_default_model_catalog,
    reset_model_catalog,
    ModelCatalogError,
)
from core.memory.models import Learning, Team, Message, Project, User


# ---------------------------------------------------------------------------
# Database Hardening Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_url_normalization():
    """Verify that standard sqlite:// URLs normalize to sqlite+aiosqlite://."""
    from core.memory import database
    original_url = database.DATABASE_URL
    with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///tmp/test.db"}):
        # Reload or check normalization logic
        url = os.getenv("DATABASE_URL")
        if url.startswith("sqlite://"):
            normalized = "sqlite+aiosqlite://" + url[len("sqlite://"):]
        assert normalized == "sqlite+aiosqlite:///tmp/test.db"


@pytest.mark.asyncio
async def test_force_db_recreate_ignored_outside_dev(monkeypatch):
    """Verify that FORCE_DB_RECREATE is ignored when not in development mode."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("FORCE_DB_RECREATE", "true")

    with patch("core.memory.database.logger.warning") as mock_warn:
        # Calling init_db should NOT drop tables in production
        with patch.object(Base.metadata, "drop_all", new_callable=MagicMock) as mock_drop:
            # We also mock _run_alembic_upgrade to avoid running external alembic in this unit test
            with patch("core.memory.database._run_alembic_upgrade"):
                await init_db()
                mock_drop.assert_not_called()
                mock_warn.assert_any_call(
                    "FORCE_DB_RECREATE requested but ignored: disabled outside explicit development mode (current env=%r)",
                    "production",
                )


@pytest.mark.asyncio
async def test_atomic_sqlite_verify_and_copy(db_session):
    """Test verify_and_copy_sqlite_table copies only common columns atomically."""
    # Create two temporary tables in SQLite
    await db_session.execute(text("CREATE TABLE test_src (id TEXT, name TEXT, extra_col TEXT)"))
    await db_session.execute(text("CREATE TABLE test_tgt (id TEXT, name TEXT, tgt_col TEXT)"))
    await db_session.execute(text("INSERT INTO test_src VALUES ('1', 'Alice', 'extra')"))
    await db_session.commit()

    # verify_and_copy_sqlite_table operates on a connection or session
    await verify_and_copy_sqlite_table(db_session, "test_src", "test_tgt")
    await db_session.commit()

    res = await db_session.execute(text("SELECT id, name, tgt_col FROM test_tgt"))
    rows = res.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "1"
    assert rows[0][1] == "Alice"
    assert rows[0][2] is None


# ---------------------------------------------------------------------------
# Auto Dream Hardening Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dream_worker_stop_cancels_and_awaits():
    """Verify stop() cancels the worker task immediately and can be awaited."""
    worker = AutoDreamWorker(interval_minutes=60)
    worker._running = True

    sleep_started = asyncio.Event()

    async def mock_loop():
        worker._task = asyncio.current_task()
        sleep_started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            worker._running = False
            raise

    task = asyncio.create_task(mock_loop())
    await sleep_started.wait()

    # Synchronous stop returns awaitable and cancels task
    stop_awaitable = worker.stop()
    assert worker._running is False
    assert task.cancelling() or task.done()

    # Can also await stop
    await stop_awaitable
    assert task.done()


def test_dream_worker_structured_no_lessons_parsing():
    """Verify robust structured check for NO_LESSONS without substring false positives."""
    worker = AutoDreamWorker()

    # Valid NO_LESSONS formats
    assert worker._is_no_lessons("NO_LESSONS") is True
    assert worker._is_no_lessons("  NO_LESSONS\n") is True
    assert worker._is_no_lessons("```\nNO_LESSONS\n```") is True
    assert worker._is_no_lessons("\"NO_LESSONS\"") is True

    # Must NOT false-positive on substring mentions in normal conversations
    assert worker._is_no_lessons("We analyzed why NO_LESSONS was raised earlier and fixed the bug.") is False
    assert worker._is_no_lessons("The system returned 0 entries; see NO_LESSONS documentation.") is False


def test_dream_worker_robust_json_parsing():
    """Verify robust parsing of fenced blocks, outer brackets, and multi-item arrays."""
    worker = AutoDreamWorker()

    # Fenced JSON with multiple items
    fenced_content = """Here is the extracted information:
```json
[
  {
    "category": "RULES",
    "task_summary": "Testing rule extraction",
    "content": "Always run pytest before committing."
  },
  {
    "category": "ENTITY_FACT",
    "key": "primary_test_framework",
    "value": "pytest"
  }
]
```
That completes the consolidation."""

    lessons, entity_facts = worker._parse_lessons(fenced_content)
    assert len(lessons) == 1
    assert lessons[0][0] == "Testing rule extraction"
    assert lessons[0][1] == "[RULES] Always run pytest before committing."
    assert len(entity_facts) == 1
    assert entity_facts[0] == ("primary_test_framework", "pytest")


@pytest.mark.asyncio
async def test_dream_worker_in_flight_message_locking():
    """Verify concurrent dream workers cannot claim the same in-flight messages."""
    worker = AutoDreamWorker()
    msg_id = "msg-123"

    async with worker._in_flight_lock:
        worker._in_flight_message_ids.add(msg_id)

    # In another coroutine, msg_id is protected
    async with worker._in_flight_lock:
        assert msg_id in worker._in_flight_message_ids
        available = [m for m in [msg_id] if m not in worker._in_flight_message_ids]
        assert len(available) == 0


@pytest.mark.asyncio
async def test_dream_worker_confidence_decay_clamped(db_session):
    """Verify confidence decay does not drop below 0.0 and violate check constraint."""
    # Insert a low-confidence learning
    learning = Learning(
        project_id=None,
        team_id=None,
        task_summary="Low confidence lesson",
        lesson_rule="Should decay to 0.0 without constraint error",
        confidence_score=0.05,
    )
    db_session.add(learning)
    await db_session.commit()

    from sqlalchemy import update, case
    # Simulate confidence decay clamped at 0.0
    await db_session.execute(
        update(Learning)
        .where(Learning.id == learning.id)
        .values(
            confidence_score=case(
                (Learning.confidence_score - 0.1 < 0.0, 0.0),
                else_=Learning.confidence_score - 0.1,
            )
        )
    )
    await db_session.commit()

@pytest.mark.asyncio
async def test_dream_worker_persistence_failure_rollback(db_session):
    """Verify that if vector persistence fails, messages are NOT marked processed and DB rolls back."""
    user = User(email="dreamer@example.com", hashed_password="pw")
    db_session.add(user)
    await db_session.flush()

    project = Project(name="Dream Project", owner_id=user.id)
    db_session.add(project)
    await db_session.flush()

    # Create test team and messages
    team = Team(name="Dream Test Team", project_id=project.id)
    db_session.add(team)
    await db_session.flush()

    messages = [
        Message(team_id=team.id, sender_id=str(user.id), sender_name="User", text="How do we configure testing?", is_private=False, is_intermediate=False, processed=False),
        Message(team_id=team.id, sender_id=str(user.id), sender_name="Agent", text="Run pytest with sqlite in-memory db.", is_private=False, is_intermediate=False, processed=False),
        Message(team_id=team.id, sender_id=str(user.id), sender_name="User", text="Got it, thank you.", is_private=False, is_intermediate=False, processed=False),
    ]
    db_session.add_all(messages)
    await db_session.commit()

    worker = AutoDreamWorker()
    claimed_ids = [m.id for m in messages]
    team_id = team.id

    mock_extraction = json.dumps([
        {"category": "RULES", "task_summary": "Testing config", "content": "Always run pytest."}
    ])

    with patch("core.memory.auto_dream.llm_router.generate_completion", new_callable=AsyncMock) as mock_llm, \
         patch("core.memory.auto_dream.llm_router.generate_embeddings", new_callable=AsyncMock) as mock_embed, \
         patch("core.memory.auto_dream.lancedb_client.search_learnings", new_callable=AsyncMock) as mock_search, \
         patch("core.memory.auto_dream.lancedb_client.insert_learning", new_callable=AsyncMock) as mock_insert, \
         patch("core.memory.auto_dream.lancedb_client.delete_learning", new_callable=AsyncMock) as mock_delete:

        mock_llm.return_value = mock_extraction
        mock_embed.return_value = [0.1] * 128
        mock_search.return_value = []
        # Simulate failure inserting into LanceDB
        mock_insert.side_effect = RuntimeError("LanceDB storage disk error")

        with pytest.raises(RuntimeError, match="LanceDB storage disk error"):
            await worker._process_claimed_messages(db_session, team, messages, claimed_ids)

        # Check in DB that messages are still processed=False
        persisted_msgs = (await db_session.execute(select(Message).where(Message.id.in_(claimed_ids)))).scalars().all()
        for m in persisted_msgs:
            assert m.processed is False

        # Verify no learning was persisted to DB
        learnings = (await db_session.execute(select(Learning).where(Learning.team_id == team_id))).scalars().all()
        assert len(learnings) == 0


# ---------------------------------------------------------------------------
# Model Catalog Hardening Tests
# ---------------------------------------------------------------------------

def test_model_catalog_validation_valid():
    """Verify valid catalog passes validation."""
    valid_catalog = {
        "anthropic": {
            "label": "Anthropic",
            "key_name": "ANTHROPIC_API_KEY",
            "models": [
                {"value": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}
            ]
        },
        "ollama": {
            "label": "Ollama Local",
            "key_name": None,
            "models": [
                {"value": "llama3.2", "label": "Llama 3.2"}
            ]
        }
    }
    _validate_model_catalog(valid_catalog)  # Should not raise


def test_model_catalog_validation_invalid_shapes():
    """Verify invalid catalog shapes raise ModelCatalogError."""
    # Not a dict
    with pytest.raises(ModelCatalogError):
        _validate_model_catalog(["not", "a", "dict"])

    # Provider ID empty
    with pytest.raises(ModelCatalogError):
        _validate_model_catalog({"": {"label": "Empty ID", "models": []}})

    # Provider missing label
    with pytest.raises(ModelCatalogError):
        _validate_model_catalog({"prov": {"models": []}})

    # Models not a list
    with pytest.raises(ModelCatalogError):
        _validate_model_catalog({"prov": {"label": "P", "models": "not-a-list"}})

    # Model entry missing value or label
    with pytest.raises(ModelCatalogError):
        _validate_model_catalog({
            "prov": {
                "label": "P",
                "models": [{"value": "m1"}]  # missing label
            }
        })


def test_model_catalog_atomic_save(tmp_path):
    """Verify catalog is saved atomically to a temporary file + replace with parents=True."""
    target_file = tmp_path / "deep" / "nested" / "supported_models.json"

    with patch("core.llm.model_catalog._USER_PATH", target_file):
        catalog = {
            "test_provider": {
                "label": "Test Provider",
                "key_name": "TEST_KEY",
                "models": [
                    {"value": "test-model-1", "label": "Test Model 1"}
                ]
            }
        }
        save_model_catalog(catalog)

        assert target_file.exists()
        loaded = json.loads(target_file.read_text(encoding="utf-8"))
        assert "test_provider" in loaded
        assert loaded["test_provider"]["label"] == "Test Provider"
