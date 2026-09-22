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
      1. Written to a scoped, content-addressed artifact on disk.
      2. Replaced in-context with: head (HEADER_CHARS) + separator + tail (TAIL_CHARS).
      3. The separator references the cache file path so the agent can ask
         a tool to read it if the full content is needed.

Previews reduce replay costs while retaining access to full evidence. If the
write fails, full evidence is retained and the context preflight can stop safely.
"""

import hashlib
import logging
import os
import uuid
import json
import time
from pathlib import Path

logger = logging.getLogger("carole.observation_cache")

# ─── Configuration ────────────────────────────────────────────────────────────

from core.config import CAROLE_HOME_DIR

CACHE_DIR = CAROLE_HOME_DIR / "observations"

# Observations up to this size are returned verbatim (≈750 tokens at 4 chars/tok)
MAX_INLINE_CHARS = 3_000

# Head and tail sizes for truncated observations
HEADER_CHARS = 1_200
TAIL_CHARS = 600


def _scope_dir(scope: str | None) -> Path:
    return CACHE_DIR / hashlib.sha256(scope.encode()).hexdigest() if scope else CACHE_DIR


def cache_observation(tool_name: str, content: str, scope: str | None = None, inline_limit: int = MAX_INLINE_CHARS) -> str:
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

    if len(content) <= inline_limit:
        return content

    # Write full output to disk
    content_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:16]
    # Sanitize tool_name for filesystem safety
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in tool_name)[:40]
    directory = _scope_dir(scope)
    cache_file = directory / f"{safe_name}_{content_hash}.txt"

    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Exclusive creation avoids overwriting or following an existing symlink.
        try:
            fd = os.open(cache_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Verify the immutable artifact before reusing it (including symlink rejection).
            if cache_file.is_symlink() or cache_file.read_text(encoding="utf-8") != content:
                return content
        else:
            with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as stream:
                stream.write(content)
        logger.debug(
            "Large observation from '%s' cached (%d chars) → %s",
            tool_name, len(content), cache_file,
        )
    except OSError as e:
        # Never silently destroy evidence when persistence fails. The normal
        # context-pressure handler can stop the run without claiming completion.
        logger.warning("Could not persist observation from '%s': %s", tool_name, type(e).__name__)
        return "[cache write failed; full evidence retained]\n" + content

    head_size = min(HEADER_CHARS, max(80, inline_limit // 2))
    tail_size = min(TAIL_CHARS, max(40, inline_limit // 4))
    head = content[:head_size]
    tail = content[-tail_size:]
    # Preserve diagnostic lines that a generic head/tail preview would miss.
    diagnostics = []
    import re
    for line in content.splitlines():
        if re.search(r"\b(error|failed|failure|exception|traceback)\b", line, re.I):
            diagnostics.append(line[:240])
            if len(diagnostics) == 3:
                break
    diagnostic_text = "\n[Diagnostic excerpts]\n" + "\n".join(diagnostics) if diagnostics else ""
    dropped = max(0, len(content) - head_size - tail_size)

    return (
        f"{head}\n"
        f"... [{dropped:,} chars omitted — full output saved to: {cache_file}] ...\n"
        f"(Use read_observation(artifact_id=\"{cache_file.name}\", offset=0, limit=2500) to retrieve more. Discover it with fetch_tool_schemas if needed.)\n"
        f"{tail}{diagnostic_text}"
    )


def read_observation(artifact_id: str, scope: str, offset: int = 0, limit: int = 2500, query: str | None = None) -> str:
    """Retrieve bounded characters using a trusted team/agent scope, never a caller path."""
    import re
    if not scope or not re.fullmatch(r"[\w-]+\.txt", artifact_id, flags=re.ASCII):
        raise ValueError("Invalid observation artifact")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2500:
        raise ValueError("limit must be between 1 and 2500")
    directory = _scope_dir(scope).resolve()
    path = (directory / artifact_id).resolve()
    if not path.is_relative_to(directory):
        raise ValueError("Observation path escapes its owner scope")
    if query is not None:
        if not isinstance(query, str) or not 1 <= len(query) <= 256:
            raise ValueError("Search query must contain 1 to 256 characters")
        hits, used, scanned = [], 0, 0
        with path.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                scanned += len(line)
                if scanned > 2_000_000:
                    break
                if query.casefold() in line.casefold():
                    entry = f"{number}: {line[:500].rstrip()}\n"
                    if used + len(entry) > limit:
                        break
                    hits.append(entry)
                    used += len(entry)
        return f"[artifact: {artifact_id}; literal search; bounded to 2M characters]\n" + ("".join(hits) or "No match in searched range.")
    with path.open(encoding="utf-8") as stream:
        # Text seeks use opaque cookies rather than character offsets. Discard
        # bounded blocks so multibyte text uses the same offsets as the preview.
        remaining = offset
        while remaining:
            discarded = stream.read(min(remaining, 8192))
            if not discarded:
                break
            remaining -= len(discarded)
        excerpt = stream.read(limit)
        more = bool(stream.read(1))
    return f"[artifact: {artifact_id}; offset: {offset}; next_offset: {offset + len(excerpt)}; more: {str(more).lower()}]\n{excerpt}"


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


def pin_observations(scope: str, checkpoint_id: str, messages) -> None:
    """Durably protect artifact references before a checkpoint can be published."""
    import re
    uuid.UUID(checkpoint_id)
    directory = _scope_dir(scope)
    directory.mkdir(parents=True, exist_ok=True)
    references = sorted(set(re.findall(r"[A-Za-z0-9_-]+\.txt", json.dumps(messages, default=str))))
    pins = directory / f"checkpoint_{checkpoint_id}.pins"
    with pins.open("x", encoding="utf-8") as stream:
        json.dump(references, stream)


def expired_observations(scope: str, max_age_seconds: int = 7 * 86400) -> list[Path]:
    """Dry-run lifecycle inventory. Never delete unknown or checkpoint-pinned evidence."""
    if not scope or max_age_seconds < 0:
        raise ValueError("A scope and nonnegative age are required")
    directory = _scope_dir(scope)
    protected = set()
    for pin in directory.glob("*.pins"):
        try:
            protected.update(json.loads(pin.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return []  # Unknown ownership: retain everything.
    cutoff = time.time() - max_age_seconds
    return [path for path in directory.glob("*.txt")
            if not path.is_symlink() and path.name not in protected and path.stat().st_mtime < cutoff]
