"""
Advanced search tools: glob patterns, grep content search, combined search
"""

import re
from pathlib import Path
from typing import Optional, List, Dict
from . import battlefield_tool


@battlefield_tool(
    name="glob_search",
    description="Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.js')",
    category="search",
    parameters={
        "pattern": {"type": "string", "required": True, "description": "Glob pattern"},
        "path": {"type": "string", "required": False, "description": "Root path (default: current dir)"}
    }
)
def glob_search(pattern: str, path: str = ".") -> str:
    """Search files by pattern"""
    try:
        root = Path(path)
        matches = list(root.glob(pattern))

        if not matches:
            return f"✗ No files matching '{pattern}' in {path}"

        result = [f"✓ Found {len(matches)} files matching '{pattern}':\n"]

        for match in sorted(matches):
            result.append(f"  {match}")

        return "\n".join(result)

    except Exception as e:
        return f"✗ Glob search error: {str(e)}"


@battlefield_tool(
    name="grep_search",
    description="Search for text pattern in files (supports regex)",
    category="search",
    parameters={
        "pattern": {"type": "string", "required": True, "description": "Search pattern (regex)"},
        "path": {"type": "string", "required": False, "description": "File or directory to search"},
        "file_pattern": {"type": "string", "required": False, "description": "File glob pattern (e.g., '*.py')"},
        "case_sensitive": {"type": "boolean", "required": False, "description": "Case sensitive search (default: False)"},
        "context_lines": {"type": "number", "required": False, "description": "Show N lines of context"}
    }
)
def grep_search(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    case_sensitive: bool = False,
    context_lines: int = 0
) -> str:
    """Search content with grep"""
    try:
        root = Path(path)
        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        results = []

        def search_file(file_path: Path):
            """Search in a single file"""
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        match_info = {
                            'file': str(file_path),
                            'line': line_num,
                            'text': line.rstrip()
                        }

                        # Add context if requested
                        if context_lines > 0:
                            start = max(0, line_num - context_lines - 1)
                            end = min(len(lines), line_num + context_lines)
                            match_info['context'] = [
                                f"{i+1}: {lines[i].rstrip()}"
                                for i in range(start, end)
                            ]

                        results.append(match_info)
            except:
                pass

        # Determine files to search
        if root.is_file():
            search_file(root)
        else:
            for file in root.rglob(file_pattern):
                if file.is_file():
                    search_file(file)

        if not results:
            return f"✗ Pattern '{pattern}' not found in {path}"

        # Format results
        output = [f"✓ Found {len(results)} matches for '{pattern}':\n"]

        for match in results[:50]:  # Limit to 50 matches
            output.append(f"{match['file']}:{match['line']}")

            if 'context' in match:
                output.append("\n".join(match['context']))
            else:
                output.append(f"  {match['text']}")

            output.append("")

        if len(results) > 50:
            output.append(f"... and {len(results) - 50} more matches")

        return "\n".join(output)

    except Exception as e:
        return f"✗ Grep search error: {str(e)}"


@battlefield_tool(
    name="smart_search",
    description="Combined search: find files by pattern AND search their contents",
    category="search",
    parameters={
        "file_pattern": {"type": "string", "required": True, "description": "File glob pattern"},
        "content_pattern": {"type": "string", "required": True, "description": "Content search pattern"},
        "path": {"type": "string", "required": False, "description": "Root directory"}
    }
)
def smart_search(file_pattern: str, content_pattern: str, path: str = ".") -> str:
    """Combined file + content search"""
    try:
        root = Path(path)
        regex = re.compile(content_pattern, re.IGNORECASE)

        results = []

        # Find files matching pattern
        for file in root.glob(file_pattern):
            if not file.is_file():
                continue

            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()

                matches = regex.findall(content)
                if matches:
                    results.append({
                        'file': str(file),
                        'match_count': len(matches),
                        'sample': matches[0] if matches else None
                    })
            except:
                pass

        if not results:
            return f"✗ No matches found for '{file_pattern}' containing '{content_pattern}'"

        output = [f"✓ Found {len(results)} files:\n"]

        for result in results:
            output.append(f"{result['file']}")
            output.append(f"  {result['match_count']} matches")
            if result['sample']:
                preview = result['sample'][:100]
                output.append(f"  Sample: {preview}...")
            output.append("")

        return "\n".join(output)

    except Exception as e:
        return f"✗ Smart search error: {str(e)}"


@battlefield_tool(
    name="find_function",
    description="Find function or class definitions in code",
    category="search",
    parameters={
        "name": {"type": "string", "required": True, "description": "Function/class name"},
        "path": {"type": "string", "required": False, "description": "Directory to search"}
    }
)
def find_function(name: str, path: str = ".") -> str:
    """Find function/class definitions"""
    try:
        patterns = [
            f"def {name}",      # Python
            f"function {name}", # JavaScript
            f"class {name}",    # Multiple languages
            f"const {name}",    # JavaScript/TypeScript
            f"func {name}",     # Go
        ]

        results = []
        root = Path(path)

        for file in root.rglob("*"):
            if not file.is_file() or file.suffix not in ['.py', '.js', '.ts', '.jsx', '.tsx', '.go', '.java']:
                continue

            try:
                with open(file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

                for line_num, line in enumerate(lines, 1):
                    if any(pattern in line for pattern in patterns):
                        results.append({
                            'file': str(file),
                            'line': line_num,
                            'text': line.strip()
                        })
            except:
                pass

        if not results:
            return f"✗ Definition for '{name}' not found"

        output = [f"✓ Found {len(results)} definitions for '{name}':\n"]

        for result in results:
            output.append(f"{result['file']}:{result['line']}")
            output.append(f"  {result['text']}\n")

        return "\n".join(output)

    except Exception as e:
        return f"✗ Find function error: {str(e)}"
