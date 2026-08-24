"""
# backend/core/auth/rate_limiter.py

Centralized rate limiter configuration using slowapi.
Provides safe decorators with automatic no-op fallback when slowapi is disabled or in test environments.
"""

import logging
from typing import Callable

logger = logging.getLogger("carole.limiter")

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    limiter = Limiter(key_func=get_remote_address)
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    limiter = None
    RateLimitExceeded = Exception  # type: ignore
    logger.warning("slowapi not installed — rate limiting disabled.")


def rate_limit(limit_str: str) -> Callable:
    """Safe decorator wrapper that applies rate limiting if slowapi is available."""
    def decorator(fn: Callable) -> Callable:
        if SLOWAPI_AVAILABLE and limiter is not None:
            return limiter.limit(limit_str)(fn)
        return fn
    return decorator
