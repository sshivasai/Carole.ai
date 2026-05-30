"""
# backend/core/tools/file_tools.py

This module contains tools for safely interacting with the local filesystem.

Responsibilities:
1. Provide `FileReadTool`, `FileWriteTool`, and `FileEditTool` for precise code modifications.
2. Provide `GlobTool` and `GrepTool` for searching directories and file contents.
3. Restrict agents from navigating outside of the designated workspace directory (sandbox enforcement).
"""

import os
from pathlib import Path
from typing import List, Dict, Any

class FileTools:
    def __init__(self, workspace_root: str = None):
        if not workspace_root:
            # Fall back to the absolute directory root of the multi-agent workspace
            # Resolved relative to this file's position in /backend/core/tools/
            workspace_root = os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parents[3]))
        self.workspace_root = Path(workspace_root).resolve()

    def _resolve_safe_path(self, relative_path: str) -> Path:
        """
        Enforce security sandboxing:
        - Resolves relative path to absolute form.
        - Verifies the path remains strictly inside self.workspace_root.
        - Raises PermissionError on any path traversal escape attempts (e.g. '../../').
        """
        # Convert path to a clean form and join with the workspace root
        joined_path = Path(self.workspace_root / relative_path)
        resolved_path = joined_path.resolve()
        
        # Verify the resolved path starts with the workspace root path string
        if not str(resolved_path).startswith(str(self.workspace_root)):
            raise PermissionError(
                f"Access Denied: Attempted path traversal to '{resolved_path}' "
                f"which is outside of the secure sandbox boundary '{self.workspace_root}'."
            )
            
        return resolved_path

    def read_file(self, relative_path: str) -> str:
        """Reads and returns the contents of a file inside the sandbox."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file or does not exist."
            with open(safe_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, relative_path: str, content: str) -> str:
        """Creates a new file or overwrites an existing one inside the sandbox."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            # Ensure parent directories exist
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Success: File '{relative_path}' successfully written ({len(content)} bytes)."
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def edit_file(self, relative_path: str, target_content: str, replacement_content: str) -> str:
        """
        Performs a precise, safe contiguous replace in a file inside the sandbox.
        Ensures the agent is modifying the exact block intended.
        """
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_file():
                return f"Error: '{relative_path}' is not a file or does not exist."
                
            with open(safe_path, "r", encoding="utf-8") as f:
                file_text = f.read()
                
            if target_content not in file_text:
                return f"Error: The target block was not found in the file text. Verify exact matches and indentation."
                
            occurrences = file_text.count(target_content)
            if occurrences > 1:
                return f"Error: Found multiple ({occurrences}) occurrences of target block. Provide a unique block to modify."
                
            updated_text = file_text.replace(target_content, replacement_content)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(updated_text)
                
            return f"Success: Modified '{relative_path}' successfully."
        except Exception as e:
            return f"Error editing file: {str(e)}"

    def list_directory(self, relative_path: str = ".") -> str:
        """Lists files and directories inside the sandbox path."""
        try:
            safe_path = self._resolve_safe_path(relative_path)
            if not safe_path.is_dir():
                return f"Error: '{relative_path}' is not a directory or does not exist."
            
            output = []
            for item in os.listdir(safe_path):
                full_item = safe_path / item
                if full_item.is_dir():
                    output.append(f"[DIR]  {item}/")
                else:
                    output.append(f"[FILE] {item} ({full_item.stat().st_size} bytes)")
            
            return "\n".join(output) if output else "Directory is empty."
        except Exception as e:
            return f"Error listing directory: {str(e)}"

# Singleton file tools instance
file_tools = FileTools()
