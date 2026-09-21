"""
# backend/core/knowledge/ast_parser.py

Compiler-grade AST parsing and semantic chunking (Semble Pattern).
Uses Tree-sitter for TypeScript, JavaScript, Python, Rust, and Go to extract
full functional units (classes, functions, methods, interfaces, types)
with exact line ranges, docstrings, parameters, calls, and imports.
Includes resilient fallback to native Python AST and polyglot regex.
"""

import ast
import re
import logging
import posixpath
import multiprocessing
import threading
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Set, Optional, Any, Tuple

logger = logging.getLogger("carole.ast_parser")

import importlib

# Dynamic Tree-sitter imports with safe fallback
_TREE_SITTER_AVAILABLE = False
_TS_PARSERS: Dict[str, Any] = {}
_TS_QUERIES: Dict[str, Any] = {}


def _init_tree_sitter_parsers() -> None:
    """Dynamically initializes Tree-sitter parsers and S-expression queries without static analysis errors."""
    global _TREE_SITTER_AVAILABLE, _TS_PARSERS, _TS_QUERIES
    try:
        ts = importlib.import_module("tree_sitter")
        Parser = getattr(ts, "Parser")
        Language = getattr(ts, "Language")
        Query = getattr(ts, "Query", None)

        lang_modules = {
            "python": ("tree_sitter_python", "language"),
            "javascript": ("tree_sitter_javascript", "language"),
            "typescript": ("tree_sitter_typescript", "language_typescript"),
            "tsx": ("tree_sitter_typescript", "language_tsx"),
            "rust": ("tree_sitter_rust", "language"),
            "go": ("tree_sitter_go", "language"),
            "java": ("tree_sitter_java", "language"),
            "c": ("tree_sitter_c", "language"),
            "cpp": ("tree_sitter_cpp", "language"),
            "c_sharp": ("tree_sitter_c_sharp", "language"),
            "ruby": ("tree_sitter_ruby", "language"),
            "php": ("tree_sitter_php", "language_php"),
            "bash": ("tree_sitter_bash", "language"),
            "lua": ("tree_sitter_lua", "language"),
            "scala": ("tree_sitter_scala", "language"),
            "kotlin": ("tree_sitter_kotlin", "language"),
            "swift": ("tree_sitter_swift", "language"),
            "sql": ("tree_sitter_sql", "language"),
            "elixir": ("tree_sitter_elixir", "language"),
            "zig": ("tree_sitter_zig", "language"),
            "html": ("tree_sitter_html", "language"),
            "css": ("tree_sitter_css", "language"),
            "json": ("tree_sitter_json", "language"),
            "yaml": ("tree_sitter_yaml", "language"),
            "toml": ("tree_sitter_toml", "language"),
            "markdown": ("tree_sitter_markdown", "language"),
            "make": ("tree_sitter_make", "language"),
            "cmake": ("tree_sitter_cmake", "language"),
        }

        scm_queries = {
            "python": "[(function_definition name: (identifier) @name) @def (class_definition name: (identifier) @name) @def]",
            "javascript": "[(function_declaration name: (identifier) @name) @def (method_definition name: (property_identifier) @name) @def (class_declaration name: (identifier) @name) @def]",
            "typescript": "[(function_declaration name: (identifier) @name) @def (method_definition name: (property_identifier) @name) @def (class_declaration name: (type_identifier) @name) @def (interface_declaration name: (type_identifier) @name) @def]",
            "tsx": "[(function_declaration name: (identifier) @name) @def (method_definition name: (property_identifier) @name) @def (class_declaration name: (type_identifier) @name) @def (interface_declaration name: (type_identifier) @name) @def]",
            "rust": "[(function_item name: (identifier) @name) @def (struct_item name: (type_identifier) @name) @def (trait_item name: (type_identifier) @name) @def]",
            "go": "[(function_declaration name: (identifier) @name) @def (method_declaration name: (field_identifier) @name) @def]",
            "java": "[(method_declaration name: (identifier) @name) @def (class_declaration name: (identifier) @name) @def (interface_declaration name: (identifier) @name) @def]",
            "c": "[(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def (struct_specifier name: (type_identifier) @name) @def]",
            "cpp": "[(function_definition declarator: (function_declarator declarator: (identifier) @name)) @def (class_specifier name: (type_identifier) @name) @def]",
            "c_sharp": "[(method_declaration name: (identifier) @name) @def (class_declaration name: (identifier) @name) @def (interface_declaration name: (identifier) @name) @def]",
        }

        for lang_key, (mod_name, func_name) in lang_modules.items():
            try:
                mod = importlib.import_module(mod_name)
                func = getattr(mod, func_name)
                lang_obj = Language(func())
                _TS_PARSERS[lang_key] = Parser(lang_obj)
                if Query and lang_key in scm_queries:
                    try:
                        _TS_QUERIES[lang_key] = Query(lang_obj, scm_queries[lang_key])
                    except Exception as qex:
                        logger.debug("Tree-sitter SCM query compilation failed for '%s': %s", lang_key, qex)
            except Exception as ex:
                logger.debug("Tree-sitter grammar for '%s' could not be loaded: %s", lang_key, ex)

        if _TS_PARSERS:
            _TREE_SITTER_AVAILABLE = True
            logger.info("🌳 [ASTParser] Tree-sitter initialized for: %s (SCM queries compiled: %d)", list(_TS_PARSERS.keys()), len(_TS_QUERIES))
    except Exception as e:
        logger.warning("Tree-sitter native grammars unavailable, falling back to compiler AST: %s", e)


