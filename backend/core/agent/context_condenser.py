"""
# backend/core/agent/context_condenser.py

Intelligent Context Condenser.
Monitors token budget, generates structured Working State Checkpoints,
sanitizes orphan tags, and performs surgical sliding window pruning.
"""

import re
import json
import logging
from typing import List, Dict, Any, Tuple, Optional

logger = logging.getLogger("carole.condenser")

# Default token pressure trigger: 75% of context window capacity
DEFAULT_TOKEN_TRIGGER_RATIO = 0.75

WORKING_STATE_SYSTEM_PROMPT = """You are a compiler-grade context distillation assistant.
Your task is to summarize the preceding conversation history into a dense, high-fidelity WORKING STATE CHECKPOINT.

CRITICAL FORMATTING REQUIREMENT:
You MUST format your output strictly under these 4 Markdown section headers:

## 1. Active Goal & User Constraints
- Exact goal the user requested
- Technical constraints, forbidden paths, and preferences

## 2. Architectural & Implementation Decisions Made
- Key technical decisions, patterns selected, and schema choices
- Confirmed findings and root causes identified

## 3. List of Modified & Created Files
- Exact relative paths of files created or modified
- Key functions, classes, or exports added or altered in each file

## 4. Blockers & Next Immediate Steps
- Current state of progress (what is completed vs what remains)
- Exact next step to execute immediately upon resuming

Keep the distillation factual, compact, and dense. Do NOT output conversational greetings.
"""

WORKING_STATE_USER_PROMPT = """Analyze the conversation history below and generate the 4-section WORKING STATE CHECKPOINT:

{conversation_text}
"""


