from __future__ import annotations

from agent.loop import AgentConfig, AgentLoop
from agent.tools.registry import ToolRegistry


def test_restricted_registry_exposes_only_declared_tools_in_schema_and_prompt() -> None:
    # Given: a registry restricted to the backtest decision surface.
    allowed = frozenset({"get_price", "submit_backtest_decision"})
    registry = ToolRegistry(allowed_tools=allowed)
    registry.discover()

    # When: schemas and prompt text are built for the restricted loop.
    names = {
        definition["function"]["name"] for definition in registry.get_definitions()
    }
    prompt = AgentLoop(
        config=AgentConfig(allowed_tools=allowed)
    )._build_default_system_prompt(registry, "backtest AAPL")

    # Then: shell, workspace, legacy bridge, and unscoped tools are absent.
    assert names == allowed
    assert "bash" not in prompt
    assert "workspace" not in prompt
    assert "run_analysis" not in prompt


def test_default_registry_remains_unrestricted_for_normal_agent_chat() -> None:
    # Given / When: the ordinary agent has no explicit subset.
    registry = ToolRegistry()
    registry.discover()

    # Then: an ordinary financial capability remains present.
    assert "get_price" in registry.list_tools()
    assert "run_analysis" in registry.list_tools()
