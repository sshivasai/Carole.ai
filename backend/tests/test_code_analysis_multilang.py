"""
# backend/tests/test_code_analysis_multilang.py

Unit tests for multi-language CodeAnalysisTools:
Validates _is_code_file, find_todos across comment syntaxes, find_function across
language keywords, count_lines comment detection, and analyze_imports.
"""

import pytest
from pathlib import Path
from core.tools.code_analysis_tools import CodeAnalysisTools


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


def test_is_code_file():
    tools = CodeAnalysisTools()

    # Supported source code
    assert tools._is_code_file("app.py")
    assert tools._is_code_file("service.ts")
    assert tools._is_code_file("server.go")
    assert tools._is_code_file("engine.rs")
    assert tools._is_code_file("script.rb")
    assert tools._is_code_file("logic.lua")
    assert tools._is_code_file("app.swift")
    assert tools._is_code_file("controller.kt")
    assert tools._is_code_file("actor.scala")
    assert tools._is_code_file("query.sql")
    assert tools._is_code_file("math.zig")
    assert tools._is_code_file("module.ex")
    assert tools._is_code_file("deploy.sh")
    assert tools._is_code_file("config.yaml")
    assert tools._is_code_file("page.html")
    assert tools._is_code_file("Makefile")
    assert tools._is_code_file("Dockerfile")
    assert tools._is_code_file("contract.sol")  # unknown source extension

    # Binary and compiled files (must be skipped)
    assert not tools._is_code_file("logo.png")
    assert not tools._is_code_file("photo.jpg")
    assert not tools._is_code_file("report.pdf")
    assert not tools._is_code_file("archive.zip")
    assert not tools._is_code_file("binary.exe")
    assert not tools._is_code_file("module.pyc")
    assert not tools._is_code_file("compiled.class")
    assert not tools._is_code_file("data.sqlite")


def test_find_todos_multi_syntax(temp_workspace):
    tools = CodeAnalysisTools(workspace_root=str(temp_workspace))

    # Python / Ruby / Bash (#)
    (temp_workspace / "script.py").write_text("# TODO: fix python bug\nx = 1\n", encoding="utf-8")
    (temp_workspace / "deploy.sh").write_text("# FIXME: update shell path\n", encoding="utf-8")
    (temp_workspace / "model.rb").write_text("# HACK: temporary ruby bypass\n", encoding="utf-8")

    # C / C++ / Swift / Kotlin / Go (//)
    (temp_workspace / "main.swift").write_text("// NOTE: handle swift optional\n", encoding="utf-8")
    (temp_workspace / "App.kt").write_text("// TODO: implement kotlin coroutine\n", encoding="utf-8")

    # SQL / Lua (--)
    (temp_workspace / "schema.sql").write_text("-- TODO: add index on user_id\n", encoding="utf-8")
    (temp_workspace / "game.lua").write_text("-- FIXME: physics collision\n", encoding="utf-8")

    # HTML (<!-- -->)
    (temp_workspace / "index.html").write_text("<!-- TODO: add footer links -->\n", encoding="utf-8")

    res = tools.find_todos(".")
    assert "Found 8 comment(s)" in res
    assert "fix python bug" in res
    assert "update shell path" in res
    assert "temporary ruby bypass" in res
    assert "handle swift optional" in res
    assert "implement kotlin coroutine" in res
    assert "add index on user_id" in res
    assert "physics collision" in res
    assert "add footer links" in res