_init_tree_sitter_parsers()


@dataclass
class ASTChunk:
    name: str
    kind: str  # 'function' | 'async_function' | 'class' | 'method' | 'interface' | 'type_alias' | 'enum' | 'struct' | 'trait'
    file_path: str
    start_line: int
    end_line: int
    code: str
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None
    params: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Tree-sitter AST Extraction (Semble Pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _get_node_text(node: Any, content_bytes: bytes) -> str:
    """Returns utf-8 string for a Tree-sitter AST node."""
    return content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


_native_pool = None
_native_lock = threading.Lock()
_failed_languages: Set[Tuple[str, str]] = set()


def _native_request(operation: str, content: str, rel_path: str, lang_key: str):
    """Keep native grammar crashes outside the API process; fail over to safe parsers."""
    global _native_pool
    if lang_key not in _TS_PARSERS or (operation, lang_key) in _failed_languages:
        return None
    with _native_lock:
        if (operation, lang_key) in _failed_languages:
            return None
        if _native_pool is None:
            _native_pool = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn"))
        try:
            return _native_pool.submit(_native_worker, operation, content, rel_path, lang_key).result(timeout=15)
        except Exception:
            logger.exception("Native parser failed for %s; using fallback", lang_key)
            _failed_languages.add((operation, lang_key))
            # A native hang cannot be cancelled as a Python future.
            for process in list((_native_pool._processes or {}).values()):
                if process.is_alive():
                    process.terminate()
            _native_pool.shutdown(wait=False, cancel_futures=True)
            _native_pool = None
            return None


def _native_worker(operation, content, rel_path, lang_key):
    if operation == "syntax":
        from tree_sitter import Parser
        parser = Parser(_TS_PARSERS[lang_key].language)
        tree = parser.parse(content.encode("utf-8"))
        return tree.root_node.has_error
    return _parse_tree_sitter_local(content, rel_path, lang_key)


def syntax_has_error(content: str, lang_key: str) -> Optional[bool]:
    return _native_request("syntax", content, "", lang_key)


def parse_tree_sitter(content: str, rel_path: str, lang_key: str) -> Tuple[List[ASTChunk], List[str]]:
    return _native_request("parse", content, rel_path, lang_key) or ([], [])


def _parse_tree_sitter_local(content: str, rel_path: str, lang_key: str) -> Tuple[List[ASTChunk], List[str]]:
    """Extracts functional units using Tree-sitter grammars."""
    template = _TS_PARSERS.get(lang_key)
    if not template:
        return [], []
    # Parser instances are mutable native state. Graph refresh and context
    # folding run in different threads; never share an instance between calls.
    from tree_sitter import Parser
    parser = Parser(template.language)

    content_bytes = content.encode("utf-8")
    tree = parser.parse(content_bytes)
    root = tree.root_node

    chunks: List[ASTChunk] = []
    imports: List[str] = []
    lines = content.splitlines()

    # Node types mapping across languages
    FUNC_TYPES = {
        "function_definition", "function_declaration", "method_definition",
        "arrow_function", "function_item", "method_declaration",
        "constructor_declaration", "method", "singleton_method",
        "secondary_constructor", "initializer_declaration", "deinitializer_declaration",
        "create_function", "create_procedure", "rule", "normal_command"
    }
    CLASS_TYPES = {
        "class_definition", "class_declaration", "struct_item", "impl_item",
        "trait_item", "type_declaration", "class_specifier", "struct_specifier",
        "record_declaration", "namespace_definition", "class", "module",
        "singleton_class", "trait_declaration", "object_definition", "trait_definition",
        "object_declaration", "protocol_declaration", "extension_declaration",
        "actor_declaration", "create_table", "create_view", "rule_set"
    }
    TYPE_TYPES = {
        "interface_declaration", "type_alias_declaration", "enum_declaration",
        "enum_item", "enum_specifier", "struct_declaration", "typealias_declaration",
        "type_definition", "typealias", "union_declaration"
    }
    IMPORT_TYPES = {
        "import_statement", "import_from_statement", "use_declaration",
        "import_declaration", "using_directive", "preproc_include",
        "namespace_use_declaration", "import_header", "import_list",
        "package_clause", "package_declaration"
    }

    def walk(node: Any, current_parent: Optional[str] = None, depth: int = 0):
        if depth > 60:
            return
        ntype = node.type

        # Extract Imports
        if ntype in IMPORT_TYPES or ntype == "use_declaration":
            raw_imp = _get_node_text(node, content_bytes).strip()
            # 1. Quoted paths (JS/TS, Go, C/C++, Rust externs, Python dynamic)
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", raw_imp)
            if quoted:
                for q in quoted:
                    if q.strip():
                        imports.append(q.strip())
            else:
                # 2. Python-style relative/absolute imports
                m_from = re.match(r"^from\s+([.\w]+)\s+import", raw_imp)
                if m_from:
                    imports.append(m_from.group(1))
                m_imp = re.match(r"^import\s+([.\w]+(?:\s*,\s*[.\w]+)*)", raw_imp)
                if m_imp:
                    for item in m_imp.group(1).split(","):
                        if item.strip():
                            imports.append(item.strip())
                # 3. Rust use declaration
                m_use = re.match(r"^(?:pub\s+)?use\s+([a-zA-Z0-9_:]+)", raw_imp)
                if m_use:
                    imports.append(m_use.group(1))
                # 4. Fallback: extract individual valid module identifiers (excluding reserved keywords)
                if not quoted and not m_from and not m_imp and not m_use:
                    for mod in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", raw_imp):
                        if mod not in ("import", "from", "as", "use", "pub", "crate", "using", "include", "package", "require", "alias", "default", "type"):
                            imports.append(mod)
            return

        # Special handling for Elixir call nodes (defmodule, def, defp)
        if ntype == "call" and node.children:
            target_text = _get_node_text(node.children[0], content_bytes)
            if target_text in ("defmodule", "defprotocol", "defimpl"):
                mod_name = None
                if len(node.children) > 1:
                    args_node = node.children[1]
                    mod_name = _get_node_text(args_node, content_bytes).split()[0].strip()
                if mod_name:
                    start_line = node.start_point.row + 1
                    end_line = node.end_point.row + 1
                    code_slice = "\n".join(lines[start_line - 1 : end_line])
                    chunks.append(ASTChunk(
                        name=mod_name,
                        kind="module" if target_text == "defmodule" else "interface",
                        file_path=rel_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=code_slice,
                        parent_symbol=current_parent,
                        imports=list(imports)
                    ))
                    for child in node.children:
                        walk(child, current_parent=mod_name, depth=depth + 1)
                    return
            elif target_text in ("def", "defp", "defmacro"):
                fn_name = None
                params = []
                if len(node.children) > 1:
                    call_spec = node.children[1]
                    spec_text = _get_node_text(call_spec, content_bytes)
                    fn_match = re.match(r"([a-zA-Z0-9_?!]+)(?:\((.*?)\))?", spec_text)
                    if fn_match:
                        fn_name = fn_match.group(1)
                        if fn_match.group(2):
                            params = [p.strip() for p in fn_match.group(2).split(",") if p.strip()]
                if fn_name:
                    start_line = node.start_point.row + 1
                    end_line = node.end_point.row + 1
                    code_slice = "\n".join(lines[start_line - 1 : end_line])
                    chunks.append(ASTChunk(
                        name=fn_name,
                        kind="method" if current_parent else "function",
                        file_path=rel_path,
                        start_line=start_line,
                        end_line=end_line,
                        code=code_slice,
                        parent_symbol=current_parent,
                        params=params,
                        imports=list(imports)
                    ))
                    return

        # Extract Functions / Methods
        if ntype in FUNC_TYPES:
            name = None
            params = []
            calls = []

            for child in node.children:
                if child.type in (
                    "identifier", "name", "property_identifier", "field_identifier",
                    "simple_identifier", "word", "targets", "object_reference"
                ):
                    if not name:
                        name = _get_node_text(child, content_bytes)
                elif child.type == "function_declarator":
                    for sub in child.children:
                        if sub.type in ("identifier", "field_identifier", "simple_identifier"):
                            if not name:
                                name = _get_node_text(sub, content_bytes)
                        elif sub.type in ("parameter_list", "parameters"):
                            raw_params = _get_node_text(sub, content_bytes)
                            params = [p.strip().split(":")[0].strip() for p in raw_params.strip("()").split(",") if p.strip()]
                elif child.type in ("parameters", "formal_parameters", "parameter_list", "method_parameters"):
                    raw_params = _get_node_text(child, content_bytes)
                    params = [p.strip().split(":")[0].strip() for p in raw_params.strip("()").split(",") if p.strip()]

            if not name:
                # Arrow functions or anonymous
                if current_parent:
                    name = f"{current_parent}_fn"
                else:
                    name = f"anonymous_L{node.start_point.row + 1}"

            start_line = node.start_point.row + 1
            end_line = node.end_point.row + 1
            code_slice = "\n".join(lines[start_line - 1 : end_line])

            # Extract internal call sites
            raw_calls = re.findall(r"\b([a-zA-Z0-9_$]{3,40})\s*\(", code_slice)
            calls = list(set(raw_calls))

            kind = "method" if current_parent else ("async_function" if "async" in code_slice[:30] else "function")
            if ntype in ("rule",):
                kind = "build_rule"
            elif ntype in ("normal_command",):
                kind = "command"

            chunks.append(ASTChunk(
                name=name,
                kind=kind,
                file_path=rel_path,
                start_line=start_line,
                end_line=end_line,
                code=code_slice,
                parent_symbol=current_parent,
                params=params,
                calls=calls,
                imports=list(imports)
            ))

        # Extract Classes / Structs / Interfaces
        elif ntype in CLASS_TYPES or ntype in TYPE_TYPES:
            name = None
            for child in node.children:
                if child.type in (
                    "identifier", "name", "type_identifier", "constant",
                    "simple_identifier", "object_reference", "selectors"
                ):
                    name = _get_node_text(child, content_bytes)
                    break

            if name:
                start_line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                code_slice = "\n".join(lines[start_line - 1 : end_line])

                kind = "class"
                if "interface" in ntype or "protocol" in ntype: kind = "interface"
                elif "type" in ntype: kind = "type_alias"
                elif "enum" in ntype: kind = "enum"
                elif "struct" in ntype: kind = "struct"
                elif "trait" in ntype: kind = "trait"
                elif "module" in ntype: kind = "module"
                elif "table" in ntype: kind = "table"
                elif "view" in ntype: kind = "view"

                # Extract base / super classes
                bases: List[str] = []
                first_line = code_slice.splitlines()[0] if code_slice else ""
                inherit_m = re.search(r"(?:class|interface|struct|trait)\s+[a-zA-Z0-9_]+\s*(?:\(([^)]+)\)|extends\s+([a-zA-Z0-9_,\s]+)|:\s*([^{:]+))", first_line)
                if inherit_m:
                    raw_b = inherit_m.group(1) or inherit_m.group(2) or inherit_m.group(3) or ""
                    bases = [b.strip() for b in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", raw_b) if b.strip() not in ("public", "private", "protected", "implements", "extends")]

                chunks.append(ASTChunk(
                    name=name,
                    kind=kind,
                    file_path=rel_path,
                    start_line=start_line,
                    end_line=end_line,
                    code=code_slice,
                    parent_symbol=current_parent,
                    imports=list(imports),
                    bases=bases
                ))

                # Recurse inside class body with updated parent
                for child in node.children:
                    walk(child, current_parent=name, depth=depth + 1)
                return

        for child in node.children:
            walk(child, current_parent=current_parent, depth=depth + 1)

    walk(root, depth=0)
    return chunks, imports


# ─────────────────────────────────────────────────────────────────────────────
# Python Native AST Visitor (Fallback / Verification)
# ─────────────────────────────────────────────────────────────────────────────

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, content: str, rel_path: str):
        self.content = content
        self.lines = content.splitlines()
        self.rel_path = rel_path
        self.chunks: List[ASTChunk] = []
        self.imports: List[str] = []
        self.current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        dots = "." * (node.level or 0)
        mod = f"{dots}{node.module}" if node.module else dots
        if mod:
            self.imports.append(mod)
        for alias in node.names:
            target = f"{mod}.{alias.name}" if mod and not mod.endswith(".") else f"{mod}{alias.name}"
            self.imports.append(target)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name

        start = node.lineno
        end = getattr(node, "end_lineno", start + len(node.body))
        code_slice = "\n".join(self.lines[start - 1 : end])
        doc = ast.get_docstring(node)

        bases: List[str] = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(b.attr)
            elif isinstance(b, ast.Subscript):
                if isinstance(b.value, ast.Name):
                    bases.append(b.value.id)

        chunk = ASTChunk(
            name=node.name,
            kind="class",
            file_path=self.rel_path,
            start_line=start,
            end_line=end,
            code=code_slice,
            docstring=doc,
            parent_symbol=prev_class,
            imports=list(self.imports),
            bases=bases
        )
        self.chunks.append(chunk)

        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node, is_async=True)

    def _handle_function(self, node: Any, is_async: bool):
        start = node.lineno
        end = getattr(node, "end_lineno", start + len(node.body))
        code_slice = "\n".join(self.lines[start - 1 : end])
        doc = ast.get_docstring(node)
        params = [arg.arg for arg in node.args.args if arg.arg != "self" and arg.arg != "cls"]

        calls = []
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Call):
                if isinstance(sub_node.func, ast.Name):
                    calls.append(sub_node.func.id)
                elif isinstance(sub_node.func, ast.Attribute):
                    calls.append(sub_node.func.attr)

        kind = "method" if self.current_class else ("async_function" if is_async else "function")
        chunk = ASTChunk(
            name=node.name,
            kind=kind,
            file_path=self.rel_path,
            start_line=start,
            end_line=end,
            code=code_slice,
            docstring=doc,
            parent_symbol=self.current_class,
            params=params,
            calls=list(set(calls)),
            imports=list(self.imports)
        )
        self.chunks.append(chunk)


