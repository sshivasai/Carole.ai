"""
# backend/core/chat/event_bus.py

EventBus system using a Pub/Sub mechanism with event history buffer.

Responsibilities:
1. Manage asynchronous communication between multiple active Agents.
2. Broadcast messages to the frontend via WebSockets.
3. Maintain an event history buffer (last 100 events per topic) for late-joining clients.
4. Support both topic-level (team) and agent-level (private) communication.

Race-condition fixes (v2):
- publish() copies the subscriber set *inside* the lock and does queue.put()
  *outside* the lock so that slow consumers cannot block publishers.
- History is no longer deleted when the last subscriber leaves — a reconnecting
  client still gets the replay buffer.
- Queues are bounded (maxsize from config) to prevent OOM under slow consumers.
"""

import asyncio
import logging
from collections import deque
from typing import Dict, Set, List

from core.config import MAX_QUEUE_SIZE

logger = logging.getLogger("carole.event_bus")


class EventBus:
    def __init__(self, history_size: int = 100):
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._history: Dict[str, deque] = {}
        self._history_size = history_size
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """Subscribe to a topic. Returns a bounded queue to read streamed events from."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = set()
            if topic not in self._history:
                self._history[topic] = deque(maxlen=self._history_size)
            self._subscribers[topic].add(queue)

            # Replay recent history to late-joining subscriber
            for event in self._history[topic]:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    # Subscriber queue already full during replay — skip oldest events
                    break

        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        """Unsubscribe a queue from a specific topic.

        NOTE: history is intentionally kept so that a client reconnecting
        immediately after the last subscriber leaves still gets a replay.
        """
        async with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic].discard(queue)
                # Clean up the subscriber set entry but preserve history
                if not self._subscribers[topic]:
                    del self._subscribers[topic]

    async def publish(self, topic: str, message: dict):
        """Publish a message to all subscribers of a topic and record in history.

        The subscriber set is copied *inside* the lock (to avoid a race with
        concurrent unsubscribes) and the actual queue.put() calls happen
        *outside* the lock so that a slow consumer never blocks the publisher.
        """
        async with self._lock:
            # Record in history (skip high-frequency noise events)
            if message.get("type") not in ("thought_delta", "typing"):
                if topic not in self._history:
                    self._history[topic] = deque(maxlen=self._history_size)
                self._history[topic].append(message)

            queues = list(self._subscribers.get(topic, set()))

        # Deliver outside the lock
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning(
                    "EventBus: dropped message for topic '%s' — subscriber queue full (maxsize=%d)",
                    topic, MAX_QUEUE_SIZE
                )

    async def publish_to_agent(self, agent_id: str, message: dict):
        """Publish a message to a specific agent's private topic."""
        topic = f"agent:{agent_id}"
        await self.publish(topic, message)

    def get_history(self, topic: str) -> List[dict]:
        """Returns the event history for a topic."""
        return list(self._history.get(topic, []))


# Global singleton
event_bus = EventBus()
