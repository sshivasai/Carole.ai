"""
# backend/core/agent/react_agent.py

This file defines the core ReACT (Reasoning and Acting) loop for standard Worker and Coordinator agents.

Responsibilities:
1. Execute the Thought-Action-Observation loop.
2. ENFORCE CONFIDENCE-BASED RESEARCH: 
    - Step 1: Think and assess confidence based on internal knowledge and 'Lessons Learned' memory.
    - Step 2: If confidence is low or the task requires modern/external documentation, MUST use `WebSearchTool` or `BrowserTool` to gather real-time data first.
    - Step 3: Re-evaluate and reason with citations from the web data.
    - Step 4: Execute actions (write code, run commands).
3. Maintain local Working Memory (JSONB scratchpad).
4. Query the MultiModelRouter for LLM completions.
5. Invoke the ToolExecutor to run tools (Code, Shell, Playwright, Git).
6. Pause execution and emit an EventBus message when a tool requires Judge or Human permission.
7. Parse the `<task-notification>` protocol when acting as a Coordinator reading Worker outputs.
"""

class ReACTAgent:
    def __init__(self, agent_config, event_bus):
        self.config = agent_config
        self.event_bus = event_bus
        
    async def run_loop(self, initial_prompt: str):
        # 1. Fetch System Prompt (Includes constraints to check confidence and search web first)
        # 2. Start While Loop (Until task is marked Complete):
        #      a. Generate LLM Completion (Thought -> Action)
        #      b. If Thought indicates low confidence -> force tool: WebSearch
        #      c. Execute Tool via ToolExecutor
        #      d. Append Observation to local memory
        #      e. Check if goal is met
        pass
