"""
# backend/core/chat/event_bus.py

EventBus system using a Pub/Sub mechanism with event history buffer.

Responsibilities:
1. Manage asynchronous communication between multiple active Agents.
2. Broadcast messages to the frontend via WebSockets.
3. Maintain an event history buffer (last 100 events per topic) for late-joining clients.
4. Support both topic-level (team) and agent-level (private) communication.
"""

import asyncio
from collections import deque
from typing import Dict, Set, List


class EventBus:
    def __init__(self, history_size: int = 100):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._history: Dict[str, deque] = {}
        self._history_size = history_size
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """Subscribe to a topic. Returns a queue to read streamed events from."""
        queue = asyncio.Queue()
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = set()
                self._history[topic] = deque(maxlen=self._history_size)
            self._subscribers[topic].add(queue)

            # Send recent history to new subscriber so they see what they missed
            for event in self._history.get(topic, []):
                await queue.put(event)

        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        """Unsubscribe a queue from a specific topic."""
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(queue)
                if not self._subscribers[topic]:
                    del self._subscribers[topic]
                    # Clean up history to prevent memory growth for inactive topics
                    if topic in self._history:
                        del self._history[topic]

    async def publish(self, topic: str, message: dict):
        """Publish a message to all subscribers of a topic and record in history."""
        async with self._lock:
            # Record in history (skip high-frequency events like thought_delta)
            if message.get("type") not in ("thought_delta", "typing"):
                if topic not in self._history:
                    self._history[topic] = deque(maxlen=self._history_size)
                self._history[topic].append(message)

            queues = self._subscribers.get(topic, set()).copy()

        if not queues:
            return

        for queue in queues:
            await queue.put(message)

    async def publish_to_agent(self, agent_id: str, message: dict):
        """Publish a message to a specific agent's private topic."""
        topic = f"agent:{agent_id}"
        await self.publish(topic, message)

    def get_history(self, topic: str) -> List[dict]:
        """Returns the event history for a topic."""
        return list(self._history.get(topic, []))


# Global singleton
event_bus = EventBus()
