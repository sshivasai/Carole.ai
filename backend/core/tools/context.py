"""
# backend/core/tools/context.py

Provides execution context, cancellation tokens, and permission structures for tools.
"""

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Set, Optional, Callable, Awaitable

file_read_scope: ContextVar[Optional[str]] = ContextVar("file_read_scope", default=None)

class CancellationToken:
    """
    A cancellation token that tools and loops can periodically check.
    Allows for graceful abortion of long-running operations.
    """
    def __init__(self):
        self._event = asyncio.Event()

    def cancel(self):
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def wait(self):
        """Wait until cancelled."""
        await self._event.wait()

@dataclass
class ToolPermissionContext:
    """
    Granular permission rules.
    - always_allow: tools in this set instantly execute, bypassing human/judge.
    - always_deny: tools in this set are immediately rejected.
    """
    always_allow: Set[str] = field(default_factory=set)
    always_deny: Set[str] = field(default_factory=set)

@dataclass
class ToolExecutionContext:
    """
    Passed to tools during execution, providing identity, streaming, and cancellation.
    """
    agent_id: str
    agent_name: str
    team_id: str
    cancellation_token: CancellationToken
    emit_progress: Optional[Callable[[str], Awaitable[None]]] = None
    active_message_id: Optional[str] = None
    agent_role: Optional[str] = None
    run_id: Optional[str] = None
