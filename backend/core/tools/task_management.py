"""
Task and project management tools: todos, plans, tracking
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from . import battlefield_tool


TASK_FILE = "battlefield_tasks.json"
PLAN_FILE = "battlefield_plan.md"


def _load_tasks() -> List[Dict]:
    """Load tasks from file"""
    if not Path(TASK_FILE).exists():
        return []

    try:
        with open(TASK_FILE, 'r') as f:
            return json.load(f)
    except:
        return []


def _save_tasks(tasks: List[Dict]):
    """Save tasks to file"""
    with open(TASK_FILE, 'w') as f:
        json.dump(tasks, f, indent=2)


@battlefield_tool(
    name="add_task",
    description="Add a task to the project task list",
    category="task_management",
    parameters={
        "title": {"type": "string", "required": True, "description": "Task title"},
        "description": {"type": "string", "required": False, "description": "Task description"},
        "priority": {"type": "string", "required": False, "description": "Priority: low, medium, high"}
    }
)
def add_task(title: str, description: Optional[str] = None, priority: str = "medium") -> str:
    """Add a task"""
    try:
        tasks = _load_tasks()

        task = {
            'id': len(tasks) + 1,
            'title': title,
            'description': description,
            'priority': priority,
            'status': 'todo',
            'created_at': datetime.now().isoformat()
        }

        tasks.append(task)
        _save_tasks(tasks)

        return f"✓ Task #{task['id']} added: {title}"

    except Exception as e:
        return f"✗ Error adding task: {str(e)}"


@battlefield_tool(
    name="list_tasks",
    description="List all tasks (optionally filter by status)",
    category="task_management",
    parameters={
        "status": {"type": "string", "required": False, "description": "Filter by status: todo, in_progress, done"}
    }
)
def list_tasks(status: Optional[str] = None) -> str:
    """List tasks"""
    try:
        tasks = _load_tasks()

        if not tasks:
            return "✓ No tasks found"

        if status:
            tasks = [t for t in tasks if t['status'] == status]

        if not tasks:
            return f"✓ No tasks with status '{status}'"

        result = [f"✓ Tasks ({len(tasks)}):\n"]

        for task in tasks:
            status_icon = {
                'todo': '☐',
                'in_progress': '⏳',
                'done': '✓'
            }.get(task['status'], '?')

            priority_icon = {
                'high': '🔴',
                'medium': '🟡',
                'low': '🟢'
            }.get(task['priority'], '')

            result.append(f"{status_icon} #{task['id']} {priority_icon} {task['title']}")

            if task.get('description'):
                result.append(f"  {task['description']}")

            result.append("")

        return "\n".join(result)

    except Exception as e:
        return f"✗ Error listing tasks: {str(e)}"


@battlefield_tool(
    name="update_task",
    description="Update task status or details",
    category="task_management",
    parameters={
        "task_id": {"type": "number", "required": True, "description": "Task ID"},
        "status": {"type": "string", "required": False, "description": "New status"},
        "priority": {"type": "string", "required": False, "description": "New priority"}
    }
)
def update_task(task_id: int, status: Optional[str] = None, priority: Optional[str] = None) -> str:
    """Update task"""
    try:
        tasks = _load_tasks()

        task = next((t for t in tasks if t['id'] == task_id), None)

        if not task:
            return f"✗ Task #{task_id} not found"

        if status:
            task['status'] = status

        if priority:
            task['priority'] = priority

        task['updated_at'] = datetime.now().isoformat()

        _save_tasks(tasks)

        return f"✓ Task #{task_id} updated"

    except Exception as e:
        return f"✗ Error updating task: {str(e)}"


@battlefield_tool(
    name="write_plan",
    description="Write or update the project plan",
    category="task_management",
    parameters={
        "content": {"type": "string", "required": True, "description": "Plan content (markdown)"}
    }
)
def write_plan(content: str) -> str:
    """Write plan"""
    try:
        with open(PLAN_FILE, 'w') as f:
            f.write(content)

        return f"✓ Plan written to {PLAN_FILE}"

    except Exception as e:
        return f"✗ Error writing plan: {str(e)}"


@battlefield_tool(
    name="read_plan",
    description="Read the current project plan",
    category="task_management",
    parameters={}
)
def read_plan() -> str:
    """Read plan"""
    try:
        if not Path(PLAN_FILE).exists():
            return "✗ No plan file found"

        with open(PLAN_FILE, 'r') as f:
            content = f.read()

        return f"✓ Project Plan:\n\n{content}"

    except Exception as e:
        return f"✗ Error reading plan: {str(e)}"


@battlefield_tool(
    name="clear_completed_tasks",
    description="Remove all completed tasks from the task list",
    category="task_management",
    requires_confirmation=True,
    parameters={}
)
def clear_completed_tasks() -> str:
    """Clear completed tasks"""
    try:
        tasks = _load_tasks()

        completed = [t for t in tasks if t['status'] == 'done']
        remaining = [t for t in tasks if t['status'] != 'done']

        _save_tasks(remaining)

        return f"✓ Removed {len(completed)} completed tasks"

    except Exception as e:
        return f"✗ Error clearing tasks: {str(e)}"
