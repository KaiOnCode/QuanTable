"""BaseTool — abstract base for all agent tools.

Every tool inherits from BaseTool. The registry auto-discovers all subclasses.
Design borrowed from Vibe-Trading's tool system.
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

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


def emit_progress(
    stage: str, current: int | None = None, total: int | None = None, message: str = ""
):
    """Called from inside tool.execute() to report progress."""
    emitter = get_emitter()
    if emitter:
        emitter(stage=stage, current=current, total=total, message=message)


@dataclass
class ToolMeta:
    """Metadata for a tool. Used by registry for execution strategy."""

    name: str = ""
    description: str = ""
    is_readonly: bool = True  # Read-only = safe to parallelize
    is_destructive: bool = False  # Write tools that can cause damage
    timeout: int = 30  # Seconds (0 = no timeout, only for readonly)
    repeatable: bool = True  # Can be called multiple times
    category: str = "general"  # financial / research / data / workspace / memory
    requires_auth: bool = False
    cooldown_seconds: int = 0  # Min seconds between calls (0 = no limit)
    input_schema: dict = field(default_factory=dict)
    # input_schema format: {"properties": {"ticker": {"type": "string", "description": "..."}},
    #                        "required": ["ticker"]}


class BaseTool(ABC):
    """Abstract base for all agent tools.

    Subclass and implement execute(). The registry auto-discovers all
    subclasses via __subclasses__(). Use build_tool() for simpler creation.
    """

    meta: ToolMeta = ToolMeta()

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool. Must return a JSON string."""
        ...

    def prompt(self) -> str:
        """Generate the tool's description for the LLM system prompt.

        Claude Code pattern: each tool has a prompt() method that returns
        detailed usage guidance (when to use, when NOT to use, parameter
        meanings, caveats). This replaces the static one-line description
        with rich, tool-specific instructions.

        Subclasses override to provide tool-specific guidance.
        Default returns meta.description.
        """
        return self.meta.description

    def validate_params(self, params: dict) -> dict | None:
        """Validate parameters against input_schema. Returns error dict or None."""
        schema = self.meta.input_schema
        if not schema or not schema.get("required"):
            return None

        # Check required params
        for field_name in schema.get("required", []):
            val = params.get(field_name)
            if val is None or (isinstance(val, str) and not val.strip()):
                return {
                    "status": "error",
                    "error": f"Missing required parameter: {field_name}",
                    "hint": f"Please provide a value for '{field_name}'",
                }

        return None

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function-calling schema.

        Uses explicit input_schema if provided, otherwise infers from type hints.
        """
        schema = self.meta.input_schema
        if schema:
            params = {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        else:
            # Fallback: infer from type hints
            params: dict[str, Any] = {
                "type": "object",
                "properties": {},
                "required": [],
            }
            import inspect

            sig = inspect.signature(self.execute)
            type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
            for name, param in sig.parameters.items():
                if name == "self":
                    continue
                annot = (
                    param.annotation
                    if param.annotation != inspect.Parameter.empty
                    else str
                )
                json_type = type_map.get(annot, "string")
                params["properties"][name] = {"type": json_type, "description": name}
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


# ── Tool factory (inspired by Claude Code's buildTool) ──────────


def build_tool(
    name: str,
    description: str,
    execute_fn,
    input_schema: dict | None = None,
    *,
    is_readonly: bool = True,
    is_destructive: bool = False,
    timeout: int = 30,
    repeatable: bool = True,
    category: str = "general",
) -> BaseTool:
    """Create a BaseTool instance from a function, without writing a class.

    Inspired by Claude Code's buildTool() factory in tools.ts.

    Args:
        name: Tool name (snake_case, used by LLM)
        description: What the tool does (shown to LLM, be specific)
        execute_fn: async or sync function(params) -> str
        input_schema: {"properties": {...}, "required": [...]}
        is_readonly: True for data tools (can parallelize)
        is_destructive: True for tools that can cause damage
        timeout: Max execution seconds
        repeatable: Can be called multiple times per session
        category: Grouping for system prompt listing
    """
    meta = ToolMeta(
        name=name,
        description=description,
        is_readonly=is_readonly,
        is_destructive=is_destructive,
        timeout=timeout,
        repeatable=repeatable,
        category=category,
        input_schema=input_schema or {},
    )

    class _FactoryTool(BaseTool):
        def execute(self, **kwargs) -> str:
            result = execute_fn(**kwargs)
            if not isinstance(result, str):
                return json.dumps(
                    {"status": "ok", "data": str(result)}, ensure_ascii=False
                )
            return result

    tool = _FactoryTool()
    tool.meta = meta
    return tool
