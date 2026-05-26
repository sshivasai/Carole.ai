"""
# backend/core/agent/react_agent.py

This file defines the core ReACT (Reasoning and Acting) loop for standard Worker and Coordinator agents.

Responsibilities:
1. Execute the Thought-Action-Observation loop.
2. Maintain local Working Memory (JSONB scratchpad).
3. Query the MultiModelRouter for LLM completions.
4. Invoke the ToolExecutor to run tools (Code, Shell, Playwright, Git).
5. Pause execution and emit an EventBus message when a tool requires Judge or Human permission.
6. Parse the `<task-notification>` protocol when acting as a Coordinator reading Worker outputs.
"""

class ReACTAgent:
    def __init__(self, agent_config, event_bus):
        self.config = agent_config
        self.event_bus = event_bus
        
    async def run_loop(self, initial_prompt: str):
        # TODO: Implement the Thought-Action-Observation loop
        pass
