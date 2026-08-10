from contextlib import AsyncExitStack

from core.tools.tool_registry import ToolRegistry, ToolSpec

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    pass

class MCPManager:
    """
    Singleton class that manages active MCP server connections.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MCPManager, cls).__new__(cls)
            cls._instance.exit_stack = AsyncExitStack()
            cls._instance.sessions = {}
            cls._instance.statuses = {}
        return cls._instance
    
    async def shutdown(self):
        """Safely close all MCP server connections and resources."""
        if self.exit_stack:
            await self.exit_stack.aclose()
            self.sessions.clear()
            
    async def connect_stdio_server(self, server_name: str, command: str, args: list[str], team_id: str = None, agent_id: str = None, env_vars: dict = None):
        """
        Connects to an MCP server via stdio, extracts its tools, 
        and registers them in the Carole ToolRegistry.
        """
        import os
        import shutil
        
        resolved_command = shutil.which(command) or command
        
        # Key matches the format expected by delete_mcp_server
        key = (str(team_id) if team_id else "None", str(agent_id) if agent_id else "global", server_name)
        
        self.statuses[key] = {
            "server_name": server_name,
            "team_id": team_id,
            "agent_id": agent_id,
            "status": "loading",
            "tools": []
        }
        
        try:
            merged_env = os.environ.copy()
            if env_vars:
                merged_env.update(env_vars)
            server_parameters = StdioServerParameters(command=resolved_command, args=args, env=merged_env)
        
            # Connect to stdio server
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_parameters))
            read_stream, write_stream = stdio_transport[0], stdio_transport[1]
        
            # Initialize session
            session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
        
            self.sessions[key] = session
        
            # List tools and register
            tools_response = await session.list_tools()
        
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
                    
                        result = await _session.call_tool(_name, arguments=args_to_send)
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
                                        import asyncio
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
                if hasattr(tool, "inputSchema") and tool.inputSchema:
                    if isinstance(tool.inputSchema, dict):
                        properties = tool.inputSchema.get("properties", {})
                        for k, v in properties.items():
                            parameters[k] = v
            
                # Register in ToolRegistry — skip if already registered (dedup guard for global MCPs
                # that may be reconnected from DB AND also auto-booted via create_task).
                spec = ToolSpec(
                    name=f"{server_name}_{tool_name}",
                    description=tool.description or f"MCP tool {tool_name} from {server_name}",
                    category="mcp",
                    parameters=parameters,
                    permission_default="judge",
                    handler=tool_handler,
                    team_id=team_id,
                    agent_id=agent_id
                )
                if ToolRegistry.get(spec.name):
                    print(f"  [WARN] Skipping duplicate MCP tool: {spec.name} (already registered)")
                    continue
                ToolRegistry.register(spec)
                registered_tools.append(spec.name)
                print(f"  [OK] Registered MCP tool: {spec.name}")

            self.statuses[key]["status"] = "connected"
            self.statuses[key]["tools"] = registered_tools

        except Exception as e:
            self.statuses[key]["status"] = "error"
            self.statuses[key]["error"] = str(e)
            print(f"  [ERROR] Failed to start MCP server {server_name}: {e}")
            raise

mcp_manager = MCPManager()

# --- Example Usage ---
# To mount a server, you can call connect_stdio_server during application startup (e.g., in main.py).
#
# async def setup_mcp():
#     await mcp_manager.connect_stdio_server(
#         server_name="github",
#         command="npx",
#         args=["-y", "@modelcontextprotocol/server-github"]
#     )
