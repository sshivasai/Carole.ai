"""
Filesystem tools for reading, writing, editing, and managing files
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Any
from . import battlefield_tool


@battlefield_tool(
    name="read_file",
    description="Read the entire contents of a file",
    category="filesystem",
    parameters={
        "path": {"type": "string", "required": True, "description": "File path to read"}
    }
)
def read_file(path: str) -> str:
    """Read file contents"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"✓ Read {len(content)} characters from {path}\n\n{content}"
    except Exception as e:
        return f"✗ Error reading {path}: {str(e)}"


@battlefield_tool(
    name="write_file",
    description="Write content to a file (creates or overwrites)",
    category="filesystem",
    requires_confirmation=True,
    parameters={
        "path": {"type": "string", "required": True, "description": "File path to write"},
        "content": {"type": "string", "required": True, "description": "Content to write"}
    }
)
def write_file(path: str, content: str) -> str:
    """Write content to a file"""
    try:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"✓ Wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"✗ Error writing {path}: {str(e)}"


@battlefield_tool(
    name="append_file",
    description="Append content to the end of a file",
    category="filesystem",
    parameters={
        "path": {"type": "string", "required": True, "description": "File path"},
        "content": {"type": "string", "required": True, "description": "Content to append"}
    }
)
def append_file(path: str, content: str) -> str:
    """Append to a file"""
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        return f"✓ Appended {len(content)} characters to {path}"
    except Exception as e:
        return f"✗ Error appending to {path}: {str(e)}"


@battlefield_tool(
    name="delete_file",
    description="Delete a file",
    category="filesystem",
    requires_confirmation=True,
    parameters={
        "path": {"type": "string", "required": True, "description": "File path to delete"}
    }
)
def delete_file(path: str) -> str:
    """Delete a file"""
    try:
        os.remove(path)
        return f"✓ Deleted {path}"
    except Exception as e:
        return f"✗ Error deleting {path}: {str(e)}"


@battlefield_tool(
    name="list_files",
    description="List files and directories in a path",
    category="filesystem",
    parameters={
        "path": {"type": "string", "required": False, "description": "Directory path (defaults to current dir)"},
        "recursive": {"type": "boolean", "required": False, "description": "List recursively"}
    }
)
def list_files(path: str = ".", recursive: bool = False) -> str:
    """List files in directory"""
    try:
        result = []
        if recursive:
            for root, dirs, files in os.walk(path):
                level = root.replace(path, '').count(os.sep)
                indent = ' ' * 2 * level
                result.append(f"{indent}{os.path.basename(root)}/")
                sub_indent = ' ' * 2 * (level + 1)
                for file in files:
                    result.append(f"{sub_indent}{file}")
        else:
            items = os.listdir(path)
            for item in sorted(items):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    result.append(f"{item}/")
                else:
                    size = os.path.getsize(full_path)
                    result.append(f"{item} ({size} bytes)")

        return f"✓ Contents of {path}:\n\n" + "\n".join(result)
    except Exception as e:
        return f"✗ Error listing {path}: {str(e)}"


@battlefield_tool(
    name="move_file",
    description="Move or rename a file",
    category="filesystem",
    requires_confirmation=True,
    parameters={
        "source": {"type": "string", "required": True, "description": "Source file path"},
        "destination": {"type": "string", "required": True, "description": "Destination file path"}
    }
)
def move_file(source: str, destination: str) -> str:
    """Move/rename a file"""
    try:
        shutil.move(source, destination)
        return f"✓ Moved {source} → {destination}"
    except Exception as e:
        return f"✗ Error moving {source}: {str(e)}"


@battlefield_tool(
    name="copy_file",
    description="Copy a file to another location",
    category="filesystem",
    parameters={
        "source": {"type": "string", "required": True, "description": "Source file path"},
        "destination": {"type": "string", "required": True, "description": "Destination file path"}
    }
)
def copy_file(source: str, destination: str) -> str:
    """Copy a file"""
    try:
        shutil.copy2(source, destination)
        return f"✓ Copied {source} → {destination}"
    except Exception as e:
        return f"✗ Error copying {source}: {str(e)}"


@battlefield_tool(
    name="create_directory",
    description="Create a new directory (including parent directories)",
    category="filesystem",
    parameters={
        "path": {"type": "string", "required": True, "description": "Directory path to create"}
    }
)
def create_directory(path: str) -> str:
    """Create a directory"""
    try:
        os.makedirs(path, exist_ok=True)
        return f"✓ Created directory {path}"
    except Exception as e:
        return f"✗ Error creating directory {path}: {str(e)}"


@battlefield_tool(
    name="search_files",
    description="Search for files by name pattern",
    category="filesystem",
    parameters={
        "pattern": {"type": "string", "required": True, "description": "Filename pattern (e.g., '*.py')"},
        "path": {"type": "string", "required": False, "description": "Directory to search in (defaults to current)"}
    }
)
def search_files(pattern: str, path: str = ".") -> str:
    """Search for files matching a pattern"""
    try:
        matches = list(Path(path).rglob(pattern))
        if not matches:
            return f"✗ No files matching '{pattern}' found in {path}"

        result = [f"✓ Found {len(matches)} files matching '{pattern}':\n"]
        for match in matches:
            result.append(f"  {match}")

        return "\n".join(result)
    except Exception as e:
        return f"✗ Error searching for {pattern}: {str(e)}"
