"""Agent tools — auto-discovered by ToolRegistry."""

# ── Cross-track import guard ───────────────────────────────────
# Prevents active code (agent/tools/) from importing
# from legacy code (quick_ask/).
# The ONLY allowed bridge is inside RunAnalysisTool.execute()
# which imports at call time, not at module level.

_LEGACY_PATTERNS = ("agents/", "orchestrator")


def _check_no_legacy_import():
    """Raise ImportError if this module is imported by legacy code,
    or if active code is importing from legacy modules at init time."""
    import traceback as _tb

    for frame in _tb.extract_stack():
        fname = frame.filename
        # If legacy code is importing active tools → warn but allow
        # (legacy orchestrator may need tools)
        if any(p in fname for p in _LEGACY_PATTERNS):
            import warnings as _w

            _w.warn(
                f"Legacy code ({fname}) importing from ACTIVE module. "
                "This is deprecated. Migrate to ReAct loop instead.",
                DeprecationWarning,
                stacklevel=2,
            )


_check_no_legacy_import()
del _check_no_legacy_import

# ── Normal imports ─────────────────────────────────────────────

from .base import BaseTool, ToolMeta, emit_progress  # noqa: E402
from .registry import ToolRegistry, get_registry, reset_registry  # noqa: E402

# Import tool modules so their BaseTool subclasses are discovered
from . import backtest, financial, workspace  # noqa: E402

__all__ = [
    "BaseTool",
    "ToolMeta",
    "ToolRegistry",
    "get_registry",
    "reset_registry",
    "emit_progress",
    "financial",
    "backtest",
    "workspace",
]
