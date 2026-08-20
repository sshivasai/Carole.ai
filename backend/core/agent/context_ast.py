"""
core/agent/context_ast.py

Lightweight AST parser for agent conversation history.

Parses the list of LLM messages into structured Node objects, enabling
precise, token-safe pruning of failed tool-call "dead ends" without
accidentally stripping valid thought content when text formatting deviates
slightly from the expected pattern.

Node types
----------
TextNode     — Free-form assistant reasoning text
ActionNode   — A [ACTION]...[/ACTION] call block within an assistant message
ObsNode      — A [OBSERVATION]...[/OBSERVATION] user message
PlainNode    — Any message that does not match the above patterns
              (user messages, system messages, etc.)

Dead-end detection
------------------
A dead-end pair is: an assistant message that produced NO valid ActionNode,
immediately followed by a user ObsNode that contains only an error observation.
Pruning these pairs removes corrected mistakes from context without touching
any message that has genuine reasoning or a successful action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any

# ─── Regex constants ─────────────────────────────────────────────────

_ACTION_RE = re.compile(
    r"\[ACTION\]([\s\S]*?)\[/ACTION\]",
    re.IGNORECASE,
)

_OBS_RE = re.compile(
    r"\[OBSERVATION\]([\s\S]*?)(?:\[/OBSERVATION\]|$)",
    re.IGNORECASE,
)

# Known error observation patterns (kept in sync with react_agent.py)
_ERROR_PATTERNS: Tuple[str, ...] = (
    "Error — Missing Tool Call Tag",
    "Error — No [ACTION] tag found",
    "Error: Tool",
    "✗ Tool",
    "Unknown tool:",
    "Invalid JSON",
    "Traceback (most recent call last)",
)


# ─── Node dataclasses ────────────────────────────────────────────────

@dataclass
class ActionNode:
    raw_block: str  # full [ACTION]...[/ACTION] text
    tool_name: str
    args_raw: str


@dataclass
class AssistantNode:
    """Represents a parsed assistant turn."""
    original: Dict[str, Any]  # the original message dict
    actions: List[ActionNode] = field(default_factory=list)
    text_only: str = ""       # text with [ACTION]...[/ACTION] stripped

    @property
    def has_valid_action(self) -> bool:
        return len(self.actions) > 0


@dataclass
class UserObsNode:
    """Represents a parsed user/observation turn."""
    original: Dict[str, Any]
    observations: List[str] = field(default_factory=list)   # contents of [OBSERVATION] blocks
    is_error_only: bool = False  # True if ALL obs are error observations


@dataclass
class PlainNode:
    """Any other message (system, plain user chat, etc.)."""
    original: Dict[str, Any]


ConvNode = AssistantNode | UserObsNode | PlainNode


# ─── Parser ─────────────────────────────────────────────────────────

def _parse_action_node(block: str) -> ActionNode:
    """Parse the interior of a [ACTION]...[/ACTION] block into an ActionNode."""
    stripped = block.strip()
    # Extract tool_name(args)
    m = re.match(r"(\w[\w.]*)\s*\(([\s\S]*)\)?\s*$", stripped)
    if m:
        return ActionNode(raw_block=block, tool_name=m.group(1), args_raw=m.group(2))
    # Fallback: treat entire content as tool name with no args
    return ActionNode(raw_block=block, tool_name=stripped, args_raw="")


def _extract_text(content: Any) -> str:
    """Safely coerce message content to a plain string for regex matching.

    LLM message dicts can use two content formats:
      - str  : simple text (most common)
      - list : multipart content blocks e.g. [{"type": "text", "text": "..."}, {"type": "image", ...}]
               used when the message contains image/file attachments.

    Returns a joined string of all text parts, or "" if content is None/empty.
    """
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                # Anthropic-style: {"type": "text", "text": "..."}
                if block.get("type") == "text":
                    parts.append(block.get("text") or "")
                # OpenAI-style: {"role": ..., "content": "..."}
                elif "content" in block and isinstance(block["content"], str):
                    parts.append(block["content"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    # Fallback: stringify whatever we got
    return str(content)


def parse_messages(messages: List[Dict[str, Any]]) -> List[ConvNode]:
    """Convert a flat list of LLM message dicts into a typed AST."""
    nodes: List[ConvNode] = []

    for msg in messages:
        role = msg.get("role", "")
        raw_content = msg.get("content")
        # Always work with a plain string for regex parsing.
        # Multipart content (list of blocks with images, etc.) is
        # flattened to its text parts so regexes don't crash.
        content = _extract_text(raw_content)

        if role == "assistant":
            # Extract all [ACTION] blocks
            action_nodes = [_parse_action_node(m.group(1)) for m in _ACTION_RE.finditer(content)]
            text_only = _ACTION_RE.sub("", content).strip()
            nodes.append(AssistantNode(original=msg, actions=action_nodes, text_only=text_only))

        elif role == "user":
            obs_matches = _OBS_RE.findall(content)
            if obs_matches:
                is_error = all(
                    any(pat in obs for pat in _ERROR_PATTERNS)
                    for obs in obs_matches
                )
                nodes.append(UserObsNode(original=msg, observations=obs_matches, is_error_only=is_error))
            else:
                nodes.append(PlainNode(original=msg))

        else:
            nodes.append(PlainNode(original=msg))

    return nodes



# ─── Pruner ─────────────────────────────────────────────────────────

def snip_dead_ends(nodes: List[ConvNode]) -> Tuple[List[ConvNode], int]:
    """
    Remove dead-end (assistant, error-obs) pairs from the AST.

    A pair is a dead-end if:
    1. The assistant node produced NO valid action
    2. The immediately following user node contains ONLY error observations

    Returns (pruned_nodes, snipped_count).
    """
    keep = [True] * len(nodes)
    snipped = 0
    i = 0
    while i < len(nodes) - 1:
        curr = nodes[i]
        nxt = nodes[i + 1]

        if (
            isinstance(curr, AssistantNode)
            and not curr.has_valid_action
            and isinstance(nxt, UserObsNode)
            and nxt.is_error_only
        ):
            keep[i] = False
            keep[i + 1] = False
            snipped += 1
            i += 2
            continue
        i += 1

    pruned = [n for n, k in zip(nodes, keep) if k]
    return pruned, snipped


# ─── Serializer ──────────────────────────────────────────────────────

def serialize_messages(nodes: List[ConvNode]) -> List[Dict[str, Any]]:
    """Convert AST nodes back to the original message dict list."""
    return [n.original for n in nodes]


# ─── Convenience wrapper ─────────────────────────────────────────────

def ast_snip_dead_ends(messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Parse → prune dead ends → serialize back to messages.
    Returns (pruned_messages, number_of_snipped_pairs).
    """
    if len(messages) < 2:
        return messages, 0

    nodes = parse_messages(messages)
    pruned_nodes, snipped = snip_dead_ends(nodes)
    return serialize_messages(pruned_nodes), snipped
