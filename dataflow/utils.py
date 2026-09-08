"""Utility functions for dataflow providers.

Ported from Vibe-Trading's alpha_bench_tool.py retry pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    tries: int = 3,
    base_delay: float = 1.0,
    exc_types: tuple = (Exception,),
) -> T | None:
    """Call ``fn`` up to ``tries`` times with exponential backoff.

    Returns None if all attempts fail.
    """
    last_exc: Exception | None = None
    for attempt in range(tries):
        try:
            return fn()
        except exc_types as exc:
            last_exc = exc
            if attempt == tries - 1:
                break
            delay = base_delay * (2**attempt)
            logger.debug("retry %d/%d after %.1fs: %s", attempt + 1, tries, delay, exc)
            time.sleep(delay)
    if last_exc is not None:
        logger.warning("retry exhausted (%d attempts): %s", tries, last_exc)
    return None


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert value to float, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Convert value to int, returning default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def truncate_text(text: str, max_chars: int = 500) -> str:
    """Truncate text to max_chars, adding ellipsis if truncated."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
