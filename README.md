# 🎮 Battlefield: Spatial Multi-Agent Platform

An open-source platform for building and visualizing AI agents working together in a 3D environment.

## 🚀 Phase 1: Tool System

### Architecture

The tool system is built on a **decorator-based registry pattern** that makes it trivial to add new capabilities:

```python
@battlefield_tool(
    name="my_tool",
    description="What it does",
    category="my_category",
    parameters={"arg": {"type": "string", "required": True}}
)
def my_tool(arg: str) -> str:
    return f"Result: {arg}"
```

### Available Tools (49 Total)

#### Filesystem (9 tools)
File operations, directory management, pattern matching

#### Shell (4 tools)
Command execution, environment variables

#### Web (6 tools)
Search, HTTP, scraping, browser automation

#### Search (4 tools)
Glob patterns, grep content search, function finder

#### Code Analysis (6 tools)
Syntax checking, linting, imports, complexity, TODOs

#### Git (9 tools)
Status, diff, commit, push, branches, stash

#### Interaction (5 tools)
User questions, confirmations, notifications, progress

#### Task Management (6 tools)
Tasks, plans, project organization

**See [TOOLS_INVENTORY.md](TOOLS_INVENTORY.md) for complete documentation**

⚠️ = Requires user confirmation (15 tools)

## 🛠️ Installation

```bash
# Install dependencies
pip install -r requirements.txt

# For browser tools (optional)
playwright install
```

## 🧪 Testing

```bash
python test_tools.py
```

This will:
1. Display all registered tools
2. Generate LLM-friendly prompt
3. Test filesystem operations

## 📁 Project Structure

```
Carole.ai/
├── core/
│   └── tools/
│       ├── __init__.py        # Registry & decorator
│       ├── filesystem.py      # File operations
│       ├── shell.py           # Command execution
│       ├── web.py             # Web & browser tools
│       └── all_tools.py       # Import all tools
├── requirements.txt
├── test_tools.py
└── README.md
```

## 🔧 Usage in Agent Loop

```python
from core.tools import ToolRegistry, all_tools

# Get all tools for LLM prompt
prompt = ToolRegistry.to_llm_prompt()

# Execute a tool
tool = ToolRegistry.get("read_file")
result = await tool.execute(path="example.txt")

# Check if confirmation needed
if tool.requires_confirmation:
    # Ask user for approval
    pass
```

## 🎯 Next Steps

- [ ] Build the Agent loop (LLM + tool parser)
- [ ] Add WebSocket event broadcaster
- [ ] Create 3D visualizer (React Three Fiber)
- [ ] Implement confirmation UI for destructive tools

## 📜 License

MIT - Build awesome things!
