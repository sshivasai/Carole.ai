"""
# backend/core/agent/message_history.py

Strict turn-alternating, native-tool-aware message history manager.

Enforces canonical Anthropic-compatible message history invariants:
  - Canonical roles: "user" and "assistant"
  - Strict turn alternation: messages[i].role != messages[i+1].role
  - Atomic tool result batches: tool_result blocks appear in a user turn
    immediately following the assistant turn that issued the tool_use blocks.
  - In user turns containing both tool results and notes, tool_result blocks
    strictly precede text/context notes.
  - Immutable encapsulation: all getters return deep copies so callers cannot
    mutate internal state.
"""

from copy import deepcopy
import json
from typing import Any, Dict, List, Optional, Set


class MessageHistory:
    """
    A robust, validated message history manager for native tool calling.

    Guarantees:
        user → assistant (with optional tool_use) → user (with tool_results) → ...
    """

    def __init__(self, seed: Optional[List[Dict[str, Any]]] = None):
        """
        Args:
            seed: Optional pre-existing message list to adopt (e.g. loaded from DB).
        """
        self._turns: List[Dict[str, Any]] = []
        self._pending_tool_call_ids: Set[str] = set()
        self._seen_tool_call_ids: Set[str] = set()

        if seed:
            seed_copy = deepcopy(seed)
            for idx, msg in enumerate(seed_copy):
                if not isinstance(msg, dict):
                    raise ValueError(f"Seed message at index {idx} must be a dict.")
                role = msg.get("role")
                if role not in ("user", "assistant", "tool", "system"):
                    raise ValueError(f"Unsupported message role '{role}' at seed index {idx}.")

                content = msg.get("content", "")

                # Normalize OpenAI "tool" role into user tool_result
                if role == "tool":
                    tool_call_id = msg.get("tool_call_id", f"call_seed_{idx}")
                    self.add_tool_results([{
                        "tool_use_id": tool_call_id,
                        "content": str(content),
                        "is_error": bool(msg.get("is_error", False)),
                    }])
                    self._carry_metadata(msg)
                    continue

                if role == "system":
                    # Convert system messages into user context note to preserve alternation
                    self.add_context_note(str(content))
                    continue

                if role == "user":
                    # Check if this user message contains tool results
                    blocks = self._to_blocks(content)
                    has_tool_results = any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in blocks
                    )
                    if has_tool_results:
                        # Extract and adopt tool results
                        results = []
                        for b in blocks:
                            if b.get("type") == "tool_result":
                                results.append({
                                    "tool_use_id": b.get("tool_use_id"),
                                    "content": b.get("content", ""),
                                    "is_error": b.get("is_error", False),
                                })
                        self.add_tool_results(results)
                        # Add remaining text blocks if any
                        other_blocks = [b for b in blocks if b.get("type") != "tool_result"]
                        if other_blocks:
                            self._merge_user_blocks(self._turns[-1], other_blocks)
                    else:
                        self.add_user(content)

                elif role == "assistant":
                    # Extract tool calls if present
                    blocks = self._to_blocks(content)
                    text_parts = []
                    tool_uses = []
                    for b in blocks:
                        b_type = b.get("type")
                        if b_type == "tool_use":
                            tool_uses.append(b)
                        elif b_type == "text":
                            text_parts.append(b.get("text", ""))
                    # Also support OpenAI-style tool_calls key
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            fn = tc.get("function", {})
                            tool_uses.append({
                                "type": "tool_use",
                                "id": tc.get("id"),
                                "name": fn.get("name", tc.get("name")),
                                "input": fn.get("arguments", tc.get("input", {})),
                            })
                    combined_text = "\n".join(t for t in text_parts if t.strip())
                    self.add_assistant_text(
                        text=combined_text,
                        tool_uses=tool_uses if tool_uses else None,
                        reasoning_blocks=[b for b in blocks if b.get("type") in {"thinking", "redacted_thinking"}],
                    )
                self._carry_metadata(msg)

    def _carry_metadata(self, message: Dict[str, Any]) -> None:
        """Retain source boundaries when canonicalization merges adjacent turns."""
        if self._turns:
            for key in ("id", "created_at", "is_private", "recipient_id"):
                if key in message:
                    self._turns[-1][key] = deepcopy(message[key])

    # ─── Public mutators ──────────────────────────────────────────────────────

    def add_user(self, content: Any) -> None:
        """
        Append a user turn.
        If the last turn is already "user", merges content into it.
        """
        if not content:
            return

        blocks = self._to_blocks(content)
        if not blocks:
            return
        if self._pending_tool_call_ids:
            raise ValueError("Cannot add user text while tool results are pending")
        if any(b.get("type") in {"tool_result", "tool_use"} for b in blocks):
            raise ValueError("Use add_tool_results for paired tool results")

        if self._turns and self._turns[-1]["role"] == "user":
            self._merge_user_blocks(self._turns[-1], blocks)
        else:
            self._turns.append({"role": "user", "content": blocks})

    def add_context_note(self, note: str) -> None:
        """
        Inject a context note (e.g. graceful degradation warnings, observations)
        into the conversation as user content, respecting block ordering.
        """
        if not note or not str(note).strip():
            return
        if self._pending_tool_call_ids:
            raise ValueError("Cannot add context while tool results are pending")
        text_block = {"type": "text", "text": str(note).strip()}
        if self._turns and self._turns[-1]["role"] == "user":
            self._turns[-1]["content"].append(text_block)
        else:
            self._turns.append({"role": "user", "content": [text_block]})

    def add_system_note(self, note: str) -> None:
        """Backward-compatible alias for add_context_note."""
        self.add_context_note(note)

    def add_assistant_text(
        self,
        text: str,
        tool_uses: Optional[List[Dict[str, Any]]] = None,
        reasoning_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Append an assistant turn.

        Args:
            text: Assistant text / thoughts.
            tool_uses: List of tool_use blocks:
                       [{"type": "tool_use", "id": "...", "name": "...", "input": {...}}, ...]
        """
        cleaned_text = text.strip() if text else ""
        content: List[Dict[str, Any]] = []
        for block in reasoning_blocks or []:
            if block.get("type") not in {"thinking", "redacted_thinking"}:
                raise ValueError("Invalid provider reasoning block")
            content.append(deepcopy(block))

        if cleaned_text:
            content.append({"type": "text", "text": cleaned_text})

        incoming_tool_uses = []
        incoming_ids = set()
        if tool_uses:
            for tc in tool_uses:
                if not isinstance(tc, dict) or not isinstance(tc.get("id"), str) or not tc["id"].strip():
                    raise ValueError(f"Invalid tool_use block: {tc}")
                if tc["id"] in incoming_ids or tc["id"] in self._seen_tool_call_ids:
                    raise ValueError("Duplicate tool-call ID")
                incoming_ids.add(tc["id"])
                tc_copy = deepcopy(tc)
                tc_copy["type"] = "tool_use"
                if isinstance(tc_copy.get("input"), str):
                    tc_copy["input"] = json.loads(tc_copy["input"])
                if not isinstance(tc_copy.get("input"), dict):
                    raise ValueError("Tool input must be an object")
                incoming_tool_uses.append(tc_copy)
                content.append(tc_copy)

        if not content:
            raise ValueError("Assistant turn cannot be empty (must contain text or tool calls).")

        if self._pending_tool_call_ids:
            raise ValueError(
                f"Cannot add assistant turn while tool results are pending for: {self._pending_tool_call_ids}"
            )

        if self._turns and self._turns[-1]["role"] == "assistant":
            prev_content = self._turns[-1].get("content", [])
            has_prev_tools = any(
                isinstance(b, dict) and b.get("type") == "tool_use"
                for b in prev_content
            )
            if has_prev_tools or incoming_tool_uses:
                raise ValueError("Cannot merge assistant turns when either turn contains tool calls.")
            # Merge text-only assistant turns
            self._turns[-1]["content"].extend(content)
        else:
            self._turns.append({"role": "assistant", "content": content})

        # Register pending tool calls
        for tc in incoming_tool_uses:
            self._pending_tool_call_ids.add(tc["id"])
            self._seen_tool_call_ids.add(tc["id"])

    def add_tool_results(self, results: List[Dict[str, Any]]) -> None:
        """
        Append a batch of tool results in a user turn, paired with pending tool_use IDs.

        Guarantees:
        - All results are validated before any state mutation.
        - Tool result blocks strictly precede regular text blocks in the user turn.
        - Pending tool call IDs are cleared.

        Args:
            results: List of dicts, each with keys:
                     {"tool_use_id": str, "content": str, "is_error": Optional[bool], "tool_name": Optional[str]}
        """
        if not results:
            return

        result_blocks = []
        result_ids = []

        for r in results:
            if not isinstance(r, dict):
                raise TypeError("Tool result must be a dictionary.")
            t_id = r.get("tool_use_id")
            if not t_id or not isinstance(t_id, str):
                raise ValueError(f"Tool result missing valid 'tool_use_id': {r}")
            if t_id not in self._pending_tool_call_ids or t_id in result_ids:
                raise ValueError("Orphaned or duplicate tool result")

            content_val = r.get("content", "")
            is_error = bool(r.get("is_error", False))

            block: Dict[str, Any] = {
                "type": "tool_result",
                "tool_use_id": t_id,
                "content": str(content_val),
            }
            if is_error:
                block["is_error"] = True

            result_blocks.append(block)
            result_ids.append(t_id)

        # Remove matching IDs from pending
        for t_id in result_ids:
            self._pending_tool_call_ids.discard(t_id)

        # Attach to user turn
        if self._turns and self._turns[-1]["role"] == "user":
            existing_blocks = self._turns[-1]["content"]
            # Partition existing blocks into tool_results and text/other
            existing_results = [b for b in existing_blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
            existing_other = [b for b in existing_blocks if not (isinstance(b, dict) and b.get("type") == "tool_result")]
            # Reconstruct: all tool_results first, then text/other
            self._turns[-1]["content"] = existing_results + result_blocks + existing_other
        else:
            self._turns.append({"role": "user", "content": result_blocks})

    def add_tool_result(
        self,
        tool_use_id: str,
        result: str,
        tool_name: str = "",
        max_inline_chars: Optional[int] = None,
        is_error: bool = False,
    ) -> None:
        """
        Convenience wrapper to add a single tool result.
        """
        self.add_tool_results([{
            "tool_use_id": tool_use_id,
            "content": result,
            "tool_name": tool_name,
            "is_error": is_error,
        }])

    # ─── Read-only accessors ──────────────────────────────────────────────────

    def get_messages(self) -> List[Dict[str, Any]]:
        """Return an independent deep copy of the message list ready for an LLM API call."""
        return deepcopy(self._turns)

    def last_role(self) -> Optional[str]:
        """Return the role of the most recent turn, or None if history is empty."""
        return self._turns[-1]["role"] if self._turns else None

    @property
    def pending_tool_calls(self) -> Set[str]:
        """Return a copy of pending tool call IDs awaiting results."""
        return set(self._pending_tool_call_ids)

    @property
    def has_pending_tool_calls(self) -> bool:
        return len(self._pending_tool_call_ids) > 0

    def __len__(self) -> int:
        return len(self._turns)

    # ─── Private helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _to_blocks(content: Any) -> List[Dict[str, Any]]:
        """Normalize content into a list of structured block dictionaries."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        if isinstance(content, list):
            if not all(isinstance(b, dict) for b in content):
                raise TypeError("Content blocks in list must be dictionaries.")
            return deepcopy(content)
        raise TypeError("Message content must be a string or list of block dicts.")

    @classmethod
    def _merge_user_blocks(cls, existing_turn: Dict[str, Any], new_blocks: List[Dict[str, Any]]) -> None:
        """Merge new blocks into an existing user turn, preserving block ordering."""
        existing_blocks = existing_turn["content"]
        # In user turns, tool_results must precede text/other blocks
        existing_results = [b for b in existing_blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        existing_other = [b for b in existing_blocks if not (isinstance(b, dict) and b.get("type") == "tool_result")]

        new_results = [b for b in new_blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        new_other = [b for b in new_blocks if not (isinstance(b, dict) and b.get("type") == "tool_result")]

        existing_turn["content"] = existing_results + new_results + existing_other + new_other
