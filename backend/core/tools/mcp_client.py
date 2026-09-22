from __future__ import annotations

import os
import sys
import shutil
import logging
import asyncio
from typing import TextIO, Dict, List, Optional, Any, Tuple, Union
from contextlib import asynccontextmanager, AsyncExitStack

from core.tools.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger("mcp_client")

try:
    import anyio
    from pydantic import TypeAdapter
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
    from anyio.streams.text import TextReceiveStream
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.shared.message import SessionMessage
    from mcp.client.stdio import (
        stdio_client,
        get_default_environment,
        _get_executable_command,
        _create_platform_compatible_process,
        _terminate_process_tree,
        PROCESS_TERMINATION_TIMEOUT,
    )

    @asynccontextmanager
    async def safe_stdio_client(server: StdioServerParameters, errlog: TextIO = sys.stderr):
        """
        Resilient client transport for stdio: filters out Windows cmd banner lines,
        AutoRun outputs, empty lines, and non-JSON stdout messages before parsing.
        """
        read_stream: MemoryObjectReceiveStream[Union[SessionMessage, Exception]]
        read_stream_writer: MemoryObjectSendStream[Union[SessionMessage, Exception]]

        write_stream: MemoryObjectSendStream[SessionMessage]
        write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

        read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
        write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

        try:
            command = _get_executable_command(server.command)
            process = await _create_platform_compatible_process(
                command=command,
                args=server.args,
                env=({**get_default_environment(), **server.env} if server.env is not None else get_default_environment()),
                errlog=errlog,
                cwd=server.cwd,
            )
        except OSError:
            await read_stream.aclose()
            await write_stream.aclose()
            await read_stream_writer.aclose()
            await write_stream_reader.aclose()
            raise

        async def stdout_reader():
            assert process.stdout, "Opened process is missing stdout"
            try:
                async with read_stream_writer:
                    buffer = ""
                    async for chunk in TextReceiveStream(
                        process.stdout,
                        encoding=server.encoding,
                        errors=server.encoding_error_handler,
                    ):
                        lines = (buffer + chunk).split("\n")
                        buffer = lines.pop()
                        if len(buffer) > 8 * 1024 * 1024:
                            raise ValueError("MCP stdout line exceeds 8 MiB")

                        for line in lines:
                            trimmed = line.strip()
                            if not trimmed:
                                continue

                            # Extract embedded JSON-RPC message if preceded by cmd prompt or banner
                            json_start = trimmed.find('{"jsonrpc"')
                            if json_start != -1:
                                trimmed = trimmed[json_start:]
                            elif not (trimmed.startswith("{") or trimmed.startswith("[")):
                                # Skip non-JSON banner, warning, or status line without raising validation error
                                logger.debug("[MCP stdio noise filtered] %s", trimmed)
                                continue

                            try:
                                message = TypeAdapter(types.JSONRPCMessage).validate_json(trimmed)
                            except Exception:
                                logger.debug("[MCP stdio invalid JSON skipped] %s", trimmed)
                                continue

                            session_message = SessionMessage(message)
                            await read_stream_writer.send(session_message)
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                await anyio.lowlevel.checkpoint()

        async def stdin_writer():
            assert process.stdin, "Opened process is missing stdin"
            try:
                async with write_stream_reader:
                    async for session_message in write_stream_reader:
                        json_str = session_message.message.model_dump_json(by_alias=True, exclude_none=True)
                        await process.stdin.send(
                            (json_str + "\n").encode(
                                encoding=server.encoding,
                                errors=server.encoding_error_handler,
                            )
                        )
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                await anyio.lowlevel.checkpoint()

        async with anyio.create_task_group() as tg, process:
            tg.start_soon(stdout_reader)
            tg.start_soon(stdin_writer)
            try:
                yield read_stream, write_stream
            finally:
                if process.stdin:
                    try:
                        await process.stdin.aclose()
                    except Exception:
                        pass

                try:
                    with anyio.fail_after(PROCESS_TERMINATION_TIMEOUT):
                        await process.wait()
                except TimeoutError:
                    await _terminate_process_tree(process)
                except ProcessLookupError:
                    pass
                await read_stream.aclose()
                await write_stream.aclose()
                await read_stream_writer.aclose()
                await write_stream_reader.aclose()

except ImportError:
    safe_stdio_client = None
    stdio_client = None


