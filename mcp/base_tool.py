"""BaseTool and ToolRegistry — zero-dependency tool abstraction.

Directly ported from Vibe-Trading's src/agent/tools.py (MIT License).
Only 95 lines. Used by MCP client and agent tool registration.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Minimal tool contract: name, description, JSON Schema parameters,
    and an execute method that returns a JSON string.

    Subclass this for every tool the system exposes to agents.
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    repeatable: bool = False
    is_readonly: bool = True

    @classmethod
    def check_available(cls) -> bool:
        """Override to gate tools on runtime conditions (API keys, etc.)."""
        return True

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Run the tool. Must return a JSON string."""
        ...

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """Central registry for BaseTool instances.

    Auto-discovered by scanning modules; tools register themselves
    via ``__init_subclass__`` or explicit ``register()`` calls.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance. Overwrites on name collision."""
        if not tool.name:
            raise ValueError(f"Tool {tool!r} has no name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Get a tool by name. Raises KeyError if not found."""
        return self._tools[name]

    def list_names(self) -> list[str]:
        """Return sorted list of registered tool names."""
        return sorted(self._tools.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        """Return all tools as OpenAI function-calling schema definitions."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name with given parameters.

        Returns the tool's JSON string output, or an error JSON on failure.
        """
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps(
                {
                    "status": "error",
                    "error": f"tool '{name}' not found",
                },
                ensure_ascii=False,
            )
        try:
            return tool.execute(**params)
        except Exception as exc:
            return json.dumps(
                {
                    "status": "error",
                    "error": f"tool '{name}' failed: {exc}",
                },
                ensure_ascii=False,
            )

    def __len__(self) -> int:
        return len(self._tools)
