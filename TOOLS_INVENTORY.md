# 🛠️ Battlefield Tool Inventory

**Total: 49 Tools across 8 Categories**

A comprehensive toolkit inspired by Claude Code's capabilities, designed for AI agents to interact with codebases, users, and external systems.

---

## 📁 FILESYSTEM (9 tools)

### Core File Operations
- `read_file(path)` - Read file contents
- `write_file(path, content)` ⚠️ - Create/overwrite files
- `append_file(path, content)` - Append to files
- `delete_file(path)` ⚠️ - Delete files
- `copy_file(source, destination)` - Copy files
- `move_file(source, destination)` ⚠️ - Move/rename files

### Directory Operations
- `list_files(path, recursive)` - List directory contents
- `create_directory(path)` - Create directories
- `search_files(pattern, path)` - Find files by name pattern (glob)

---

## 🖥️ SHELL (4 tools)

- `run_command(command, timeout)` ⚠️ - Execute bash commands
- `run_command_async(command, working_dir)` ⚠️ - Long-running commands
- `get_environment(var_name)` - Read environment variables
- `check_command_exists(command)` - Verify command availability

---

## 🌐 WEB (6 tools)

### HTTP & Scraping
- `web_search(query, num_results)` - DuckDuckGo search
- `fetch_url(url, method, headers)` - HTTP requests
- `scrape_page(url, selector)` - HTML parsing with BeautifulSoup
- `download_file(url, output_path)` - File downloads

### Browser Automation (Playwright)
- `browser_screenshot(url, output_path, full_page)` ⚠️ - Take screenshots
- `browser_execute(url, script)` ⚠️ - Run JavaScript in browser

---

## 🔍 SEARCH (5 tools)

### Advanced File Discovery
- `glob_search(pattern, path)` - Glob pattern matching (`**/*.py`)
- `grep_search(pattern, path, file_pattern, case_sensitive, context_lines)` - Content search with regex
- `smart_search(file_pattern, content_pattern, path)` - Combined file + content search
- `find_function(name, path)` - Find function/class definitions

**Like Claude's Glob + Grep tools combined**

---

## 🔬 CODE_ANALYSIS (6 tools)

### Quality & Structure
- `check_syntax(path)` - Python syntax validation
- `lint_code(path, linter)` - Run linters (pylint, flake8, eslint)
- `analyze_imports(path)` - List all imports/dependencies
- `count_lines(path)` - LOC metrics (code, comments, blank)
- `find_todos(path)` - Find TODO/FIXME/HACK comments
- `analyze_complexity(path)` - Complexity analysis (functions, classes)

**Similar to Claude's code understanding capabilities**

---

## 🔀 GIT (10 tools)

### Repository Operations
- `git_status()` - Show repo status
- `git_diff(file, staged)` - Show changes
- `git_log(count, oneline)` - Commit history
- `git_add(files)` ⚠️ - Stage files
- `git_commit(message)` ⚠️ - Create commits
- `git_push(remote, branch)` ⚠️ - Push to remote

### Branch Management
- `git_branch(action, branch_name)` - List/create/switch branches
- `git_clone(url, directory)` ⚠️ - Clone repositories
- `git_stash(action, message)` - Stash changes

**Matches Claude's git workflow tools**

---

## 💬 INTERACTION (5 tools)

### User Communication
- `ask_user(question, options)` - Ask questions, wait for response
- `request_confirmation(action, details)` - Request approval
- `show_progress(message, percentage)` - Progress updates
- `notify_user(message, level)` - Send notifications (info/success/warning/error)
- `show_options_menu(title, options)` - Display selection menus

**Like Claude's AskUserQuestion tool**

---

## 📋 TASK_MANAGEMENT (4 tools)

### Project Organization
- `add_task(title, description, priority)` - Create tasks
- `list_tasks(status)` - View tasks (filter by todo/in_progress/done)
- `update_task(task_id, status, priority)` - Update task status
- `clear_completed_tasks()` ⚠️ - Remove done tasks

### Planning
- `write_plan(content)` - Write project plan (markdown)
- `read_plan()` - Read current plan

**Similar to Claude's TodoWrite and planning features**

---

## 🔐 Safety Features

### Confirmation Required (⚠️)
The following tools require user approval before execution:

**Filesystem**
- write_file, delete_file, move_file

**Shell**
- run_command, run_command_async

**Git**
- git_add, git_commit, git_push, git_clone

**Web**
- browser_screenshot, browser_execute

**Tasks**
- clear_completed_tasks

---

## 🎯 Claude Code Feature Parity

| Claude Code Feature | Battlefield Equivalent | Status |
|---------------------|------------------------|--------|
| Read/Edit/Write | read_file, write_file | ✅ |
| Glob | glob_search | ✅ |
| Grep | grep_search | ✅ |
| Bash | run_command | ✅ |
| Git operations | git_* tools | ✅ |
| WebFetch | fetch_url, scrape_page | ✅ |
| AskUserQuestion | ask_user | ✅ |
| TodoWrite | add_task, list_tasks | ✅ |
| Code analysis | code_analysis tools | ✅ |

---

## 🚀 Usage Example

```python
from core.tools import ToolRegistry
from core.tools import all_tools

# Get all tools
tools = ToolRegistry.list_all()

# Execute a tool
tool = ToolRegistry.get("grep_search")
result = await tool.execute(
    pattern="TODO",
    path=".",
    file_pattern="*.py"
)

# Generate LLM prompt
prompt = ToolRegistry.to_llm_prompt()
```

---

## 📦 Dependencies

```bash
pip install -r requirements.txt

# For browser tools
playwright install
```

---

## 🔧 Extending the Toolkit

Add new tools easily:

```python
from core.tools import battlefield_tool

@battlefield_tool(
    name="my_tool",
    description="What it does",
    category="my_category",
    requires_confirmation=False,
    parameters={
        "arg": {
            "type": "string",
            "required": True,
            "description": "Argument description"
        }
    }
)
def my_tool(arg: str) -> str:
    return f"Result: {arg}"
```

The decorator automatically registers the tool with the global registry.

---

## 🎮 Next Steps

Now that we have a comprehensive toolkit, we can build:

1. **Agent Loop** - LLM that can parse tool calls and execute them
2. **WebSocket Broadcaster** - Stream agent actions in real-time
3. **3D Visualizer** - React Three Fiber battlefield view
4. **Confirmation UI** - Approve/deny destructive operations

The foundation is solid! 🚀
