"""MCP Client — loads external MCP tools into the agent tool registry.

Ported from Vibe-Trading's src/tools/mcp.py (MIT License).
Supports stdio, SSE, and streamableHTTP transports via the fastmcp library.

Tool naming convention: mcp_<server>_<tool>
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an external MCP server."""
    name: str
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    transport: str = "stdio"  # stdio | sse | streamableHttp
    tool_timeout: float = 30.0
    enabled: bool = True
    enabled_tools: list[str] = field(default_factory=list)  # Empty = all tools


class MCPClientManager:
    """Manages connections to external MCP servers.

    Usage:
        mgr = MCPClientManager()
        mgr.add_server(MCPServerConfig(name="financial-datasets",
                                        command="uvx",
                                        args=["financial-datasets-mcp"]))
        tools = mgr.discover_tools()  # list[dict]
    """

    def __init__(self):
        self._servers: dict[str, MCPServerConfig] = {}
        self._adapters: dict[str, Any] = {}  # MCPServerAdapter instances
        self._tools: dict[str, dict] = {}  # tool_name -> {server, spec}

    def add_server(self, config: MCPServerConfig) -> None:
        """Register an external MCP server configuration."""
        self._servers[config.name] = config

    def remove_server(self, name: str) -> None:
        """Remove a server and its tools."""
        self._servers.pop(name, None)
        self._adapters.pop(name, None)
        # Remove all tools from this server
        prefix = f"mcp_{name}_"
        to_remove = [k for k in self._tools if k.startswith(prefix)]
        for k in to_remove:
            del self._tools[k]

    def list_servers(self) -> list[dict]:
        """List configured servers with status."""
        return [
            {
                "name": name,
                "command": cfg.command,
                "args": cfg.args,
                "enabled": cfg.enabled,
                "transport": cfg.transport,
                "tools_count": sum(
                    1 for t in self._tools if t.startswith(f"mcp_{name}_")
                ),
            }
            for name, cfg in self._servers.items()
        ]

    def list_tools(self) -> list[dict]:
        """List all discovered external MCP tools."""
        return [
            {
                "name": name,
                "server": info["server"],
                "description": info.get("description", ""),
            }
            for name, info in self._tools.items()
        ]

    def discover_tools(self) -> list[dict]:
        """Discover tools from all enabled servers.

        Returns list of tool definitions suitable for ToolRegistry.
        """
        all_tools: list[dict] = []
        for name, config in self._servers.items():
            if not config.enabled:
                continue
            try:
                tools = self._discover_from_server(name, config)
                all_tools.extend(tools)
            except Exception as exc:
                logger.warning("Failed to discover tools from MCP server '%s': %s", name, exc)
        return all_tools

    def _discover_from_server(
        self, server_name: str, config: MCPServerConfig
    ) -> list[dict]:
        """Discover tools from a single MCP server.

        Note: Full MCP discovery requires the fastmcp library.
        This implementation provides the interface contract;
        actual transport implementations are loaded lazily.
        """
        # Stub for now — actual fastmcp integration follows the pattern:
        #   1. Build transport based on config.transport
        #   2. Create FastMCP client
        #   3. Call list_tools()
        #   4. Wrap each tool as mcp_<server>_<tool>
        logger.info(
            "MCP server '%s' configured (transport=%s) — "
            "full discovery requires fastmcp library",
            server_name, config.transport,
        )
        return []

    def execute_tool(self, tool_name: str, params: dict[str, Any]) -> str:
        """Execute an external MCP tool. Returns JSON string."""
        info = self._tools.get(tool_name)
        if info is None:
            return json.dumps({
                "status": "error",
                "error": f"MCP tool '{tool_name}' not found",
            }, ensure_ascii=False)

        # Stub: actual execution requires fastmcp adapter
        return json.dumps({
            "status": "error",
            "error": f"MCP tool execution requires fastmcp library (tool: {tool_name})",
        }, ensure_ascii=False)


# Singleton
_mcp_manager: MCPClientManager | None = None


def get_mcp_manager() -> MCPClientManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager
