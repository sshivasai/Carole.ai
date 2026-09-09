"""Offline audit probes against current source, without starting the application.

Run from the repository root:
    backend/venv/Scripts/python.exe backend/audit/reproduce_core_findings.py

These are diagnostic reproductions, not a passing application regression suite.
They compile selected, unchanged definitions from source to avoid application
startup, user configuration, databases, provider calls, and model downloads.
Dependencies are supplied explicitly where a boundary must be isolated.
"""

from __future__ import annotations

import ast
import asyncio
import copy
import dataclasses
import fnmatch
import hashlib
import json
import logging
import re
import sys
import types
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def definitions(relative_path, names, extra=None):
    """Load just named definitions/constants; never execute source imports."""
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    selected = []
    for node in tree.body:
        name = getattr(node, "name", None)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        if name in names:
            selected.append(node)
    module = types.ModuleType(f"audit_{len(sys.modules)}")
    sys.modules[module.__name__] = module
    module.__dict__.update(
        asyncio=asyncio, json=json, re=re, hashlib=hashlib, np=np,
        fnmatch=fnmatch, logger=logging.getLogger("audit"),
        deepcopy=copy.deepcopy, defaultdict=defaultdict, deque=deque,
        dataclass=dataclasses.dataclass, field=dataclasses.field,
        asdict=dataclasses.asdict, Path=Path,
    )
    module.__dict__.update(extra or {})
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    source = ast.fix_missing_locations(ast.Module(body=[future, *selected], type_ignores=[]))
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def method(relative_path, class_name, method_name, extra=None):
    """Compile an unchanged method in a minimal class; preserve decorators."""
    path = ROOT / relative_path
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    node = next(n for n in cls.body if getattr(n, "name", None) == method_name)
    holder = ast.ClassDef(name="Subject", bases=[], keywords=[], body=[node], decorator_list=[])
    ns = dict(json=json, re=re, Path=Path, logging=logging, **(extra or {}))
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    source = ast.fix_missing_locations(ast.Module(body=[future, holder], type_ignores=[]))
    exec(compile(source, str(path), "exec"), ns)
    return ns["Subject"]


