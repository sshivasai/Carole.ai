"""Bound corrective turns independently from the overall execution limit."""
from collections import Counter
import asyncio
import time


class LoopGuard:
    def __init__(self, deadline_seconds: float = 1800):
        self.deadline = time.monotonic() + deadline_seconds
        self.corrections = Counter()

    def allow_correction(self, reason: str, limit: int = 2) -> bool:
        self.corrections[reason] += 1
        return self.corrections[reason] <= limit

    def check(self, token=None):
        if token and token.is_cancelled:
            raise asyncio.CancelledError()
        if time.monotonic() >= self.deadline:
            raise TimeoutError("Agent execution deadline reached; completion is unverified.")


async def cancellable_events(stream, token=None, idle_timeout: float = 120):
    """Cancellation wakes blocked provider reads, not just the next tool call."""
    iterator = stream.__aiter__()
    cancelled = asyncio.create_task(token.wait()) if token else None
    pending = None
    try:
        while True:
            pending = asyncio.create_task(anext(iterator))
            waits = {pending} | ({cancelled} if cancelled else set())
            done, _ = await asyncio.wait(waits, timeout=idle_timeout, return_when=asyncio.FIRST_COMPLETED)
            if cancelled and cancelled in done:
                raise asyncio.CancelledError()
            if pending not in done:
                raise TimeoutError("Provider stream stalled.")
            try:
                yield pending.result()
            except StopAsyncIteration:
                break
    finally:
        for task in (pending, cancelled):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (pending, cancelled) if t), return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close:
            await close()
