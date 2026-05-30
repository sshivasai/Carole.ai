"""
# backend/core/chat/event_bus.py

This file contains the EventBus system using a Pub/Sub mechanism.

Responsibilities:
1. Manage asynchronous communication between multiple active Agents (Workers, Coordinator, Judge).
2. Broadcast messages to the frontend via WebSockets.
3. Route private messages (/@name) to specific agent queues.
4. Route group messages (@name or generic) to the public thread.
5. Stream tool execution progress and Playwright screenshots to the UI.
"""

import asyncio
from typing import Dict, Set

class EventBus:
    def __init__(self):
        # Maps a topic string (e.g. "team:uuid", "agent:uuid") to a set of subscriber queues
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """
        Subscribe to a topic.
        Returns an asyncio.Queue from which the subscriber can read streamed events.
        """
        queue = asyncio.Queue()
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = set()
            self._subscribers[topic].add(queue)
        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        """
        Unsubscribe a queue from a specific topic to free resources.
        """
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(queue)
                # Clean up empty topic keys to save memory
                if not self._subscribers[topic]:
                    del self._subscribers[topic]

    async def publish(self, topic: str, message: dict):
        """
        Publish a dictionary message to all subscribers of a specific topic.
        """
        async with self._lock:
            # Copy the set of queues to avoid modification issues while iterating
            queues = self._subscribers.get(topic, set()).copy()

        if not queues:
            return

        # Push the message to all listening queues concurrently
        for queue in queues:
            await queue.put(message)

# Global singleton instance of the EventBus to be shared across backend modules
event_bus = EventBus()
