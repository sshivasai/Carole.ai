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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# Tree-sitter AST Extraction (Semble Pattern)
# ─────────────────────────────────────────────────────────────────────────────

def _get_node_text(node: Any, content_bytes: bytes) -> str:
    """Returns utf-8 string for a Tree-sitter AST node."""
    return content_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def parse_tree_sitter(content: str, rel_path: str, lang_key: str) -> Tuple[List[ASTChunk], List[str]]:
    """Extracts functional units using Tree-sitter grammars."""
    parser = _TS_PARSERS.get(lang_key)
    if not parser:
        return [], []

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
        "constructor_declaration"
    }
    CLASS_TYPES = {
        "class_definition", "class_declaration", "struct_item", "impl_item",
        "trait_item", "type_declaration", "class_specifier", "struct_specifier",
        "record_declaration", "namespace_definition"
    }
    TYPE_TYPES = {
        "interface_declaration", "type_alias_declaration", "enum_declaration",
        "enum_item", "enum_specifier", "struct_declaration"
    }
    IMPORT_TYPES = {
        "import_statement", "import_from_statement", "use_declaration",
        "import_declaration", "using_directive", "preproc_include"
    }

    def walk(node: Any, current_parent: Optional[str] = None):
        ntype = node.type

        # Extract Imports
        if ntype in IMPORT_TYPES or ntype == "use_declaration":
            raw_imp = _get_node_text(node, content_bytes).strip()
            imports.append(raw_imp)
            for mod in re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", raw_imp):
                if mod not in ("import", "from", "as", "use", "pub", "crate", "using", "include"):
                    imports.append(mod)
            return

        # Extract Functions / Methods
        if ntype in FUNC_TYPES:
            name = None
            params = []
            calls = []

            for child in node.children:
                if child.type in ("identifier", "name", "property_identifier", "field_identifier"):
                    if not name:
                        name = _get_node_text(child, content_bytes)
                elif child.type == "function_declarator":
                    for sub in child.children:
                        if sub.type in ("identifier", "field_identifier"):
                            if not name:
                                name = _get_node_text(sub, content_bytes)
                        elif sub.type in ("parameter_list", "parameters"):
                            raw_params = _get_node_text(sub, content_bytes)
                            params = [p.strip().split(":")[0].strip() for p in raw_params.strip("()").split(",") if p.strip()]
                elif child.type in ("parameters", "formal_parameters", "parameter_list"):
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
                if child.type in ("identifier", "name", "type_identifier"):
                    name = _get_node_text(child, content_bytes)
                    break

            if name:
                start_line = node.start_point.row + 1
                end_line = node.end_point.row + 1
                code_slice = "\n".join(lines[start_line - 1 : end_line])

                kind = "class"
                if "interface" in ntype: kind = "interface"
                elif "type" in ntype: kind = "type_alias"
                elif "enum" in ntype: kind = "enum"
                elif "struct" in ntype: kind = "struct"
                elif "trait" in ntype: kind = "trait"

                chunks.append(ASTChunk(
                    name=name,
                    kind=kind,
                    file_path=rel_path,
                    start_line=start_line,
                    end_line=end_line,
                    code=code_slice,
                    parent_symbol=current_parent,
                    imports=list(imports)
                ))

                # Recurse inside class body with updated parent
                for child in node.children:
                    walk(child, current_parent=name)
                return

        for child in node.children:
            walk(child, current_parent=current_parent)

    walk(root)
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
        mod = node.module or ""
        for alias in node.names:
            self.imports.append(f"{mod}.{alias.name}" if mod else alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name

        start = node.lineno
        end = getattr(node, "end_lineno", start + len(node.body))
        code_slice = "\n".join(self.lines[start - 1 : end])
        doc = ast.get_docstring(node)

        chunk = ASTChunk(
            name=node.name,
            kind="class",
            file_path=self.rel_path,
            start_line=start,
            end_line=end,
            code=code_slice,
            docstring=doc,
            parent_symbol=prev_class,
            imports=list(self.imports)
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
    """Emergency fallback regex chunker when syntax is unparseable."""
    lines = content.splitlines()
    chunks: List[ASTChunk] = []
    imports: List[str] = []

    pattern = re.compile(
        r"^\s*(?:pub\s+)?(?:export\s+)?(?:async\s+)?(?:fn|func|def|class|struct|interface|type)\s+([a-zA-Z0-9_]+)",
        re.MULTILINE
    )

    for i, line in enumerate(lines, 1):
        m = pattern.search(line)
        if m:
            name = m.group(1)
            start_line = i
            end_line = min(len(lines), start_line + 35)
            code_slice = "\n".join(lines[start_line - 1 : end_line])
            calls = list(set(re.findall(r"\b([a-zA-Z0-9_]{3,30})\s*\(", code_slice)))
            chunks.append(ASTChunk(
                name=name,
                kind="function" if any(k in line for k in ("fn", "func", "def")) else "class",
                file_path=rel_path,
                start_line=start_line,
                end_line=end_line,
                code=code_slice,
                calls=calls,
            ))

    return chunks, imports


# ─────────────────────────────────────────────────────────────────────────────
# Main AST Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def parse_file_ast(content: str, rel_path: str) -> Tuple[List[ASTChunk], List[str]]:
    """Dispatches to Tree-sitter or compiler AST based on file extension."""
    norm_path = rel_path.replace("\\", "/").lower()
    ext = posixpath.splitext(norm_path)[1]

    if ext == ".py":
        return parse_python_file(content, rel_path)

    if _TREE_SITTER_AVAILABLE:
        lang_map = {
            ".ts": "typescript",
            ".tsx": "tsx",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".cs": "c_sharp",
        }
        lang_key = lang_map.get(ext)
        if lang_key and lang_key in _TS_PARSERS:
            try:
                chunks, imports = parse_tree_sitter(content, rel_path, lang_key)
                if chunks:
                    return chunks, imports
            except Exception as e:
                logger.debug("Tree-sitter parse error for %s (%s): %s", rel_path, lang_key, e)

    return parse_polyglot_regex(content, rel_path)
