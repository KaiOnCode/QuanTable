"""Data cache with pickle + SHA256 integrity checks.

Ported from Vibe-Trading's alpha_bench_tool.py cache pattern.
Each cached file is paired with a .sha256 sidecar for integrity verification.
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".agentic-quant" / "cache"
DEFAULT_TTL_HOURS = 24


def _sha256_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(cache_path.suffix + ".sha256")


def _hashes_equal(a: str, b: str) -> bool:
    """Constant-time comparison of two hex digests."""
    import hmac

    return hmac.compare_digest(a.strip().lower(), b.strip().lower())


def read_cache(cache_path: Path, max_age_hours: int = DEFAULT_TTL_HOURS) -> Any | None:
    """Read a cached pickle blob, verifying SHA256 integrity and TTL.

    Returns None if cache miss, corrupted, or expired.
    """
    if not cache_path.is_file():
        return None

    sha_path = _sha256_path(cache_path)
    if not sha_path.is_file():
        logger.debug("cache miss (no sha256 sidecar): %s", cache_path)
        return None

    try:
        blob = cache_path.read_bytes()
        expected = sha_path.read_text(encoding="utf-8").strip()
        actual = hashlib.sha256(blob).hexdigest()
        if not _hashes_equal(expected, actual):
            logger.warning("cache corrupted (sha256 mismatch): %s", cache_path)
            cache_path.unlink(missing_ok=True)
            sha_path.unlink(missing_ok=True)
            return None
    except OSError as exc:
        logger.warning("cache read failed: %s", exc)
        return None

    # TTL check
    mtime = datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
    if datetime.now(timezone.utc) - mtime > timedelta(hours=max_age_hours):
        logger.debug("cache expired (age > %dh): %s", max_age_hours, cache_path)
        return None

    try:
        return pickle.loads(blob)
    except Exception as exc:
        logger.warning("cache unpickle failed: %s", exc)
        return None


def write_cache(cache_path: Path, data: Any) -> None:
    """Write data as pickle blob with SHA256 sidecar. Failures are non-fatal."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        blob = pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL)
        cache_path.write_bytes(blob)
        _sha256_path(cache_path).write_text(
            hashlib.sha256(blob).hexdigest(), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("cache write failed (non-fatal): %s", exc)


def invalidate_cache(cache_path: Path) -> None:
    """Remove both the cache file and its SHA256 sidecar."""
    cache_path.unlink(missing_ok=True)
    _sha256_path(cache_path).unlink(missing_ok=True)


def cache_key(*parts: str) -> Path:
    """Build a deterministic cache path from key components."""
    key = "_".join(p.replace("/", "_").replace(" ", "_") for p in parts)
    return DEFAULT_CACHE_DIR / f"{key}.pkl"
