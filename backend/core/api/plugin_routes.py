from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import os
import re
import aiofiles

from core.config import PLUGINS_DIR
from core.tools.tool_registry import ToolRegistry
from core.auth.auth_middleware import require_auth
import core.config

router = APIRouter(prefix="/api/plugins", tags=["plugins"])

class PluginCode(BaseModel):
    code: str

class GenerateRequest(BaseModel):
    prompt: str

@router.get("")
async def list_plugins(user: dict = Depends(require_auth)):
    """List all python plugin files in the PLUGINS_DIR. Requires authentication."""
    plugins = []
    if not PLUGINS_DIR.exists():
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
        
    for p in PLUGINS_DIR.glob("*.py"):
        if p.is_file():
            async with aiofiles.open(p, "r", encoding="utf-8") as f:
                content = await f.read()
            plugins.append({
                "filename": p.name,
                "content": content
            })
    return plugins


import ast

_SAFE_PLUGIN_FILENAME_RE = re.compile(r'^[a-zA-Z0-9_-]+\.py$')


class PluginSecurityChecker(ast.NodeVisitor):
    FORBIDDEN_MODULES = {"subprocess", "shutil", "socket", "pty", "winpty", "ctypes"}
    FORBIDDEN_CALLS = {"eval", "exec", "__import__", "compile"}

    def visit_Import(self, node):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod in self.FORBIDDEN_MODULES:
                raise ValueError(f"Importing '{base_mod}' is forbidden in custom plugins for security.")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            base_mod = node.module.split(".")[0]
            if base_mod in self.FORBIDDEN_MODULES:
                raise ValueError(f"Importing from '{base_mod}' is forbidden in custom plugins for security.")
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id in self.FORBIDDEN_CALLS:
            raise ValueError(f"Calling '{node.func.id}()' is forbidden in custom plugins for security.")
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if node.func.attr in {"system", "popen", "spawn", "kill", "remove", "unlink", "rmdir"}:
                    raise ValueError(f"Calling 'os.{node.func.attr}()' is forbidden in custom plugins.")
        self.generic_visit(node)


def _validate_plugin_filename(filename: str) -> None:
    """Validate plugin filename is safe (no path traversal, no dangerous chars)."""
    if not _SAFE_PLUGIN_FILENAME_RE.match(filename):
        raise HTTPException(
            400,
            "Invalid plugin filename. Only alphanumeric, underscore, and hyphen characters are allowed (e.g. my_tool.py)."
        )
    # Double-check resolved path stays strictly inside PLUGINS_DIR
    resolved = (PLUGINS_DIR / filename).resolve()
    try:
        resolved.relative_to(PLUGINS_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "Path traversal attempt detected.")


@router.post("/{filename}")
async def save_plugin(filename: str, body: PluginCode, user: dict = Depends(require_auth)):
    """Save a plugin file and hot-reload the tool registry. Requires authentication."""
    _validate_plugin_filename(filename)
    
    # Pre-validate Python syntax and AST security before saving
    try:
        tree = ast.parse(body.code, filename=filename)
        PluginSecurityChecker().visit(tree)
    except SyntaxError as e:
        raise HTTPException(400, f"Python syntax error on line {e.lineno}: {e.msg}")
    except ValueError as e:
        raise HTTPException(400, f"Security screening rejected plugin: {e}")

    file_path = PLUGINS_DIR / filename
    
    # Save the file
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(body.code)
        
    # Reload registry
    try:
        ToolRegistry.load_plugin_directory(str(PLUGINS_DIR))
    except Exception as e:
        # If it fails to load due to syntax error, still saved but raise error
        raise HTTPException(500, f"Saved, but failed to load: {e}")
        
    from core.memory.database import async_session
    from sqlalchemy import select
    from core.memory.models import Team
    from core.chat.message_router import message_router
    from core.api.crud_routes import _get_human_name
    
    async with async_session() as db:
        result = await db.execute(select(Team.id))
        teams = result.scalars().all()
        human_name = await _get_human_name(db)
        
    for t_id in teams:
        await message_router.route_message(
            text=f"[TOOL_ADD] Custom plugin tool '{filename}' was added by {human_name}",
            sender_id="system",
            team_id=str(t_id),
            sender_name="System",
            attachments=[]
        )

    return {"ok": True, "filename": filename}

@router.delete("/{filename}")
async def delete_plugin(filename: str, user: dict = Depends(require_auth)):
    """Delete a plugin file and hot-reload the tool registry. Requires authentication."""
    _validate_plugin_filename(filename)
    file_path = PLUGINS_DIR / filename
    if file_path.exists():
        os.remove(file_path)
        try:
            ToolRegistry.load_plugin_directory(str(PLUGINS_DIR))
        except Exception:
            pass
            
        from core.memory.database import async_session
        from sqlalchemy import select
        from core.memory.models import Team
        from core.chat.message_router import message_router
        from core.api.crud_routes import _get_human_name
        
        async with async_session() as db:
            result = await db.execute(select(Team.id))
            teams = result.scalars().all()
            human_name = await _get_human_name(db)
            
        for t_id in teams:
            await message_router.route_message(
                text=f"[TOOL_DELETE] Custom plugin tool '{filename}' was removed by {human_name}",
                sender_id="system",
                team_id=str(t_id),
                sender_name="System",
                attachments=[]
            )
    return {"ok": True}

@router.post("/action/generate")
async def generate_plugin(body: GenerateRequest, user: dict = Depends(require_auth)):
    """Generate a Carole.ai compatible Python @tool plugin. Requires authentication."""
    from core.llm.multi_model_router import llm_router
    
    system_prompt = """
You are an expert Python developer for the Carole.ai multi-agent system.
Your task is to write a custom tool using the provided user request.
The tool MUST:
1. Be a standalone python function.
2. Be decorated with `@tool` from `core.tools.tool_registry`.
3. Have fully type-hinted arguments.
4. Have a detailed docstring explaining what the tool does and what the arguments are (Google or Sphinx style).
5. Catch any necessary exceptions and return descriptive error strings.
6. Only import standard library modules or commonly installed packages (e.g. requests, bs4).

Do NOT output ANY markdown formatting or ```python tags. Output ONLY the raw python code.

Example structure:
from core.tools.tool_registry import tool
import requests

@tool
def fetch_weather(city: str) -> str:
    \"\"\"Fetches the current weather for a given city.\"\"\"
    try:
        # logic here
        return f"Weather in {city} is sunny."
    except Exception as e:
        return f"Error fetching weather: {e}"
"""
    
    # Ask the LLM to generate the code
    try:
        coder_model = getattr(core.config, "DEFAULT_CODER_MODEL", "openrouter/free")
    except Exception:
        coder_model = "openrouter/free"
        
    response_text = await llm_router.generate_completion(
        model=coder_model,
        messages=[{"role": "user", "content": body.prompt}],
        system_prompt=system_prompt,
        temperature=0.2,
    )
    
    code = response_text
    # Cleanup markdown if the LLM ignored instructions
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
        
    return {"code": code.strip()}
