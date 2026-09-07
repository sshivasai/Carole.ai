"""
# backend/tests/test_hybrid_rag_and_code_graph.py

Comprehensive test suite verifying:
1. Incremental hybrid search indexing and file-hash caching.
2. Smart import and relative dependency resolution.
3. Qualified symbol indexing (Parent.child) and lookup.
4. Class inheritance hierarchy tracking and AST bases extraction.
5. REST API endpoints (/api/search/code, /api/knowledge/symbols, /api/knowledge/graph, /api/knowledge/hierarchy).
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.knowledge.ast_parser import ASTChunk, parse_file_ast
from core.knowledge.hybrid_search import ProjectIndex, HybridCodeSearch
from core.knowledge.code_graph import CodeGraph, resolve_import_path
from core.tools.code_analysis_tools import CodeAnalysisTools


# ─────────────────────────────────────────────────────────────────────────────
# 1. Incremental Hybrid Search & Hash Caching
# ─────────────────────────────────────────────────────────────────────────────

def test_incremental_indexing_and_hash_caching():
    idx = ProjectIndex("test-project-1")
    
    file_a = "services/auth_service.py"
    chunk_a = [
        ASTChunk(
            name="authenticate_user",
            kind="function",
            file_path=file_a,
            start_line=1,
            end_line=10,
            code="def authenticate_user(token):\n    return True\n",
            params=["token"]
        )
    ]
    content_a = "def authenticate_user(token):\n    return True\n"

    # 1. First index should compute hash and return True (recomputed)
    recomputed = idx.update_file(file_a, chunk_a, content=content_a)
    assert recomputed is True
    assert file_a in idx.file_chunks
    assert file_a in idx.file_hashes

    # 2. Re-indexing identical content should be a cache hit and return False
    cached = idx.update_file(file_a, chunk_a, content=content_a)
    assert cached is False

    # 3. Synchronize index and perform search
    idx.sync_index()
    assert len(idx.combined_chunks) == 1
    assert idx.combined_chunks[0].name == "authenticate_user"

    bm25_res = idx.bm25.search("authenticate", top_k=5)
    assert len(bm25_res) > 0
    assert bm25_res[0][0] == 0

    # 4. Modifying content should update hash and return True
    modified_content = "def authenticate_user(token, scope):\n    return False\n"
    modified_chunk = [
        ASTChunk(
            name="authenticate_user",
            kind="function",
            file_path=file_a,
            start_line=1,
            end_line=12,
            code=modified_content,
            params=["token", "scope"]
        )
    ]
    recomputed2 = idx.update_file(file_a, modified_chunk, content=modified_content)
    assert recomputed2 is True

    # 5. Removing file should clear chunks and mark index dirty
    assert idx.remove_file(file_a) is True
    idx.sync_index()
    assert len(idx.combined_chunks) == 0


@pytest.mark.asyncio
async def test_hybrid_code_search_filtering():
    engine = HybridCodeSearch()
    pid = "filter-test-proj"

    chunks = [
        ASTChunk(name="UserController", kind="class", file_path="api/user.py", start_line=1, end_line=20, code="class UserController: pass"),
        ASTChunk(name="getUser", kind="function", file_path="api/user.py", start_line=21, end_line=30, code="def getUser(): pass"),
        ASTChunk(name="UserModel", kind="class", file_path="models/user.ts", start_line=1, end_line=15, code="class UserModel {}"),
    ]
    engine.index_workspace_chunks(chunks, project_id=pid)

    # Filter by file extension/path
    res_py = await engine.search("user", project_id=pid, top_k=10, file_filter=".py")
    assert len(res_py) > 0
    assert all(r["file_path"].endswith(".py") for r in res_py)

    # Filter by kind
    res_class = await engine.search("user", project_id=pid, top_k=10, kind="class")
    assert len(res_class) > 0
    assert all(r["kind"] == "class" for r in res_class)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Smart Import & Relative Dependency Resolution
# ─────────────────────────────────────────────────────────────────────────────

def test_smart_relative_import_resolution():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create simulated project structure
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "models.py").write_text("class Model: pass", encoding="utf-8")
        (root / "pkg" / "service.py").write_text("from .models import Model", encoding="utf-8")
        
        (root / "src" / "components").mkdir(parents=True)
        (root / "src" / "components" / "Button.tsx").write_text("export const Button = () => null;", encoding="utf-8")
        (root / "src" / "components" / "Card.tsx").write_text("import { Button } from './Button';", encoding="utf-8")

        (root / "src" / "utils").mkdir(parents=True)
        (root / "src" / "utils" / "index.ts").write_text("export const helper = 1;", encoding="utf-8")

        # 1. Python Relative Import (.models from pkg/service.py)
        res_py = resolve_import_path("pkg/service.py", ".models", root)
        assert "pkg/models.py" in res_py

        # 2. JS/TS Relative Import (./Button from src/components/Card.tsx)
        res_ts = resolve_import_path("src/components/Card.tsx", "./Button", root)
        assert "src/components/Button.tsx" in res_ts

        # 3. JS/TS Directory Index Import (../utils from src/components/Card.tsx)
        res_idx = resolve_import_path("src/components/Card.tsx", "../utils", root)
        assert "src/utils/index.ts" in res_idx

        # 4. Non-existent / external package should not create phantom files
        res_ext = resolve_import_path("pkg/service.py", "requests", root)
        assert len(res_ext) == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. Qualified Symbol Indexing & Lookup
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qualified_symbol_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cg = CodeGraph(workspace_root=str(root))

        code_content = """
