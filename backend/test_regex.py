import re

thought_buffer = """Alright, here's the plan: 

1. Create a task for building a simple calculator using HTML and CSS.
2. Assign it to Sage since they're our developer.

Let me create that task now. 

[ACTION]create_task({"title": "Create Simple Calculator", "description": "Build a simple calculator using HTML and CSS.", "priority": "medium", "assignee": "Sage", "blocked_by_task_id": ""})[/ACTION]
"""

text_before_action = re.sub(r'\[ACTION\][\s\S]*?\[/ACTION\]', '', thought_buffer).strip()

print("Original:")
print(thought_buffer)
print("\nStripped:")
print(text_before_action)