def test_find_function_multi_language(temp_workspace):
    tools = CodeAnalysisTools(workspace_root=str(temp_workspace))

    # Swift
    (temp_workspace / "client.swift").write_text(
        "class NetworkService {\n    func fetchRemoteData() {}\n}\n",
        encoding="utf-8"
    )
    # Kotlin
    (temp_workspace / "auth.kt").write_text(
        "class AuthProvider {\n    fun validateCredentials() {}\n}\n",
        encoding="utf-8"
    )
    # Rust
    (temp_workspace / "lib.rs").write_text(
        "pub fn calculate_checksum() {}\n",
        encoding="utf-8"
    )
    # Ruby
    (temp_workspace / "worker.rb").write_text(
        "def perform_background_task\nend\n",
        encoding="utf-8"
    )
    # Solidity
    (temp_workspace / "Token.sol").write_text(
        "contract LiquidityVault {\n    function depositTokens() public {}\n}\n",
        encoding="utf-8"
    )

    swift_res = tools.find_function("fetchRemoteData")
    assert "client.swift" in swift_res
    assert "func fetchRemoteData" in swift_res

    kt_res = tools.find_function("validateCredentials")
    assert "auth.kt" in kt_res
    assert "fun validateCredentials" in kt_res

    rs_res = tools.find_function("calculate_checksum")
    assert "lib.rs" in rs_res
    assert "pub fn calculate_checksum" in rs_res

    rb_res = tools.find_function("perform_background_task")
    assert "worker.rb" in rb_res
    assert "def perform_background_task" in rb_res

    sol_res = tools.find_function("LiquidityVault")
    assert "Token.sol" in sol_res
    assert "contract LiquidityVault" in sol_res


def test_count_lines_multi_comment_prefixes(temp_workspace):
    tools = CodeAnalysisTools(workspace_root=str(temp_workspace))

    # Python (#)
    (temp_workspace / "test.py").write_text("# comment 1\n# comment 2\n\ncode = 1\n", encoding="utf-8")
    py_res = tools.count_lines("test.py")
    assert "Total:    4" in py_res
    assert "Code:     1" in py_res
    assert "Comments: 2" in py_res
    assert "Blank:    1" in py_res

    # SQL (--)
    (temp_workspace / "query.sql").write_text("-- first sql comment\n-- second sql comment\nSELECT * FROM users;\n", encoding="utf-8")
    sql_res = tools.count_lines("query.sql")
    assert "Total:    3" in sql_res
    assert "Code:     1" in sql_res
    assert "Comments: 2" in sql_res

    # Swift (//)
    (temp_workspace / "app.swift").write_text("// swift comment\nlet x = 10\n", encoding="utf-8")
    swift_res = tools.count_lines("app.swift")
    assert "Total:    2" in swift_res
    assert "Code:     1" in swift_res
    assert "Comments: 1" in swift_res


def test_analyze_imports_multi_language(temp_workspace):
    tools = CodeAnalysisTools(workspace_root=str(temp_workspace))

    # Python
    (temp_workspace / "app.py").write_text("import sys\nfrom os import path\nx = 1\n", encoding="utf-8")
    py_imp = tools.analyze_imports("app.py")
    assert "import sys" in py_imp
    assert "from os import path" in py_imp

    # TypeScript / JavaScript
    (temp_workspace / "app.ts").write_text("import React from 'react';\nconst fs = require('fs');\nexport { x } from './utils';\n", encoding="utf-8")
    ts_imp = tools.analyze_imports("app.ts")
    assert "import React from 'react';" in ts_imp
    assert "const fs = require('fs');" in ts_imp
    assert "export { x } from './utils';" in ts_imp

    # C++
    (temp_workspace / "app.cpp").write_text("#include <iostream>\n#include \"header.h\"\nint main() {}\n", encoding="utf-8")
    cpp_imp = tools.analyze_imports("app.cpp")
    assert "#include <iostream>" in cpp_imp
    assert '#include "header.h"' in cpp_imp

    # Rust
    (temp_workspace / "app.rs").write_text("use std::collections::HashMap;\nuse crate::utils;\n", encoding="utf-8")
    rs_imp = tools.analyze_imports("app.rs")
    assert "use std::collections::HashMap;" in rs_imp
    assert "use crate::utils;" in rs_imp

    # Swift
    (temp_workspace / "app.swift").write_text("import Foundation\nimport UIKit\n", encoding="utf-8")
    swift_imp = tools.analyze_imports("app.swift")
    assert "import Foundation" in swift_imp
    assert "import UIKit" in swift_imp