async def main():
    findings = []

    def record(name, observed, defect):
        findings.append({"probe": name, "defect_reproduced": bool(defect), "observed": observed})

    chunks = definitions("core/knowledge/ast_parser.py", {"ASTChunk"})
    search = definitions(
        "core/knowledge/hybrid_search.py",
        {"tokenize_code", "BM25Index", "StaticCodeEmbedder", "ProjectIndex", "HybridCodeSearch"},
        {"ASTChunk": chunks.ASTChunk},
    )
    # Deterministic vectors replace model inference only, not indexing/ranking.
    search.StaticCodeEmbedder.encode = classmethod(lambda cls, texts: np.tile([[1.0, 0.0]], (len(texts), 1)))

    def chunk(name, code=None, path=None):
        return chunks.ASTChunk(name, "function", path or f"{name}.py", 1, 10, code or f"def {name}(): pass")

    idx = search.ProjectIndex("p")
    idx.update_file("a.py", [chunk("a", "x" * 120 + "old", "a.py")])
    changed = idx.update_file("a.py", [chunk("a", "x" * 120 + "new", "a.py")])
    record("chunk_body_update", {"update_detected": changed, "stored_tail": idx.file_chunks["a.py"][0].code[-3:]}, not changed)

    bm = search.BM25Index()
    bm.index_chunks([chunk("needle"), chunk("unrelated")])
    hits = bm.search("needle")
    record("lexical_nonmatches", hits, any(i == 1 for i, _ in hits))

    idx = search.ProjectIndex("partial")
    idx.update_file("a.py", [chunk("a")])
    idx.update_file("b.py", [chunk("b")])
    idx.file_embeddings.pop("b.py")
    idx.sync_index()
    hits = idx.search_vectors("a")
    record("partial_embedding_failure", {"chunks": len(idx.combined_chunks), "vectors": len(idx.combined_embeddings), "hits": hits}, not hits)

    hybrid = search.HybridCodeSearch()
    hybrid._ranker_loaded = True
    hybrid.index_workspace_chunks([chunk("needle", path=f"other/{i}.py") for i in range(6)] + [chunk("needle", path="target.py")], "filtered")
    hits = await hybrid.search("needle", "filtered", top_k=1, file_filter="target.py")
    record("filter_candidate_starvation", hits, not hits)

    history_mod = definitions("core/agent/message_history.py", {"MessageHistory"})
    history = history_mod.MessageHistory([{"role": "user", "content": "goal", "id": "m1", "created_at": datetime.now(timezone.utc)}])
    record("history_watermark_loss", history.get_messages(), "created_at" not in history.get_messages()[0])
    history.add_tool_results([{"tool_use_id": "never-called", "content": "invented result"}])
    record("orphan_result_accepted", history.get_messages()[-1], not history.has_pending_tool_calls)

    registry = types.ModuleType("core.tools.tool_registry")
    tool_categories = {"grep_search": "search", "glob_search": "search", "check_syntax": "code_analysis"}
    registry.ToolRegistry = types.SimpleNamespace(get=lambda name: types.SimpleNamespace(category=tool_categories.get(name, "filesystem")))
    tool_names = {"UNIVERSAL_ALLOWED_CATEGORIES", "ROLE_ALLOWED_CATEGORIES", "UNIVERSAL_CORE_TOOLS", "ROLE_DEFAULT_TOOLS", "INTENT_TRIGGERS", "resolve_active_tools"}
    agent = definitions("core/agent/react_agent.py", tool_names)
    with patch.dict(sys.modules, {"core.tools.tool_registry": registry}):
        cats, names = agent.resolve_active_tools("coder", "run tests and inspect git changes", {"check_syntax"})
        record("requested_tool_evicted", sorted(names), "check_syntax" not in names)
        cats, names = agent.resolve_active_tools("coder", "grep search for a pattern")
        record("search_category_unreachable", sorted(cats), "search" not in cats and "grep_search" not in names)

    counter = method("core/agent/react_agent.py", "ReACTAgent", "_estimate_tokens")()
    image_tokens = counter._estimate_tokens([{"role": "user", "content": [{"type": "image", "local_path": "unused.png"}]}])
    record("image_token_estimate", image_tokens, image_tokens < 100)

    formatter = method("core/llm/multi_model_router.py", "MultiModelRouter", "_format_messages_for_provider")()
    tool_history = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "c1", "name": "read_file", "input": {"relative_path": "a.py"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "file contents"}]},
    ]
    formatted = formatter._format_messages_for_provider(tool_history, "google")
    record("gemini_tool_history_loss", formatted, not formatted)

    dag = definitions("core/agent/workflow_dag.py", {"DAGCycleError", "WorkflowDAG"})
    ready = dag.WorkflowDAG.get_ready_tasks([{"id": "child", "status": "blocked", "depends_on": ["missing"]}])
    record("missing_dependency_ready", ready, len(ready) == 1)

    validator = definitions("core/tools/file_tools.py", {"_validate_code_syntax"})
    syntax_error = validator._validate_code_syntax("valid.js", "const regex = /[)]/;\n")
    record("valid_js_regex_rejected", syntax_error, syntax_error is not None)

    scratch = definitions("core/memory/scratchpad.py", {"_safe_agent_name"})
    base = PureWindowsPath("C:/workspace/team/scratchpads")
    unsafe_name = scratch._safe_agent_name("C:\\outside\\note")
    escaped = base / f"{unsafe_name}.md"
    record("scratchpad_windows_path_escape", str(escaped), not escaped.is_relative_to(base))

    # Scope a real source LanceDB filter routine to a fake table; no disk store.
    lance = definitions("core/memory/lancedb_client.py", {"LanceDBClient"})
    client = lance.LanceDBClient("unused")
    table_calls = []
    class FakeTable:
        def search(self, vector):
            return self

        def metric(self, metric):
            return self

        def where(self, predicate):
            return self

        def limit(self, limit):
            return self

        def to_list(self):
            return [{"id": "expected-match"}]

    def open_table(name):
        table_calls.append(name)
        return FakeTable()

    fake_db = types.SimpleNamespace(open_table=open_table)
    client._get_db = lambda: fake_db
    client._has_table = lambda db: True
    import uuid
    project_id, team_id = uuid.uuid4(), uuid.uuid4()
    result = client._sync_search([1.0], project_id, team_id, 1)
    control = client._sync_search([1.0], str(project_id), str(team_id), 1)
    record("uuid_memory_lookup", {"uuid_result": result, "string_result": control}, result == [] and bool(control))

    extraction_inputs, processed_ids = [], []

    async def completion(**kwargs):
        extraction_inputs.append(kwargs["messages"][0]["content"])
        return "NO_LESSONS"

    class Statement:
        def where(self, ids):
            processed_ids.extend(ids)
            return self

        def values(self, **kwargs):
            return self

    class FakeSession:
        async def execute(self, statement):
            pass

        async def commit(self):
            pass

    dream = method("core/memory/auto_dream.py", "AutoDreamWorker", "_process_claimed_messages", {
        "logger": logging.getLogger("audit"),
        "core": types.SimpleNamespace(config=types.SimpleNamespace(DEFAULT_FAST_MODEL="unused")),
        "llm_router": types.SimpleNamespace(generate_completion=completion),
        "CONSOLIDATION_PROMPT": "conversation={conversation}",
        "Message": types.SimpleNamespace(id=types.SimpleNamespace(in_=lambda ids: ids)),
        "update": lambda model: Statement(),
    })()
    dream._is_no_lessons = lambda text: True
    messages = [types.SimpleNamespace(id=str(i), sender_name="human", text=text)
                for i, text in enumerate(["remember first fact", "remember second fact", "x" * 9000])]
    await dream._process_claimed_messages(FakeSession(), types.SimpleNamespace(name="team"), messages, [m.id for m in messages])
    record("dream_skipped_input_marked_processed", {"extraction_input": extraction_inputs, "processed_ids": processed_ids}, extraction_inputs == ["conversation="] and len(processed_ids) == 3)

    print(json.dumps({"kind": "source-level diagnostic probes, not end-to-end tests", "findings": findings}, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
