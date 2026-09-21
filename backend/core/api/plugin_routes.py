from core.auth.instance_owner import require_instance_owner
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
async def list_plugins(user: dict = Depends(require_instance_owner)):
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
async def save_plugin(filename: str, body: PluginCode, user: dict = Depends(require_instance_owner)):
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
    
    previous = file_path.read_text(encoding="utf-8") if file_path.exists() else None
    # Save the file
    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(body.code)
        
    # Reload registry
    try:
        ToolRegistry.load_plugin_directory(str(PLUGINS_DIR))
    except Exception as e:
        if previous is None:
            file_path.unlink(missing_ok=True)
        else:
            file_path.write_text(previous, encoding="utf-8")
        raise HTTPException(400, f"Plugin rejected; previous version retained: {e}")
        
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
async def delete_plugin(filename: str, user: dict = Depends(require_instance_owner)):
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
async def generate_plugin(body: GenerateRequest, user: dict = Depends(require_instance_owner)):
    """Generate a Carole.ai compatible Python @tool plugin. Requires authentication."""
    from core.llm.multi_model_router import llm_router
    
    system_prompt = """
Generate a trusted administrator-installed Carole Python plugin.
Return only Python source, without Markdown fences.
Import carole_tool from core.tools.tool_registry. Decorate a handler with
@carole_tool(name="descriptive_name", description="Specific purpose", category="custom",
             permission_default="judge", parameters={"value": {"type": "string", "required": True}})
The handler signature MUST be async def handler(args: dict, team_id: str) -> str.
Read declared arguments from args. The runtime supplies team_id separately.
Choose safe/judge/human permission_default according to side effects; never bypass approval.
Use workspace-aware application helpers for file operations. Never read backend credentials,
change permissions, run work at import time, or claim execution succeeded without checking it.
Handle expected failures with descriptive error strings. Use only installed dependencies.
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
