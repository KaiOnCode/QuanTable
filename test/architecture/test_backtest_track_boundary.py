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


def test_shared_strategies_route_does_not_import_active_or_legacy_code() -> None:
    # Given: the SHARED strategy configuration route.
    source = Path("server/routes/strategies.py").read_text(encoding="utf-8")

    # When: direct imports are inspected at the track boundary.
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

    # Then: SHARED strategy configuration cannot load ACTIVE or LEGACY agents.
    forbidden = ("agent", "quick_ask")
    assert not {
        module
        for module in imported_modules
        if module == "agent"
        or module.startswith(tuple(f"{name}." for name in forbidden))
    }, "SHARED strategies route must not import ACTIVE/LEGACY agent code"


def test_production_backtest_job_path_does_not_depend_on_react_adapter() -> None:
    source = Path("agent/backtest_jobs.py").read_text(encoding="utf-8")

    assert "BacktestDecisionAdapter" not in source
    assert "AgentLoop" not in source


def test_route_track_rules_document_typed_backtest_exception() -> None:
    rules = Path("server/routes/_TRACKS.md").read_text(encoding="utf-8")

    assert (
        "ACTIVE interactive routes must use `agentgraph.react_loop.AgentLoop`" in rules
    )
    assert "`/api/agent/backtest*` uses the typed policy executor" in rules