class OrderProcessor:
    def process_payment(self, amount: float):
        return True

def standalone_payment():
    return False
"""
        test_file = root / "order.py"
        test_file.write_text(code_content, encoding="utf-8")

        await cg.parse_file("order.py", project_id="test_pid")

        # 1. Simple lookup for OrderProcessor
        class_defs = await cg.get_symbol_definitions("OrderProcessor", project_id="test_pid")
        assert len(class_defs) == 1
        assert class_defs[0]["kind"] == "class"

        # 2. Qualified lookup for OrderProcessor.process_payment
        qual_defs = await cg.get_symbol_definitions("OrderProcessor.process_payment", project_id="test_pid")
        assert len(qual_defs) == 1
        assert qual_defs[0]["name"] == "process_payment"
        assert qual_defs[0]["parent_symbol"] == "OrderProcessor"

        # 3. Simple lookup for process_payment
        simple_defs = await cg.get_symbol_definitions("process_payment", project_id="test_pid")
        assert len(simple_defs) == 1
        assert simple_defs[0]["parent_symbol"] == "OrderProcessor"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Class Inheritance Hierarchy & AST Bases Extraction
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_class_inheritance_hierarchy():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cg = CodeGraph(workspace_root=str(root))

        code_content = """
class BaseWorker:
    def run(self): pass

class AsyncWorker(BaseWorker):
    async def run(self): pass

class PriorityWorker(AsyncWorker):
    pass