class MCPManager:
    """
    Singleton class that manages active MCP server connections.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPManager, cls).__new__(cls)
            cls._instance.exit_stacks = {}
            cls._instance.sessions = {}
            cls._instance.statuses = {}
            cls._instance.connection_tasks = {}
            cls._instance.connection_stops = {}
            cls._instance.connection_locks = {}
        return cls._instance

    @property
    def exit_stack(self):
        """Backward compatibility for any callers expecting a single exit stack."""
        if not hasattr(self, "_fallback_stack"):
            self._fallback_stack = AsyncExitStack()
        return self._fallback_stack

    async def _close_stack(self, stack: AsyncExitStack, server_name: str = ""):
        """Safely close an AsyncExitStack without crashing on AnyIO cross-task cancel scopes."""
        try:
            await stack.aclose()
        except Exception as e:
            # AnyIO raises RuntimeError when an AsyncExitStack that entered a TaskGroup
            # is closed from a different asyncio task than the one that entered it.
            # Child process and streams are already cleaned up in the generator's finally block.
            logger.debug("[MCP] Exit stack cleanup note for %s: %s", server_name, e)
        except BaseException as e:
            if type(e).__name__ in ("BaseExceptionGroup", "ExceptionGroup"):
                logger.debug("[MCP] Exit stack group note for %s: %s", server_name, e)
            else:
                raise

    async def shutdown(self):
        """Safely close all MCP server connections and resources."""
        for key in list(self.connection_tasks):
            await self._stop_connection(key)
        for key, stack in list(self.exit_stacks.items()):
            server_name = key[2] if len(key) > 2 else "unknown"
            await self._close_stack(stack, server_name)
        self.exit_stacks.clear()
        self.sessions.clear()
        self.statuses.clear()
        if hasattr(self, "_fallback_stack"):
            await self._close_stack(self._fallback_stack, "fallback")

    async def disconnect_server(self, team_id: str = None, agent_id: str = None, server_name: str = None):
        """
        Disconnects an MCP server, closes its session, removes from statuses,
        and unregisters all associated tools from ToolRegistry.
        """
        if not server_name:
            return

        keys_to_remove = []
        requested_team = str(team_id) if team_id else "None"
        for key in list(self.statuses):
            k_team, k_agent, k_server = key
            if (k_server == server_name and k_team == requested_team
                    and (agent_id is None or k_agent == str(agent_id))):
                keys_to_remove.append(key)
        for key in keys_to_remove:
            if key in self.connection_tasks:
                async with self.connection_locks.setdefault(key, asyncio.Lock()):
                    await self._stop_connection(key)
                continue
            status = self.statuses.pop(key)
            for name in status.get("tools", []):
                ToolRegistry.unregister(name)
            self.sessions.pop(key, None)
            stack = self.exit_stacks.pop(key, None)
            if stack:
                await self._close_stack(stack, server_name)


    async def _stop_connection(self, key):
        task = self.connection_tasks.get(key)
        stop = self.connection_stops.get(key)
        if task is not None:
            if stop is not None:
                stop.set()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=30)
            except TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.connection_tasks.pop(key, None)
        self.connection_stops.pop(key, None)
        status = self.statuses.pop(key, {})
        for name in status.get("tools", []):
            ToolRegistry.unregister(name)
        self.sessions.pop(key, None)

    async def connect_stdio_server(self, server_name: str, command: str, args: list[str],
                                   team_id: str = None, agent_id: str = None,
                                   env_vars: dict = None, init_timeout: float = 120.0):
        """A dedicated task owns each AnyIO context from entry through cleanup."""
        key = (str(team_id) if team_id else "None", str(agent_id) if agent_id else "global", server_name)
        async with self.connection_locks.setdefault(key, asyncio.Lock()):
            if key in self.connection_tasks:
                await self._stop_connection(key)
            ready = asyncio.get_running_loop().create_future()
            stop = asyncio.Event()

            async def own_connection():
                try:
                    await self._connect_stdio_server(server_name, command, args, team_id, agent_id, env_vars, init_timeout)
                    if not ready.done():
                        ready.set_result(None)
                    await stop.wait()
                except BaseException as exc:
                    if not ready.done():
                        ready.set_exception(exc)
                    elif not isinstance(exc, asyncio.CancelledError):
                        logger.exception("MCP connection ended unexpectedly: %s", server_name)
                finally:
                    for name in self.statuses.get(key, {}).get("tools", []):
                        ToolRegistry.unregister(name)
                    self.sessions.pop(key, None)
                    stack = self.exit_stacks.pop(key, None)
                    if stack:
                        await self._close_stack(stack, server_name)
                    status = self.statuses.get(key)
                    if status and status.get("status") == "connected":
                        status["status"] = "disconnected"
                        status["tools"] = []

            self.connection_stops[key] = stop
            task = asyncio.create_task(own_connection(), name=f"mcp:{server_name}")
            self.connection_tasks[key] = task
            try:
                await asyncio.shield(ready)
            except BaseException:
                stop.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self.connection_tasks.pop(key, None)
                self.connection_stops.pop(key, None)
                raise

    async def _connect_stdio_server(
        self,
        server_name: str,
        command: str,
        args: list[str],
        team_id: str = None,
        agent_id: str = None,
        env_vars: dict = None,
        init_timeout: float = 120.0,
    ):
        """
        Connects to an MCP server via stdio, extracts its tools, 
        and registers them in the Carole ToolRegistry.
        """
        resolved_command = shutil.which(command) or command
        resolved_args = list(args) if args else []

        # On Windows, resolve npx/npm to direct node.exe + cli.js execution to bypass cmd.exe wrapper
        if sys.platform == "win32":
            cmd_lower = command.lower()
            if cmd_lower in ("npx", "npx.cmd") or (resolved_command and resolved_command.lower().endswith("npx.cmd")):
                node_exe = shutil.which("node") or shutil.which("node.exe")
                if node_exe:
                    node_dir = os.path.dirname(node_exe)
                    candidates = [
                        os.path.join(node_dir, "node_modules", "npm", "bin", "npx-cli.js"),
                        os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules", "npm", "bin", "npx-cli.js"),
                        os.path.join(node_dir, "node_modules", "corepack", "dist", "npx.js"),
                    ]
                    npx_cli = next((p for p in candidates if os.path.exists(p)), None)
                    if npx_cli:
                        resolved_command = node_exe
                        resolved_args = [npx_cli] + resolved_args
            elif cmd_lower in ("npm", "npm.cmd") or (resolved_command and resolved_command.lower().endswith("npm.cmd")):
                node_exe = shutil.which("node") or shutil.which("node.exe")
                if node_exe:
                    node_dir = os.path.dirname(node_exe)
                    candidates = [
                        os.path.join(node_dir, "node_modules", "npm", "bin", "npm-cli.js"),
                        os.path.join(os.environ.get("APPDATA", ""), "npm", "node_modules", "npm", "bin", "npm-cli.js"),
                    ]
                    npm_cli = next((p for p in candidates if os.path.exists(p)), None)
                    if npm_cli:
                        resolved_command = node_exe
                        resolved_args = [npm_cli] + resolved_args

        # Key matches the format expected by delete_mcp_server
        key = (str(team_id) if team_id else "None", str(agent_id) if agent_id else "global", server_name)
        
        # Invalidate handlers before closing the session they captured.
        for old_name in self.statuses.get(key, {}).get("tools", []):
            ToolRegistry.unregister(old_name)
        self.sessions.pop(key, None)
        # Close existing stack if reconnecting
        old_stack = self.exit_stacks.pop(key, None)
        if old_stack:
            await self._close_stack(old_stack, server_name)

        server_stack = AsyncExitStack()
        self.exit_stacks[key] = server_stack

        self.statuses[key] = {
            "server_name": server_name,
            "team_id": team_id,
            "agent_id": agent_id,
            "status": "loading",
            "tools": [],
        }
        try:
            # MCP servers receive only transport/runtime variables plus secrets
            # explicitly assigned to that connection, never backend credentials.
            merged_env = get_default_environment()
            if env_vars:
                merged_env.update(env_vars)
            server_parameters = StdioServerParameters(command=resolved_command, args=resolved_args, env=merged_env)
        
            # Connect to stdio server using safe_stdio_client
            client_cm = safe_stdio_client(server_parameters) if safe_stdio_client else stdio_client(server_parameters)
            stdio_transport = await server_stack.enter_async_context(client_cm)
            read_stream, write_stream = stdio_transport[0], stdio_transport[1]
        
            # Initialize session with 120s timeout (configurable via MCP_INIT_TIMEOUT) to allow cold-boot package installation (e.g. uvx/npx)
            session = await server_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await asyncio.wait_for(session.initialize(), timeout=init_timeout)
        
            self.sessions[key] = session
        
            # List tools and register with 30s timeout
            tools_response = await asyncio.wait_for(session.list_tools(), timeout=30.0)
        
            registered_tools = []
            for tool in tools_response.tools:
                tool_name = tool.name
            
                # create a closure for the handler to capture tool_name and session properly
                async def tool_handler(args_dict: dict, team_id: str = None, _session=session, _name=tool_name) -> str:
                    try:
                        # Remove internal context objects before sending to MCP server
                        args_to_send = dict(args_dict)
                        args_to_send.pop("cancellation_token", None)
                        args_to_send.pop("context", None)
                        args_to_send.pop("team_id", None)
                        for internal_key in ("_agent_id", "_agent_name", "_active_message_id", "_team_id", "_context", "_server_approved", "_human_confirmed"):
                            args_to_send.pop(internal_key, None)
                    
                        # Bounded 60s execution timeout prevents indefinite agent hangs
                        result = await asyncio.wait_for(_session.call_tool(_name, arguments=args_to_send), timeout=60.0)
                        if hasattr(result, "content") and result.content:
                            # Extract text from content blocks and intercept images
                            text_results = []
                            for block in result.content:
                                is_image = False
                                b64 = None
                                mime = "image/png"
                            
                                if hasattr(block, "type") and block.type == "image":
                                    is_image = True
                                    b64 = getattr(block, "data", "")
                                    mime = getattr(block, "mimeType", mime)
                                elif isinstance(block, dict) and block.get("type") == "image":
                                    is_image = True
                                    b64 = block.get("data", "")
                                    mime = block.get("mimeType", mime)
                                
                                if is_image and b64:
                                    if team_id:
                                        from core.chat.event_bus import event_bus
                                        # Publish to UI async so we don't block
                                        asyncio.create_task(event_bus.publish(f"team:{team_id}", {
                                             "type": "browser_screenshot",
                                             "sender_id": agent_id if agent_id else "system",
                                             "sender_name": f"{server_name}",
                                             "url": f"MCP: {_name}",
                                             "label": f"Screenshot from {_name}",
                                             "image_base64": f"data:{mime};base64,{b64}",
                                        }))
                                    text_results.append("[Image Data Omitted - Sent to UI Viewer]")
                                elif hasattr(block, "text"):
                                    text_results.append(block.text)
                                elif isinstance(block, dict) and "text" in block:
                                    text_results.append(block["text"])
                                else:
                                    text_results.append(str(block))
                            return "\n".join(text_results)
                        return str(result)
                    except Exception as e:
                        return f"Error executing MCP tool {_name}: {str(e)}"
            
                # Extract parameters from JSON schema
                parameters = {}
                input_schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
                if input_schema:
                    if isinstance(input_schema, dict):
                        properties = input_schema.get("properties", {})
                        for k, v in properties.items():
                            parameters[k] = {**v, "_required": k in input_schema.get("required", [])}
            
                # Register in ToolRegistry — skip if already registered (dedup guard for global MCPs
                # that may be reconnected from DB AND also auto-booted via create_task).
                import hashlib
                import re
                base_name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server_name}_{tool_name}")
                scope_suffix = hashlib.sha256(repr((key, tool_name)).encode()).hexdigest()[:12]
                registered_name = f"mcp_{base_name[:43]}_{scope_suffix}"
                spec = ToolSpec(
                    name=registered_name,
                    description=tool.description or f"MCP tool {tool_name} from {server_name}",
                    category="mcp",
                    parameters=parameters,
                    permission_default="judge",
                    handler=tool_handler,
                    team_id=team_id,
                    agent_id=agent_id,
                    input_schema=input_schema if isinstance(input_schema, dict) else None,
                )
                if ToolRegistry.get(spec.name):
                    print(f"  [WARN] Skipping duplicate MCP tool: {spec.name} (already registered)")
                    continue
                ToolRegistry.register(spec)
                registered_tools.append(spec.name)
                self.statuses[key]["tools"] = list(registered_tools)
                print(f"  [OK] Registered MCP tool: {spec.name}")

            self.statuses[key]["status"] = "connected"
            self.statuses[key]["tools"] = registered_tools

        except Exception as e:
            err_msg = str(e).strip()
            if not err_msg:
                if isinstance(e, asyncio.TimeoutError):
                    err_msg = f"Connection timed out (initialization exceeded {int(init_timeout)}s limit)"
                else:
                    err_msg = f"{type(e).__name__} during startup"
            self.statuses[key]["status"] = "error"
            self.statuses[key]["error"] = err_msg
            print(f"  [ERROR] Failed to start MCP server {server_name}: {err_msg}")
            
            failed_stack = self.exit_stacks.pop(key, None)
            if failed_stack:
                await self._close_stack(failed_stack, server_name)
            raise

mcp_manager = MCPManager()
