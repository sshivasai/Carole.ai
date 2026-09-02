"""
# backend/tests/test_hybrid_rag_and_symbols.py

Tests for Phase 3 (AST-Aware Code Intelligence & Hybrid RAG) and Phase 4 (Code Symbol Graph & Relational Navigation).
"""

import pytest
from core.knowledge.ast_parser import parse_file_ast, ASTChunk
from core.knowledge.hybrid_search import tokenize_code, BM25Index, HybridCodeSearch
from core.knowledge.code_graph import CodeGraph
from core.tools.code_analysis_tools import CodeAnalysisTools


def test_code_tokenizer_camel_and_snake():
    text = "def calculate_total_amount(userAccount, order_id):"
    tokens = tokenize_code(text)

    # Must preserve exact tokens
    assert "calculate_total_amount" in tokens
    assert "useraccount" in tokens
    assert "order_id" in tokens

    # Must split snake_case
    assert "calculate" in tokens
    assert "total" in tokens
    assert "amount" in tokens
    assert "order" in tokens
    assert "id" in tokens

    # Must split camelCase
    assert "user" in tokens
    assert "account" in tokens


def test_bm25_index_and_ranking():
    chunk1 = ASTChunk(
        name="authenticate_user",
        kind="function",
        file_path="backend/core/auth.py",
        start_line=10,
        end_line=30,
        code="def authenticate_user(username, password):\n    validate_credentials(username, password)",
        params=["username", "password"],
        calls=["validate_credentials"],
    )

    chunk2 = ASTChunk(
        name="render_button",
        kind="function",
        file_path="frontend/src/Button.tsx",
        start_line=1,
        end_line=15,
        code="export function render_button(props) {\n    return <button>{props.label}</button>;\n}",
        params=["props"],
        calls=[],
    )

    bm25 = BM25Index()
    bm25.index_chunks([chunk1, chunk2])

    # Search for authentication
    auth_results = bm25.search("authenticate user password")
    assert len(auth_results) > 0
    top_doc_idx, top_score = auth_results[0]
    assert top_doc_idx == 0  # chunk1
    assert top_score > 0.0

    # Search for button UI
    ui_results = bm25.search("button render props")
    assert len(ui_results) > 0
    top_doc_idx, top_score = ui_results[0]
    assert top_doc_idx == 1  # chunk2
    assert top_score > 0.0


def test_reciprocal_rank_fusion():
    hybrid = HybridCodeSearch()
    bm25_ranked = [(0, 5.0), (1, 3.0), (2, 1.0)]
    vector_ranked = [(1, 0.95), (0, 0.85), (3, 0.70)]

    fused = hybrid.reciprocal_rank_fusion(bm25_ranked, vector_ranked, k=60)
    # Both 0 and 1 are in top 2 of both rankers, so they should be at the top of fused
    top_indices = [idx for idx, _ in fused[:2]]
    assert 0 in top_indices
    assert 1 in top_indices


def test_ast_parser_python_chunks():
    py_code = """
import os
from typing import List

class UserManager:
    def __init__(self, db):
        self.db = db

    def get_user_by_id(self, user_id: str) -> dict:
        \"\"\"Fetches user record.\"\"\"
        return self.db.find(user_id)
"""
    chunks, imports = parse_file_ast(py_code, "backend/user_manager.py")
    assert len(chunks) >= 2
    names = [c.name for c in chunks]
    assert "UserManager" in names
    assert "get_user_by_id" in names
    assert "os" in imports or "typing" in imports


@pytest.mark.asyncio
async def test_code_graph_and_tools_module_dependencies(tmp_path):
    tools = CodeAnalysisTools(workspace_root=str(tmp_path))
    # Test non-existent file gracefully reports no dependencies
    res = await tools.get_module_dependencies("non_existent_module.py")
    assert "Module Dependencies" in res


def test_ast_parser_typescript_tree_sitter():
    ts_code = """
import { useState } from "react";

export interface UserProfile {
    id: string;
    username: string;
}

export class AuthService {
    login(token: string): boolean {
        return Boolean(token);
    }
}
"""
    chunks, imports = parse_file_ast(ts_code, "frontend/src/auth.ts")
    assert len(chunks) >= 2
    names = [c.name for c in chunks]
    assert "UserProfile" in names or "AuthService" in names
    assert any(c.kind in ("interface", "class", "method") for c in chunks)


@pytest.mark.asyncio
async def test_static_code_embeddings_model2vec():
    chunk1 = ASTChunk(
        name="authenticate_user",
        kind="function",
        file_path="backend/core/auth.py",
        start_line=1,
        end_line=10,
        code="def authenticate_user(token): verify_jwt_signature(token)",
    )
    chunk2 = ASTChunk(
        name="render_button",
        kind="function",
        file_path="frontend/src/button.tsx",
        start_line=1,
        end_line=10,
        code="export function render_button() { return <button>Click</button>; }",
    )

    hybrid = HybridCodeSearch()
    hybrid.index_workspace_chunks([chunk1, chunk2])

    # Search with semantic query
    results = await hybrid.search("verify security token credential", top_k=2)
    assert len(results) > 0
    assert results[0]["name"] == "authenticate_user"