"""
        test_file = root / "workers.py"
        test_file.write_text(code_content, encoding="utf-8")

        await cg.parse_file("workers.py", project_id="test_pid")

        # 1. Inspect AsyncWorker hierarchy
        info = await cg.get_class_hierarchy("AsyncWorker", project_id="test_pid")
        assert info["class"] == "AsyncWorker"
        assert "BaseWorker" in info["superclasses"]
        assert "PriorityWorker" in info["subclasses"]

        # 2. Inspect PriorityWorker ancestors
        info_prio = await cg.get_class_hierarchy("PriorityWorker", project_id="test_pid")
        assert "AsyncWorker" in info_prio["superclasses"]
        assert "BaseWorker" in info_prio["all_ancestors"]

        # 3. CodeAnalysisTools formatting
        tools = CodeAnalysisTools(workspace_root=str(root))
        with patch("core.knowledge.code_graph.code_graph", cg):
            out = await tools.get_class_hierarchy("AsyncWorker", project_id="test_pid")
            assert "Class Hierarchy for 'AsyncWorker'" in out
            assert "Superclasses: BaseWorker" in out
            assert "PriorityWorker" in out


# ─────────────────────────────────────────────────────────────────────────────
# 5. REST Endpoints Testing
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_and_knowledge_endpoints():
    from httpx import AsyncClient, ASGITransport
    from main import app
    from core.auth.auth_middleware import require_auth
    from core.api.crud_routes import _assert_project_access

    async def mock_auth():
        return {"sub": "test-user-id", "email": "test@carole.ai"}

    async def mock_assert_access(db, pid, uid):
        return True

    app.dependency_overrides[require_auth] = mock_auth
    app.dependency_overrides[_assert_project_access] = mock_assert_access

    valid_pid = "00000000-0000-0000-0000-000000000001"
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("core.api.search_routes._assert_project_access", return_value=True), \
                 patch("core.api.crud_routes._assert_project_access", return_value=True):
                # 1. POST /api/search/code
                with patch("core.knowledge.hybrid_search.hybrid_code_search.search") as mock_search:
                    mock_search.return_value = [
                        {
                            "file_path": "core/agent/worker.py",
                            "name": "execute_task",
                            "kind": "function",
                            "start_line": 10,
                            "end_line": 30,
                            "code": "def execute_task(): pass",
                            "score": 0.85
                        }
                    ]
                    res = await client.post("/api/search/code", json={
                        "query": "execute_task",
                        "project_id": valid_pid,
                        "top_k": 5
                    })
                    assert res.status_code == 200
                    data = res.json()
                    assert data["status"] == "success"
                    assert data["total"] == 1
                    assert data["results"][0]["name"] == "execute_task"

                # 2. GET /api/knowledge/symbols/{project_id}
                with patch("core.knowledge.code_graph.code_graph.get_symbol_definitions") as mock_sym:
                    mock_sym.return_value = [
                        {"name": "WorkflowDAG", "kind": "class", "file_path": "core/agent/workflow_dag.py"}
                    ]
                    res = await client.get(f"/api/knowledge/symbols/{valid_pid}?name=WorkflowDAG")
                    assert res.status_code == 200
                    data = res.json()
                    assert data["status"] == "success"
                    assert len(data["symbols"]) == 1

                # 3. GET /api/knowledge/graph/{project_id}
                with patch("core.knowledge.code_graph.code_graph.get_graph") as mock_graph:
                    import networkx as nx
                    g = nx.DiGraph()
                    g.add_edge("file_a.py", "file_b.py")
                    mock_graph.return_value = g
                    res = await client.get(f"/api/knowledge/graph/{valid_pid}")
                    assert res.status_code == 200
                    data = res.json()
                    assert data["status"] == "success"
                    assert data["node_count"] == 2
                    assert data["edge_count"] == 1

                # 4. GET /api/knowledge/hierarchy/{project_id}
                with patch("core.knowledge.code_graph.code_graph.get_class_hierarchy") as mock_hier:
                    mock_hier.return_value = {
                        "class": "Child",
                        "superclasses": ["Parent"],
                        "subclasses": []
                    }
                    res = await client.get(f"/api/knowledge/hierarchy/{valid_pid}?class_name=Child")
                    assert res.status_code == 200
                    data = res.json()
                    assert data["status"] == "success"
                    assert data["hierarchy"]["superclasses"] == ["Parent"]

    finally:
        app.dependency_overrides.pop(require_auth, None)
        app.dependency_overrides.pop(_assert_project_access, None)


def test_polyglot_ast_bases_extraction():
    # 1. Python class inheritance
    py_code = "class PaymentService(BaseService, LoggableMixin):\n    pass\n"
    chunks, _ = parse_file_ast(py_code, "service.py")
    assert len(chunks) == 1
    assert chunks[0].kind == "class"
    assert "BaseService" in chunks[0].bases
    assert "LoggableMixin" in chunks[0].bases

    # 2. TypeScript class inheritance
    ts_code = "export class DashboardComponent extends React.Component {\n    render() {}\n}\n"
    chunks_ts, _ = parse_file_ast(ts_code, "Dashboard.tsx")
    assert len(chunks_ts) >= 1
    class_chunk = [c for c in chunks_ts if c.kind == "class"]
    assert len(class_chunk) == 1
    assert "Component" in class_chunk[0].bases or "React" in class_chunk[0].bases or len(class_chunk[0].bases) > 0


@pytest.mark.asyncio
async def test_repo_map_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        cg = CodeGraph(workspace_root=str(root))
        
        file1 = root / "auth.py"
        file1.write_text("class AuthManager:\n    def login(self): pass\n", encoding="utf-8")
        
        file2 = root / "app.py"
        file2.write_text("from .auth import AuthManager\nclass App:\n    def run(self): pass\n", encoding="utf-8")

        await cg.build_graph("repo_map_pid")
        repo_map = await cg.generate_repo_map("repo_map_pid", max_tokens=500)
        assert "<repo-map>" in repo_map
        assert "</repo-map>" in repo_map
        assert "AuthManager" in repo_map