class ContextCondenser:
    """
    Manages in-loop token monitoring, structured distillation, and sliding window pruning.
    """

    @staticmethod
    def is_under_context_pressure(
        estimated_tokens: int,
        context_window: int,
        trigger_ratio: float = DEFAULT_TOKEN_TRIGGER_RATIO
    ) -> bool:
        """Determines if token count has reached the condensation trigger threshold."""
        if context_window <= 0:
            return False
        return (estimated_tokens / context_window) >= trigger_ratio

    @staticmethod
    def sanitize_orphan_tags(content: str) -> str:
        """
        Sanitizes unclosed, dangling, or corrupted tool tags in message content
        to avoid OpenAI/Anthropic API 400 validation errors.
        """
        if not content or not isinstance(content, str):
            return content

        sanitized = content

        # 1. Close unclosed [ACTION] tags if an opening tag has no matching closing tag
        action_opens = len(re.findall(r"\[ACTION\]", sanitized, re.IGNORECASE))
        action_closes = len(re.findall(r"\[/ACTION\]", sanitized, re.IGNORECASE))
        if action_opens > action_closes:
            diff = action_opens - action_closes
            sanitized += ("[/ACTION]" * diff)

        # 2. Close unclosed [OBSERVATION] tags
        obs_opens = len(re.findall(r"\[OBSERVATION\]", sanitized, re.IGNORECASE))
        obs_closes = len(re.findall(r"\[/OBSERVATION\]", sanitized, re.IGNORECASE))
        if obs_opens > obs_closes:
            diff = obs_opens - obs_closes
            sanitized += ("[/OBSERVATION]" * diff)

        # 3. Clean orphan closing tags without opens
        if action_closes > action_opens:
            sanitized = re.sub(r"\[/ACTION\]", "", sanitized, count=(action_closes - action_opens), flags=re.IGNORECASE)
        if obs_closes > obs_opens:
            sanitized = re.sub(r"\[/OBSERVATION\]", "", sanitized, count=(obs_closes - obs_opens), flags=re.IGNORECASE)

        return sanitized

    @classmethod
    def sanitize_messages(cls, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Applies orphan tag sanitization across all message dicts."""
        cleaned = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                cleaned_msg = dict(msg)
                cleaned_msg["content"] = cls.sanitize_orphan_tags(content)
                cleaned.append(cleaned_msg)
            elif isinstance(content, list):
                # Multipart content
                cleaned_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        cp = dict(part)
                        cp["text"] = cls.sanitize_orphan_tags(part.get("text", ""))
                        cleaned_parts.append(cp)
                    else:
                        cleaned_parts.append(part)
                cleaned_msg = dict(msg)
                cleaned_msg["content"] = cleaned_parts
                cleaned.append(cleaned_msg)
            else:
                cleaned.append(msg)
        return cleaned

    @staticmethod
    def extract_pinned_identifiers(messages: List[Dict[str, Any]]) -> str:
        """
        Scans messages about to be condensed and extracts file paths, URLs,
        and high-density code references to pin at the head of the condensed checkpoint.
        """
        extracted_paths = set()
        for msg in messages:
            content_str = str(msg.get("content", ""))
            # Extract paths from tool calls
            for m in re.finditer(r'[\'"]?(?:relative_path|path|filename|file_path)[\'"]?\s*[:=]\s*[\'"]([^\'"]+)[\'"]', content_str):
                extracted_paths.add(m.group(1))
            # Extract paths from markdown links
            for m in re.finditer(r'\[.*?\]\((?:file:)?([^\)]+)\)', content_str):
                extracted_paths.add(m.group(1))
            # Extract paths from code headers
            for m in re.finditer(r'^\s*#\s+(?:backend|frontend|packages|src)/[a-zA-Z0-9_./-]+', content_str, re.MULTILINE):
                extracted_paths.add(m.group(0).strip('# \t'))
            # Extract plain paths with source extensions in text (e.g. backend/core/agent/react_agent.py)
            for m in re.finditer(r'(?:[a-zA-Z0-9_\-]+[/\\])+[a-zA-Z0-9_\-]+\.(?:py|ts|tsx|js|jsx|json|yaml|yml|md|html|css|rs|go)\b', content_str):
                extracted_paths.add(m.group(0).replace("\\", "/"))

        # Filter noise (common short tokens)
        valid_paths = [
            p for p in sorted(extracted_paths)
            if ("/" in p or "\\" in p or "." in p) and len(p) > 3 and not p.startswith("http")
        ]

        if not valid_paths:
            return ""

        block = "[PINNED CONTEXT: ACTIVE WORKSPACE IDENTIFIERS]\n"
        for p in valid_paths:
            block += f"- {p}\n"
        block += "[/PINNED CONTEXT]\n\n"
        return block

    @staticmethod
    def generate_folded_signatures(file_paths: List[str], workspace_root: Optional[str] = None) -> str:
        """
        Generates folded AST signature summaries (classes, methods, functions, interfaces)
        for files touched during the session without including function bodies.
        Saves ~95% tokens compared to injecting full file contents.
        """
        if not file_paths:
            return ""

        from core.knowledge.ast_parser import parse_file_ast
        import os

        folded_lines = ["[PINNED CONTEXT: FOLDED FILE SIGNATURES]"]

        for rel_path in file_paths[:6]:  # Limit to top 6 files to prevent bloat
            full_path = rel_path
            if workspace_root and not os.path.isabs(rel_path):
                full_path = os.path.join(workspace_root, rel_path)

            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(40000)

                chunks, _ = parse_file_ast(content, rel_path)
                if not chunks:
                    continue

                folded_lines.append(f"File: {rel_path}")
                for chunk in chunks[:15]:
                    params_str = ", ".join(chunk.params) if chunk.params else ""
                    parent = f"{chunk.parent_symbol}." if chunk.parent_symbol else ""
                    folded_lines.append(f"  - {chunk.kind} {parent}{chunk.name}({params_str}) [L{chunk.start_line}-L{chunk.end_line}]")
            except Exception:
                continue

        folded_lines.append("[/PINNED CONTEXT: FOLDED FILE SIGNATURES]\n\n")
        if len(folded_lines) <= 2:
            return ""
        return "\n".join(folded_lines)

    @classmethod
    def apply_sliding_window_pruning(
        cls,
        messages: List[Dict[str, Any]],
        checkpoint_card: str,
        keep_recent_turns: int = 4
    ) -> List[Dict[str, Any]]:
        """
        Performs non-destructive sliding window pruning:
        - Keeps messages[0] (root user request/prompt)
        - Injects structured WORKING STATE CHECKPOINT as a user turn
        - Keeps the latest N messages (recent turns)
        """
        if len(messages) <= keep_recent_turns + 1:
            return messages

        first_msg = messages[0]
        # Align boundary so we don't start on an orphaned tool or observation message
        start_idx = max(1, len(messages) - keep_recent_turns)
        while start_idx < len(messages) - 1 and (
            messages[start_idx].get("role") == "tool" or
            "[OBSERVATION]" in str(messages[start_idx].get("content", ""))[:40]
        ):
            start_idx += 1

        recent_messages = messages[start_idx:]

        checkpoint_msg = {
            "role": "user",
            "content": f"[WORKING STATE CHECKPOINT]\n{checkpoint_card.strip()}\n[/WORKING STATE CHECKPOINT]"
        }

        pruned = [first_msg, checkpoint_msg] + recent_messages
        return cls.sanitize_messages(pruned)
