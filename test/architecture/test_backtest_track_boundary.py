from __future__ import annotations

import ast
from pathlib import Path


def test_broker_backtest_modules_do_not_import_active_or_legacy_agents() -> None:
    # Given: the shared broker backtest source tree.
    source_paths = [Path("broker/backtest_runner.py"), Path("broker/backtest_data.py")]

    # When: imports are inspected at the module boundary.
    imported_modules = {
        alias.name
        for source_path in source_paths
        for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for source_path in source_paths
        for node in ast.walk(ast.parse(source_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }

    # Then: shared broker code cannot load active or legacy agent tracks.
    forbidden = ("agentgraph", "quick_ask", "agent")
    assert not {
        module
        for module in imported_modules
        if module == "agent"
        or module.startswith(tuple(f"{name}." for name in forbidden))
    }


def test_shared_server_main_does_not_import_active_route_or_agent_code() -> None:
    # Given: the shared FastAPI application composition module.
    source = Path("server/main.py").read_text(encoding="utf-8")

    # When: its direct imports are inspected.
    imported_modules = {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    # Then: ACTIVE lifecycle ownership remains inside the ACTIVE router.
    assert "server.routes.agent" not in imported_modules
    assert not {
        module
        for module in imported_modules
        if module == "agent" or module.startswith("agent.")
    }
