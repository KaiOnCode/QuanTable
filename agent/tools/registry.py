"""ToolRegistry — central registry for all agent tools.

Auto-discovers BaseTool subclasses. Provides lookup, execution, and
OpenAI-compatible schema generation. Categorizes tools for execution strategy.

Design borrowed from Vibe-Trading's ToolRegistry pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import BaseTool, ToolMeta, set_emitter, clear_emitter

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry of all agent tools. Auto-discovers BaseTool subclasses."""

    def __init__(self, include_shell: bool = False):
        self._tools: dict[str, BaseTool] = {}
        self._meta: dict[str, ToolMeta] = {}
        self._include_shell = include_shell
        self._last_call: dict[str, float] = {}  # For cooldown tracking

    def discover(self):
        """Auto-discover all BaseTool subclasses and register them."""
        from .base import BaseTool

        def _recurse(cls):
            for sub in cls.__subclasses__():
                if not sub.__subclasses__():
                    self._register_instance(sub)
                _recurse(sub)

        _recurse(BaseTool)
        logger.info("ToolRegistry: discovered %d tools", len(self._tools))

    def _register_instance(self, tool_cls):
        """Register a single tool instance."""
        try:
            if not tool_cls.check_available():
                logger.debug("Tool %s not available (check_available=False)", tool_cls.__name__)
                return
            instance = tool_cls()
            name = instance.meta.name
            # Shell tools filtered unless explicitly enabled
            if name in ("bash", "background_run", "check_background") and not self._include_shell:
                return
            self._tools[name] = instance
            self._meta[name] = instance.meta
        except Exception as exc:
            logger.warning("Failed to register %s: %s", tool_cls.__name__, exc)

    def register(self, tool: BaseTool):
        """Manually register a tool instance."""
        self._tools[tool.meta.name] = tool
        self._meta[tool.meta.name] = tool.meta

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_meta(self, name: str) -> ToolMeta | None:
        return self._meta.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def list_by_category(self) -> dict[str, list[str]]:
        cats: dict[str, list[str]] = {}
        for name, meta in self._meta.items():
            cats.setdefault(meta.category, []).append(name)
        return cats

    def get_definitions(self) -> list[dict]:
        """Return OpenAI-compatible tool definitions for all registered tools."""
        defs = []
        for tool in self._tools.values():
            try:
                defs.append(tool.to_openai_schema())
            except Exception as exc:
                logger.warning("Schema generation failed for %s: %s", tool.meta.name, exc)
        return defs

    def get_compact_text(self) -> str:
        """Return a compact one-line listing of tool names for system prompt."""
        names = sorted(self._tools.keys())
        return ", ".join(names)

    def get_description_text(self) -> str:
        """Return a formatted string listing all tools for system prompt."""
        lines = []
        by_cat = self.list_by_category()
        for cat, names in sorted(by_cat.items()):
            lines.append(f"\n## {cat}")
            for name in names:
                meta = self._meta[name]
                ro = "R" if meta.is_readonly else "W"
                lines.append(f"- {name} [{ro}] {meta.description[:120]}")
        return "\n".join(lines)

    def execute(self, name: str, params: dict[str, Any], emitter=None) -> str:
        """Execute a tool by name. Returns JSON string. Errors wrapped in {'status':'error'}."""
        tool = self._tools.get(name)
        if not tool:
            return '{"status":"error","error":"tool_not_found"}'

        # Cooldown check
        if tool.meta.cooldown_seconds > 0:
            now = __import__("time").time()
            last = self._last_call.get(name, 0)
            if now - last < tool.meta.cooldown_seconds:
                return '{"status":"error","error":"cooldown"}'
            self._last_call[name] = now

        if emitter:
            set_emitter(emitter)
        try:
            result = tool.execute(**params)
            if not isinstance(result, str):
                result = str(result)
            return result
        except Exception as exc:
            logger.warning("Tool %s failed: %s", name, exc, exc_info=True)
            return f'{{"status":"error","error":"{str(exc)[:500]}"}}'
        finally:
            clear_emitter()

    @property
    def tool_count(self) -> int:
        return len(self._tools)


# Global singleton
_registry: ToolRegistry | None = None


def get_registry(include_shell: bool = False) -> ToolRegistry:
    """Get or create the global tool registry singleton."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry(include_shell=include_shell)
        _registry.discover()
    return _registry


def reset_registry():
    """Reset global registry (for testing)."""
    global _registry
    _registry = None
