"""
# backend/tests/test_ast_parser_multilang.py

Unit tests for multi-language Tree-sitter AST extraction in Carole.ai:
Verifies 28 native Tree-sitter grammars and universal polyglot fallback.
"""

import pytest
from core.knowledge.ast_parser import parse_file_ast, _TS_PARSERS, _TREE_SITTER_AVAILABLE


def test_tree_sitter_parsers_initialized():
    """Verify core language grammars are loaded in Tree-sitter."""
    assert _TREE_SITTER_AVAILABLE, "Tree-sitter must be available"
    expected = ["python", "javascript", "typescript", "tsx", "rust", "go", "java", "c", "cpp", "c_sharp"]
    for lang in expected:
        assert lang in _TS_PARSERS, f"Parser for {lang} should be initialized"
    assert len(_TS_PARSERS) >= 10


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


def test_ruby_ast_parsing():
    """Test extracting classes and methods from Ruby source code."""
    if "ruby" not in _TS_PARSERS:
        pytest.skip("Tree-sitter ruby grammar not installed in environment")
    code = """class PaymentProcessor
  def charge(amount)
    execute_transaction(amount)
  end

  def refund(tx_id)
  end
end
"""
    chunks, imports = parse_file_ast(code, "app/models/payment_processor.rb")
    chunk_names = [c.name for c in chunks]

    assert "PaymentProcessor" in chunk_names
    assert "charge" in chunk_names
    assert "refund" in chunk_names

    methods = [c for c in chunks if c.name in ("charge", "refund")]
    for m in methods:
        assert m.parent_symbol == "PaymentProcessor"


def test_php_ast_parsing():
    """Test extracting classes and methods from PHP source code."""
    code = """<?php
namespace App\\Services;

class UserService {
    public function findUser(int $id) {
        return $id;
    }
}
"""
    chunks, imports = parse_file_ast(code, "app/Services/UserService.php")
    chunk_names = [c.name for c in chunks]

    assert "UserService" in chunk_names
    assert "findUser" in chunk_names


def test_bash_ast_parsing():
    """Test extracting shell functions from Bash scripts."""
    if "bash" not in _TS_PARSERS:
        pytest.skip("Tree-sitter bash grammar not installed in environment")
    code = """#!/usr/bin/env bash

function deploy_app() {
    echo "Deploying..."
    build_assets
}

cleanup_temp() {
    rm -rf /tmp/build
}
"""
    chunks, imports = parse_file_ast(code, "scripts/deploy.sh")
    chunk_names = [c.name for c in chunks]

    assert "deploy_app" in chunk_names
    assert "cleanup_temp" in chunk_names


def test_lua_ast_parsing():
    """Test extracting functions from Lua source code."""
    code = """local M = {}

function calculate_bonus(salary, rate)
    return salary * rate
end

function M.init()
end
"""
    chunks, imports = parse_file_ast(code, "src/calculator.lua")
    chunk_names = [c.name for c in chunks]

    assert "calculate_bonus" in chunk_names


def test_swift_ast_parsing():
    """Test extracting classes and methods from Swift source code."""
    code = """import Foundation

class NetworkClient {
    func fetchData(url: String) {
        let req = createRequest(url)
    }
}
"""
    chunks, imports = parse_file_ast(code, "Sources/NetworkClient.swift")
    chunk_names = [c.name for c in chunks]

    assert "NetworkClient" in chunk_names
    assert "fetchData" in chunk_names


def test_kotlin_ast_parsing():
    """Test extracting classes and methods from Kotlin source code."""
    code = """package com.carole.api

class AuthManager {
    fun verifyToken(token: String): Boolean {
        return token.isNotEmpty()
    }
}
"""
    chunks, imports = parse_file_ast(code, "src/main/kotlin/AuthManager.kt")
    chunk_names = [c.name for c in chunks]

    assert "AuthManager" in chunk_names
    assert "verifyToken" in chunk_names


def test_scala_ast_parsing():
    """Test extracting classes and methods from Scala source code."""
    code = """package com.example

class GreetingService {
    def greet(name: String): String = {
        s"Hello, $name"
    }
}
"""
    chunks, imports = parse_file_ast(code, "src/GreetingService.scala")
    chunk_names = [c.name for c in chunks]

    assert "GreetingService" in chunk_names
    assert "greet" in chunk_names


def test_elixir_ast_parsing():
    """Test extracting modules and functions from Elixir source code."""
    if "elixir" not in _TS_PARSERS:
        pytest.skip("Tree-sitter elixir grammar not installed in environment")
    code = """defmodule Calculator do
  def add(a, b) do
    a + b
  end

  def multiply(x, y) do
    x * y
  end
end
"""
    chunks, imports = parse_file_ast(code, "lib/calculator.ex")
    chunk_names = [c.name for c in chunks]

    assert "Calculator" in chunk_names
    assert "add" in chunk_names
    assert "multiply" in chunk_names


def test_zig_ast_parsing():
    """Test extracting functions from Zig source code."""
    code = """const std = @import("std");

pub fn compute_sum(a: i32, b: i32) i32 {
    return a + b;
}
"""
    chunks, imports = parse_file_ast(code, "src/math.zig")
    chunk_names = [c.name for c in chunks]

    assert "compute_sum" in chunk_names


def test_polyglot_regex_fallback():
    """Test fallback parsing on languages outside native grammars (Perl, Dart, Solidity)."""
    code = """
sub process_transaction {
    my ($amount) = @_;
}

contract VaultToken {
    function deposit() public {}
}
"""
    chunks, _ = parse_file_ast(code, "legacy/script.pl")
    chunk_names = [c.name for c in chunks]
    assert "process_transaction" in chunk_names

    sol_chunks, _ = parse_file_ast(code, "contracts/Token.sol")
    sol_names = [c.name for c in sol_chunks]
    assert "VaultToken" in sol_names or "deposit" in sol_names
