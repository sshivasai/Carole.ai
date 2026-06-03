import asyncio
from contextlib import AsyncExitStack
from typing import Dict, Any, List

from backend.core.tools.tool_registry import ToolRegistry, ToolSpec

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
        return cls._instance
    
    async def connect_stdio_server(self, server_name: str, command: str, args: list[str], team_id: str = None, agent_id: str = None):
        """
        Connects to an MCP server via stdio, extracts its tools, 
        and registers them in the Carole ToolRegistry.
        """
        server_parameters = StdioServerParameters(command=command, args=args)
        
        # Connect to stdio server
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_parameters))
        read_stream, write_stream = stdio_transport[0], stdio_transport[1]
        
        # Initialize session
        session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        
        self.sessions[server_name] = session
        
        # List tools and register
        tools_response = await session.list_tools()
        
        for tool in tools_response.tools:
            tool_name = tool.name
            
            # create a closure for the handler to capture tool_name and session properly
            async def tool_handler(args_dict: dict, team_id: str = None, _session=session, _name=tool_name) -> str:
                try:
                    result = await _session.call_tool(_name, arguments=args_dict)
                    if hasattr(result, "content") and result.content:
                        # Extract text from content blocks
                        text_results = []
                        for block in result.content:
                            if hasattr(block, "text"):
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
            
            # Register in ToolRegistry
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
            ToolRegistry.register(spec)
            print(f"  ✓ Registered MCP tool: {spec.name}")

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
