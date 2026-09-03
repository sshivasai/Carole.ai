"""
# backend/tests/test_ast_parser_multilang.py

Unit tests for multi-language Tree-sitter AST extraction in Carole.ai:
Python, TypeScript, Rust, Go, Java, C, C++, C#.
"""

import pytest
from core.knowledge.ast_parser import parse_file_ast, _TS_PARSERS, _TREE_SITTER_AVAILABLE


def test_tree_sitter_parsers_initialized():
    """Verify all 10 language grammars are loaded in Tree-sitter."""
    assert _TREE_SITTER_AVAILABLE, "Tree-sitter must be available"
    expected = ["python", "javascript", "typescript", "tsx", "rust", "go", "java", "c", "cpp", "c_sharp"]
    for lang in expected:
        assert lang in _TS_PARSERS, f"Parser for {lang} should be initialized"


def test_java_ast_parsing():
    """Test extracting classes and methods from Java source code."""
    code = """package com.example;

import java.util.List;

public class OrderService {
    public int processOrder(String orderId, int quantity) {
        validate(orderId);
        return quantity * 10;
    }

    private void validate(String id) {
        System.out.println("Validating " + id);
    }
}
"""
    chunks, imports = parse_file_ast(code, "src/OrderService.java")
    chunk_names = [c.name for c in chunks]

    assert "OrderService" in chunk_names
    assert "processOrder" in chunk_names
    assert "validate" in chunk_names

    # Check methods have OrderService as parent
    methods = [c for c in chunks if c.name in ("processOrder", "validate")]
    for m in methods:
        assert m.parent_symbol == "OrderService"


def test_c_ast_parsing():
    """Test extracting functions and includes from C source code."""
    code = """#include <stdio.h>
#include "helper.h"

int calculate_hash(const char *key, int len) {
    int hash = 0;
    for (int i = 0; i < len; i++) {
        hash += key[i];
    }
    return hash;
}
"""
    chunks, imports = parse_file_ast(code, "src/hash.c")
    chunk_names = [c.name for c in chunks]

    assert "calculate_hash" in chunk_names
    fn = next(c for c in chunks if c.name == "calculate_hash")
    assert fn.kind == "function"
    assert fn.start_line == 4


def test_cpp_ast_parsing():
    """Test extracting classes and methods from C++ source code."""
    code = """#include <iostream>

class NetworkManager {
public:
    void connect(const std::string& host, int port) {
        initSocket();
    }
private:
    void initSocket() {}
};
"""
    chunks, imports = parse_file_ast(code, "src/network.cpp")
    chunk_names = [c.name for c in chunks]

    assert "NetworkManager" in chunk_names
    assert "connect" in chunk_names
    assert "initSocket" in chunk_names


def test_c_sharp_ast_parsing():
    """Test extracting classes and methods from C# source code."""
    code = """using System;

namespace CoreApp {
    public class AccountController {
        public bool Authenticate(string username, string password) {
            return VerifyHash(username, password);
        }

        private bool VerifyHash(string u, string p) {
            return true;
        }
    }
}
"""
    chunks, imports = parse_file_ast(code, "Controllers/AccountController.cs")
    chunk_names = [c.name for c in chunks]

    assert "AccountController" in chunk_names
    assert "Authenticate" in chunk_names
    assert "VerifyHash" in chunk_names
