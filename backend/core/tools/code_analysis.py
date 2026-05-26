"""
Code analysis tools: linting, syntax checking, dependency analysis
"""

import ast
import subprocess
from typing import Optional, List, Dict, Any
from pathlib import Path
from . import battlefield_tool


@battlefield_tool(
    name="check_syntax",
    description="Check Python file for syntax errors",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "Python file path"}
    }
)
def check_syntax(path: str) -> str:
    """Check Python syntax"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            code = f.read()

        ast.parse(code)
        return f"✓ {path} has valid Python syntax"

    except SyntaxError as e:
        return f"✗ Syntax error in {path}:\n  Line {e.lineno}: {e.msg}\n  {e.text}"
    except Exception as e:
        return f"✗ Error checking {path}: {str(e)}"


@battlefield_tool(
    name="lint_code",
    description="Run linter on code file (supports pylint, flake8, eslint)",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "File path to lint"},
        "linter": {"type": "string", "required": False, "description": "Linter to use (auto-detect if omitted)"}
    }
)
def lint_code(path: str, linter: Optional[str] = None) -> str:
    """Lint code file"""
    try:
        # Auto-detect linter based on file extension
        ext = Path(path).suffix

        if linter is None:
            if ext == '.py':
                linter = 'pylint'
            elif ext in ['.js', '.jsx', '.ts', '.tsx']:
                linter = 'eslint'
            else:
                return f"✗ Cannot auto-detect linter for {ext} files"

        # Check if linter exists
        check = subprocess.run(
            f"which {linter}",
            shell=True,
            capture_output=True
        )

        if check.returncode != 0:
            return f"✗ {linter} not found. Install it first."

        # Run linter
        result = subprocess.run(
            f"{linter} {path}",
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = result.stdout + result.stderr

        if result.returncode == 0:
            return f"✓ {path} passed {linter} checks\n\n{output}"
        else:
            return f"⚠ {linter} found issues in {path}:\n\n{output}"

    except subprocess.TimeoutExpired:
        return f"✗ Linting timed out for {path}"
    except Exception as e:
        return f"✗ Error linting {path}: {str(e)}"


@battlefield_tool(
    name="analyze_imports",
    description="Analyze imports/dependencies in a Python file",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "Python file path"}
    }
)
def analyze_imports(path: str) -> str:
    """Analyze Python imports"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        imports = []
        from_imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    from_imports.append(f"{module}.{alias.name}" if module else alias.name)

        result = [f"✓ Imports in {path}:"]

        if imports:
            result.append("\nDirect imports:")
            for imp in sorted(set(imports)):
                result.append(f"  - {imp}")

        if from_imports:
            result.append("\nFrom imports:")
            for imp in sorted(set(from_imports)):
                result.append(f"  - {imp}")

        if not imports and not from_imports:
            result.append("  No imports found")

        return "\n".join(result)

    except Exception as e:
        return f"✗ Error analyzing imports: {str(e)}"


@battlefield_tool(
    name="count_lines",
    description="Count lines of code (total, code, comments, blank)",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "File or directory path"}
    }
)
def count_lines(path: str) -> str:
    """Count lines of code"""
    try:
        path_obj = Path(path)

        def count_file(file_path: Path) -> Dict[str, int]:
            """Count lines in a single file"""
            total = 0
            code = 0
            comments = 0
            blank = 0

            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    total += 1
                    stripped = line.strip()

                    if not stripped:
                        blank += 1
                    elif stripped.startswith('#') or stripped.startswith('//'):
                        comments += 1
                    else:
                        code += 1

            return {
                'total': total,
                'code': code,
                'comments': comments,
                'blank': blank
            }

        if path_obj.is_file():
            counts = count_file(path_obj)
            return f"✓ Lines in {path}:\n  Total: {counts['total']}\n  Code: {counts['code']}\n  Comments: {counts['comments']}\n  Blank: {counts['blank']}"

        elif path_obj.is_dir():
            # Count all Python files
            total_counts = {'total': 0, 'code': 0, 'comments': 0, 'blank': 0}
            file_count = 0

            for file in path_obj.rglob('*.py'):
                counts = count_file(file)
                for key in total_counts:
                    total_counts[key] += counts[key]
                file_count += 1

            return f"✓ Lines in {path} ({file_count} Python files):\n  Total: {total_counts['total']}\n  Code: {total_counts['code']}\n  Comments: {total_counts['comments']}\n  Blank: {total_counts['blank']}"

        else:
            return f"✗ Path not found: {path}"

    except Exception as e:
        return f"✗ Error counting lines: {str(e)}"


@battlefield_tool(
    name="find_todos",
    description="Find TODO, FIXME, HACK comments in code",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "File or directory path"}
    }
)
def find_todos(path: str) -> str:
    """Find TODO comments"""
    try:
        path_obj = Path(path)
        todos = []

        def scan_file(file_path: Path):
            """Scan a file for TODO comments"""
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line_num, line in enumerate(f, 1):
                        for marker in ['TODO', 'FIXME', 'HACK', 'XXX', 'BUG']:
                            if marker in line:
                                todos.append({
                                    'file': str(file_path),
                                    'line': line_num,
                                    'marker': marker,
                                    'text': line.strip()
                                })
                                break
            except:
                pass

        if path_obj.is_file():
            scan_file(path_obj)
        elif path_obj.is_dir():
            for file in path_obj.rglob('*'):
                if file.is_file() and file.suffix in ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go']:
                    scan_file(file)

        if not todos:
            return f"✓ No TODO/FIXME comments found in {path}"

        result = [f"✓ Found {len(todos)} TODO/FIXME comments:\n"]

        for todo in todos:
            result.append(f"[{todo['marker']}] {todo['file']}:{todo['line']}")
            result.append(f"  {todo['text']}\n")

        return "\n".join(result)

    except Exception as e:
        return f"✗ Error finding TODOs: {str(e)}"


@battlefield_tool(
    name="analyze_complexity",
    description="Analyze code complexity (functions, classes, lines per function)",
    category="code_analysis",
    parameters={
        "path": {"type": "string", "required": True, "description": "Python file path"}
    }
)
def analyze_complexity(path: str) -> str:
    """Analyze code complexity"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        functions = []
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Count lines in function
                if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
                    lines = node.end_lineno - node.lineno
                else:
                    lines = 0

                functions.append({
                    'name': node.name,
                    'lines': lines,
                    'args': len(node.args.args)
                })

            elif isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                classes.append({
                    'name': node.name,
                    'methods': len(methods)
                })

        result = [f"✓ Complexity analysis for {path}:\n"]

        if classes:
            result.append(f"Classes: {len(classes)}")
            for cls in classes:
                result.append(f"  - {cls['name']} ({cls['methods']} methods)")

        if functions:
            result.append(f"\nFunctions: {len(functions)}")
            long_functions = [f for f in functions if f['lines'] > 50]

            if long_functions:
                result.append(f"\n⚠ Long functions (>50 lines):")
                for func in long_functions:
                    result.append(f"  - {func['name']}: {func['lines']} lines")

        return "\n".join(result)

    except Exception as e:
        return f"✗ Error analyzing complexity: {str(e)}"
