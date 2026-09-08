from __future__ import annotations

import json

from agent.run_context import (
    AgentRunContext,
    bind_agent_run_context,
    current_agent_run_context,
)
from agent.tools.base import BaseTool, ToolMeta
from agent.tools.executor import StreamingToolExecutor
from agent.tools.registry import ToolRegistry
from broker.backtest_data import BacktestDataService
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from dataflow.store import MarketDataStore


class _ContextEchoTool(BaseTool):
    meta = ToolMeta(
        name="context_echo",
        description="Return the bound point-in-time cutoff.",
        is_readonly=True,
    )

    def execute(self, **unused: str) -> str:
        del unused
        context = current_agent_run_context()
        return self._ok({"as_of": context.as_of if context is not None else None})


def test_streaming_executor_propagates_agent_run_context_to_read_workers(
    tmp_path,
) -> None:
    # Given: a point-in-time context and a read tool executed on the worker pool.
    market_store = MarketDataStore(tmp_path / "market.db")
    context = AgentRunContext(
        data_service=BacktestDataService("2024-01-02T00:00:00Z", market_store),
        as_of="2024-01-02T00:00:00Z",
        broker=MockBrokerEngine(BrokerConfig()),
        strategy_id="strategy-a",
        account_id="default",
        session_id="backtest-a",
        ticker="AAPL",
    )
    registry = ToolRegistry(allowed_tools=frozenset({"context_echo"}))
    registry.register(_ContextEchoTool())
    executor = StreamingToolExecutor(registry, lambda *_args: None)

    # When: the read call crosses the ThreadPoolExecutor boundary.
    with bind_agent_run_context(context):
        executor.submit(0, {"id": "call-1", "name": "context_echo", "args": {}})
        result = executor.get_remaining_results()[0]
    executor.shutdown()

    # Then: the worker retains the exact historical cutoff rather than live fallback.
    assert json.loads(result)["as_of"] == "2024-01-02T00:00:00Z"
