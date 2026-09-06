"""
# backend/core/agent/observation_cache.py

Observation Budget & Disk Caching for native tool-calling loop.

Problem: Tools like read_file, execute_command, or browser_task can return
tens of thousands of characters. If we inject the full output verbatim into
the message history on every tool call, the context window fills up in 3-4
loop iterations, triggering expensive compaction or hitting 400 errors.

Solution:
  - Observations <= MAX_INLINE_CHARS are returned as-is.
  - Observations > MAX_INLINE_CHARS are:
      1. Written to a temp file on disk.
      2. Replaced in-context with: head (HEADER_CHARS) + separator + tail (TAIL_CHARS).
      3. The separator references the cache file path so the agent can ask
         a tool to read it if the full content is needed.

This caps the worst-case per-tool token cost at ~1,000 tokens regardless of
how large the output is, while still giving the agent full access to the data.
"""

import hashlib
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger("carole.observation_cache")

# ─── Configuration ────────────────────────────────────────────────────────────

CACHE_DIR = Path(tempfile.gettempdir()) / "carole_obs_cache"

# Observations up to this size are returned verbatim (≈750 tokens at 4 chars/tok)
MAX_INLINE_CHARS = 3_000

# Head and tail sizes for truncated observations
HEADER_CHARS = 1_200
TAIL_CHARS = 600


def cache_observation(tool_name: str, content: str) -> str:
    """
    Return content verbatim if small, otherwise write excess to disk and return
    a head+tail summary with a disk reference.

    This is the *only* entry point needed — call it on every tool result before
    adding it to MessageHistory.

    Args:
        tool_name: Tool name (used in cache filename for readability).
        content:   Raw tool output string.

    Returns:
        Either the original content (if small) or a truncated summary string.
    """
    if not isinstance(content, str):
        content = str(content)

    if len(content) <= MAX_INLINE_CHARS:
        return content

    # Write full output to disk
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    content_hash = hashlib.md5(content.encode("utf-8", errors="replace")).hexdigest()[:12]
    # Sanitize tool_name for filesystem safety
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in tool_name)[:40]
    cache_file = CACHE_DIR / f"{safe_name}_{content_hash}.txt"

    try:
        cache_file.write_text(content, encoding="utf-8", errors="replace")
        logger.debug(
            "Large observation from '%s' cached (%d chars) → %s",
            tool_name, len(content), cache_file,
        )
    except OSError as e:
        # If we can't write to disk, fall back to aggressive inline truncation
        logger.warning("Could not write observation cache for '%s': %s", tool_name, e)
        return (
            content[:HEADER_CHARS]
            + f"\n\n... [{len(content) - HEADER_CHARS - TAIL_CHARS:,} chars omitted — cache write failed] ...\n\n"
            + content[-TAIL_CHARS:]
        )

    head = content[:HEADER_CHARS]
    tail = content[-TAIL_CHARS:]
    dropped = len(content) - HEADER_CHARS - TAIL_CHARS

    return (
        f"{head}\n"
        f"... [{dropped:,} chars omitted — full output saved to: {cache_file}] ...\n"
        f"(Use read_file or execute_command to read the cached file if you need the full content.)\n"
        f"{tail}"
    )


def clear_cache() -> int:
    """
    Remove all cached observation files from the temp directory.
    Returns the number of files deleted.
    Call this on application shutdown if desired (optional — OS tmp cleanup handles it).
    """
    if not CACHE_DIR.exists():
        return 0
    deleted = 0
    for f in CACHE_DIR.glob("*.txt"):
        try:
            f.unlink()
            deleted += 1
        except OSError:
            pass
    logger.info("Cleared %d observation cache files from %s.", deleted, CACHE_DIR)
    return deleted
