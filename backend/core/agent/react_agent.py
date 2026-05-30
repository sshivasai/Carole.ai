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

import json
from typing import List, Dict, Any
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm.multi_model_router import llm_router
from core.chat.event_bus import event_bus
from core.memory.models import Learning, Message, Agent

class ReACTAgent:
    def __init__(self, agent_id: str, team_id: str, project_id: str, name: str, role: str, model: str, system_prompt: str):
        self.agent_id = agent_id
        self.team_id = team_id
        self.project_id = project_id
        self.name = name
        self.role = role
        self.model = model
        self.system_prompt = system_prompt
        self.topic = f"team:{self.team_id}"

    async def assemble_system_prompt(self, db_session: AsyncSession, current_task: str) -> str:
        """
        Assembles a highly customized system prompt for this ReACT invocation:
        1. Base System Prompt
        2. Relevant vector-recalled past learnings (pgvector cosine similarity)
        3. Real-time web-citation guidelines
        """
        # 1. Fetch top 3 semantically relevant "Lessons Learned" from pgvector
        query_vector = await llm_router.generate_embeddings(current_task)
        
        stmt = (
            select(Learning)
            .where(Learning.project_id == self.project_id)
            .where(or_(Learning.team_id == None, Learning.team_id == self.team_id))
            .order_by(Learning.embedding.cosine_distance(query_vector))
            .limit(3)
        )
        res = await db_session.execute(stmt)
        past_learnings = res.scalars().all()

        # 2. Format past learnings into XML tags
        learnings_block = ""
        if past_learnings:
            learnings_block = "\n<lessons-learned>\n"
            for learning in past_learnings:
                learnings_block += f"- Task context: {learning.task_summary}\n  Lesson: {learning.lesson_rule}\n"
            learnings_block += "</lessons-learned>\n"

        # 3. Inject strict confidence and research guidelines
        research_directives = (
            "\n<strict-reasoning-guidelines>\n"
            "1. CONFIDENCE ASSESSMENT: Analyze your confidence level in fulfilling the user request. "
            "If your internal data is old, vague, or missing key parameters, you MUST immediately call `WebSearch` or `BrowserTool` first.\n"
            "2. WEB CITATIONS: When gathering information from the web, ALWAYS output the source citations (URLs) in your final response.\n"
            "3. THOUGHT AND ACTION FORMAT: Wrap all thoughts in [THOUGHT]...[/THOUGHT] tags, and wrap tool execution calls in [ACTION]tool_name(args)[/ACTION] tags.\n"
            "</strict-reasoning-guidelines>\n"
        )

        return f"{self.system_prompt}\n{learnings_block}\n{research_directives}"

    async def run_loop(self, db_session: AsyncSession, initial_prompt: str):
        """
        Runs the core ReACT Thought-Action-Observation loop.
        Steams thoughts to the EventBus character-by-character for beautiful premium UI rendering.
        """
        # Fetch the agent's latest configurations (including tool permissions) from the database
        stmt = select(Agent).where(Agent.id == self.agent_id)
        res = await db_session.execute(stmt)
        db_agent = res.scalar_one_or_none()
        permissions = db_agent.tool_permissions if db_agent else {}

        # Fetch the fully formulated system prompt
        system_prompt = await self.assemble_system_prompt(db_session, initial_prompt)
        
        # Initialize conversation messages context for LLM
        messages = [{"role": "user", "content": initial_prompt}]
        
        loop_count = 0
        max_loops = 10  # Prevent infinite loops in runaway agents
        
        while loop_count < max_loops:
            loop_count += 1
            
            # Emit a "Typing" event over the EventBus
            await event_bus.publish(self.topic, {
                "type": "typing",
                "sender_id": self.agent_id,
                "sender_name": self.name,
                "role": self.role,
                "status": "thinking"
            })
            
            # Stream the completion from the llm_router
            print(f"🤖 [Agent: {self.name}] Thinking...")
            thought_buffer = ""
            
            async for chunk in llm_router.generate_stream(
                model=self.model,
                system_prompt=system_prompt,
                messages=messages,
                temperature=0.4
            ):
                thought_buffer += chunk
                
                # Stream the raw thought delta to the WebSocket EventBus in real-time
                await event_bus.publish(self.topic, {
                    "type": "thought_delta",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "delta": chunk
                })

            # Append the completed model thought to the context
            messages.append({"role": "assistant", "content": thought_buffer})
            
            # Check if the thought has completed the task or is calling a tool
            # For simplicity, we parse [ACTION]tool_name(args)[/ACTION]
            action_call = self._parse_action(thought_buffer)
            
            if not action_call:
                # No action called. The agent finished the reasoning loop and outputted the final answer.
                print(f"✓ [Agent: {self.name}] Task finished.")
                
                # Write final message to db
                db_msg = Message(
                    team_id=self.team_id,
                    sender_id=self.agent_id,
                    text=thought_buffer
                )
                db_session.add(db_msg)
                await db_session.commit()
                
                # Broadcast final message event
                await event_bus.publish(self.topic, {
                    "type": "message",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "role": self.role,
                    "text": thought_buffer
                })
                break
                
            else:
                # Tool Action called!
                tool_name, tool_args = action_call
                print(f"🛠️ [Agent: {self.name}] Executing Tool: {tool_name} with args: {tool_args}")
                
                # Emit tool execution started event
                await event_bus.publish(self.topic, {
                    "type": "tool_start",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "arguments": tool_args
                })
                
                # --- TOOL EXECUTION LAYER ---
                try:
                    observation = await self._execute_tool(name=tool_name, args=tool_args, permissions=permissions)
                except Exception as e:
                    observation = f"✗ Tool Execution Error: {str(e)}"
                
                # Emit tool execution completion event
                await event_bus.publish(self.topic, {
                    "type": "tool_end",
                    "sender_id": self.agent_id,
                    "sender_name": self.name,
                    "tool_name": tool_name,
                    "observation": observation
                })
                
                # Feed observation back as next message in prompt context
                messages.append({
                    "role": "user",
                    "content": f"[OBSERVATION] Tool output:\n{observation}\n[/OBSERVATION]"
                })

    def _parse_action(self, text: str) -> Any:
        """Parses [ACTION]tool_name(args)[/ACTION] from the generated text."""
        import re
        # Look for [ACTION]tool_name(json_string_or_raw)[/ACTION]
        match = re.search(r"\[ACTION\](\w+)\((.*?)\)\[/ACTION\]", text, re.DOTALL)
        if match:
            tool_name = match.group(1)
            raw_args = match.group(2).strip()
            try:
                # Parse as JSON if arguments are structured
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {"value": raw_args}
            return tool_name, arguments
        return None

    async def _execute_tool(self, name: str, args: Dict[str, Any], permissions: Dict[str, str]) -> str:
        """
        Routes the tool execution request to our dedicated tool registry (ToolExecutor).
        """
        from core.tools.tool_executor import tool_executor
        return await tool_executor.execute(
            tool_name=name,
            arguments=args,
            agent_id=self.agent_id,
            agent_name=self.name,
            team_id=self.team_id,
            permissions=permissions
        )
