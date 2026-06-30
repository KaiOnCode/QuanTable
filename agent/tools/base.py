"""BaseTool — abstract base for all agent tools.

Every tool inherits from BaseTool. The registry auto-discovers all subclasses.
Design borrowed from Vibe-Trading's tool system.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Thread-local emitter for progress events (set by AgentLoop before invocation)
_tool_emitter: threading.local = threading.local()


def get_emitter():
    return getattr(_tool_emitter, "emitter", None)


def set_emitter(emitter):
    _tool_emitter.emitter = emitter


def clear_emitter():
    if hasattr(_tool_emitter, "emitter"):
        del _tool_emitter.emitter


def emit_progress(stage: str, current: int | None = None,
                  total: int | None = None, message: str = ""):
    """Called from inside tool.execute() to report progress."""
    emitter = get_emitter()
    if emitter:
        emitter(stage=stage, current=current, total=total, message=message)


@dataclass
class ToolMeta:
    """Metadata for a tool. Used by registry for execution strategy."""
    name: str = ""
    description: str = ""
    is_readonly: bool = True    # Read-only = safe to parallelize
    timeout: int = 30           # Seconds (0 = no timeout, only for readonly)
    repeatable: bool = True     # Can be called multiple times
    category: str = "general"   # financial / research / data / workspace / memory
    requires_auth: bool = False
    cooldown_seconds: int = 0   # Min seconds between calls (0 = no limit)


class BaseTool(ABC):
    """Abstract base for all agent tools.

    Subclass and implement execute(). The registry auto-discovers all
    subclasses via __subclasses__().
    """

    meta: ToolMeta = ToolMeta()

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool. Must return a JSON string."""
        ...

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function-calling schema."""
        params: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        # Parse parameter annotations from the execute method's type hints
        import inspect
        sig = inspect.signature(self.execute)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            annot = param.annotation if param.annotation != inspect.Parameter.empty else str
            type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
            json_type = type_map.get(annot, "string")
            params["properties"][name] = {"type": json_type, "description": f"Parameter: {name}"}
            if param.default == inspect.Parameter.empty:
                params["required"].append(name)
        if not params["required"]:
            del params["required"]
        return {
            "type": "function",
            "function": {
                "name": self.meta.name,
                "description": self.meta.description,
                "parameters": params,
            },
        }

    @classmethod
    def check_available(cls) -> bool:
        """Override to conditionally register. e.g., check API key exists."""
        return True

    def _ok(self, data: dict | None = None) -> str:
        return json.dumps({"status": "ok", **(data or {})}, ensure_ascii=False)

    def _error(self, msg: str) -> str:
        return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