def parse_python_file(content: str, rel_path: str) -> Tuple[List[ASTChunk], List[str]]:
    """Parses Python code: prefers Tree-sitter with native ast fallback."""
    if _TREE_SITTER_AVAILABLE and "python" in _TS_PARSERS:
        try:
            chunks, imports = parse_tree_sitter(content, rel_path, "python")
            if chunks:
                return chunks, imports
        except Exception as e:
            logger.debug("Tree-sitter python error, falling back to native ast: %s", e)

    try:
        tree = ast.parse(content, filename=rel_path)
        visitor = PythonASTVisitor(content, rel_path)
        visitor.visit(tree)
        return visitor.chunks, visitor.imports
    except Exception:
        return parse_polyglot_regex(content, rel_path, is_python=True)


def parse_polyglot_regex(content: str, rel_path: str, is_python: bool = False) -> Tuple[List[ASTChunk], List[str]]:
    """Universal fallback regex chunker supporting 100+ programming languages."""
    lines = content.splitlines()
    chunks: List[ASTChunk] = []
    imports: List[str] = []

    pattern = re.compile(
        r"^\s*(?:(?:pub(?:lic)?|private|protected|internal|export|default|async|static|final|abstract|override|open|sealed|inline)\s+)*"
        r"(def|class|function|fn|func|fun|sub|procedure|proc|struct|interface|trait|type|enum|protocol|record|actor|module|contract|union)\s+"
        r"([a-zA-Z0-9_]+)",
        re.MULTILINE | re.IGNORECASE
    )

    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            keyword = m.group(1).lower()
            name = m.group(2)
            start_line = i
            end_line = min(len(lines), start_line + 35)
            code_slice = "\n".join(lines[start_line - 1 : end_line])
            calls = list(set(re.findall(r"\b([a-zA-Z0-9_]{3,30})\s*\(", code_slice)))

            bases: List[str] = []
            if keyword in ("def", "function", "fn", "func", "fun", "sub", "procedure", "proc"):
                kind = "function"
            elif keyword in ("interface", "trait", "protocol"):
                kind = "interface"
            elif keyword in ("type", "enum", "union"):
                kind = "type_alias"
            elif keyword in ("struct", "record"):
                kind = "struct"
            else:
                kind = "class"
                inherit_m = re.search(r"class\s+[a-zA-Z0-9_]+\s*(?:\(([^)]+)\)|extends\s+([a-zA-Z0-9_,\s]+)|:\s*([^{:]+))", line)
                if inherit_m:
                    raw_b = inherit_m.group(1) or inherit_m.group(2) or inherit_m.group(3) or ""
                    bases = [b.strip() for b in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", raw_b) if b.strip() not in ("public", "private", "protected", "implements", "extends")]

            chunks.append(ASTChunk(
                name=name,
                kind=kind,
                file_path=rel_path,
                start_line=start_line,
                end_line=end_line,
                code=code_slice,
                calls=calls,
                bases=bases
            ))

    return chunks, imports


# ─────────────────────────────────────────────────────────────────────────────
# Main AST Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def parse_file_ast(content: str, rel_path: str) -> Tuple[List[ASTChunk], List[str]]:
    """Dispatches to Tree-sitter or compiler AST based on file extension or basename."""
    norm_path = rel_path.replace("\\", "/").lower()
    ext = posixpath.splitext(norm_path)[1]
    basename = posixpath.basename(norm_path)

    if ext == ".py":
        return parse_python_file(content, rel_path)

    if _TREE_SITTER_AVAILABLE:
        lang_map = {
            # TypeScript / JavaScript
            ".ts": "typescript",
            ".mts": "typescript",
            ".cts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".jsx": "javascript",
            # Rust / Go / Java
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            # C / C++
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".hh": "cpp",
            ".c++": "cpp",
            ".h++": "cpp",
            # C#
            ".cs": "c_sharp",
            ".csx": "c_sharp",
            # Ruby
            ".rb": "ruby",
            ".rake": "ruby",
            ".gemspec": "ruby",
            # PHP
            ".php": "php",
            ".phtml": "php",
            ".php3": "php",
            ".php4": "php",
            ".php5": "php",
            ".phps": "php",
            # Shell / Bash
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".ksh": "bash",
            # Lua
            ".lua": "lua",
            # Scala
            ".scala": "scala",
            ".sc": "scala",
            # Kotlin
            ".kt": "kotlin",
            ".kts": "kotlin",
            # Swift
            ".swift": "swift",
            # SQL
            ".sql": "sql",
            ".psql": "sql",
            # Elixir
            ".ex": "elixir",
            ".exs": "elixir",
            # Zig
            ".zig": "zig",
            # Web
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "css",
            # Data / Config / Markup
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".md": "markdown",
            ".markdown": "markdown",
            # Build files
            ".mk": "make",
            ".cmake": "cmake",
        }
        lang_key = lang_map.get(ext)
        if not lang_key:
            if basename in ("makefile", "gnumakefile"):
                lang_key = "make"
            elif basename in ("cmakelists.txt",):
                lang_key = "cmake"
            elif basename in ("rakefile", "gemfile"):
                lang_key = "ruby"

        if lang_key and lang_key in _TS_PARSERS:
            try:
                chunks, imports = parse_tree_sitter(content, rel_path, lang_key)
                if chunks:
                    return chunks, imports
            except Exception as e:
                logger.debug("Tree-sitter parse error for %s (%s): %s", rel_path, lang_key, e)

    return parse_polyglot_regex(content, rel_path)
