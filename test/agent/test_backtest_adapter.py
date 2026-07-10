from __future__ import annotations

import json

import pytest

from agent.backtest_adapter import (
    AgentRunResult,
    BacktestDecisionAdapter,
    BacktestDecisionError,
)
from agent.run_context import AgentRunContext, current_agent_run_context
from broker.backtest_data import BacktestDataService
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from dataflow.store import MarketDataStore


class _OneDecisionLoop:
    def __init__(self, result: AgentRunResult) -> None:
        self._result = result
        self.requests: list[dict[str, object]] = []

    def run(self, user_message: str, **kwargs: str | None) -> AgentRunResult:
        self.requests.append({"user_message": user_message, **kwargs})
        return {"messages": self._result.get("messages", [])}


class _FailingLoop:
    def run(self, user_message: str, **kwargs: str | None) -> AgentRunResult:
        del user_message, kwargs
        raise RuntimeError("agent failed")


class _ValueErrorLoop:
    def run(self, user_message: str, **kwargs: str | None) -> AgentRunResult:
        del user_message, kwargs
        raise ValueError("unexpected agent failure")


def _context(tmp_path) -> AgentRunContext:
    store = MarketDataStore(str(tmp_path / "market.db"))
    service = BacktestDataService(as_of="2026-01-02T00:00:00Z", market_store=store)
    return AgentRunContext(
        data_service=service,
        as_of="2026-01-02T00:00:00Z",
        broker=MockBrokerEngine(BrokerConfig()),
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        ticker="AAPL",
    )


def test_backtest_adapter_requires_exactly_one_structured_decision_and_resets_context(
    tmp_path,
) -> None:
    # Given: the active loop returns one validated decision tool result.
    loop = _OneDecisionLoop(
        {
            "messages": [
                {
                    "role": "tool",
                    "name": "submit_backtest_decision",
                    "content": json.dumps(
                        {
                            "status": "ok",
                            "action": "HOLD",
                            "target_position_pct": 0.0,
                            "confidence": 0.5,
                            "rationale": "seeded hold",
                            "execution": "held",
                        }
                    ),
                }
            ]
        }
    )
    adapter = BacktestDecisionAdapter(loop_factory=lambda: loop)

    # When: one decision is requested through its scoped adapter.
    result = adapter.run(
        context=_context(tmp_path),
        ticker="AAPL",
        date="2026-01-02T00:00:00Z",
        as_of="2026-01-02T00:00:00Z",
        current_position_pct=0.0,
        execution_enabled=True,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
    )

    # Then: the result is tool-derived and no context leaks after the call.
    assert result["status"] == "ok"
    assert len(loop.requests) == 1
    assert current_agent_run_context() is None


def test_backtest_adapter_rejects_prose_or_multiple_decision_calls(tmp_path) -> None:
    # Given: the loop makes two decision calls instead of exactly one.
    loop = _OneDecisionLoop(
        {
            "messages": [
                {"role": "tool", "name": "submit_backtest_decision", "content": "{}"},
                {"role": "tool", "name": "submit_backtest_decision", "content": "{}"},
            ]
        }
    )
    adapter = BacktestDecisionAdapter(loop_factory=lambda: loop)

    # When / Then: the job fails rather than guessing from final prose.
    with pytest.raises(BacktestDecisionError, match="exactly one"):
        adapter.run(
            context=_context(tmp_path),
            ticker="AAPL",
            date="2026-01-02T00:00:00Z",
            as_of="2026-01-02T00:00:00Z",
            current_position_pct=0.0,
            execution_enabled=True,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
        )

    assert current_agent_run_context() is None


def test_backtest_adapter_converts_agent_runtime_failure_to_typed_error(
    tmp_path,
) -> None:
    adapter = BacktestDecisionAdapter(loop_factory=_FailingLoop)

    with pytest.raises(BacktestDecisionError, match="agent execution failed"):
        adapter.run(
            context=_context(tmp_path),
            ticker="AAPL",
            date="2026-01-02T00:00:00Z",
            as_of="2026-01-02T00:00:00Z",
            current_position_pct=0.0,
            execution_enabled=True,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
        )

    assert current_agent_run_context() is None


def test_backtest_adapter_converts_value_error_to_typed_error(tmp_path) -> None:
    adapter = BacktestDecisionAdapter(loop_factory=_ValueErrorLoop)

    with pytest.raises(BacktestDecisionError, match="agent execution failed"):
        adapter.run(
            context=_context(tmp_path),
            ticker="AAPL",
            date="2026-01-02T00:00:00Z",
            as_of="2026-01-02T00:00:00Z",
            current_position_pct=0.0,
            execution_enabled=True,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
        )

    assert current_agent_run_context() is None


def test_backtest_adapter_rejects_status_only_success_payload(tmp_path) -> None:
    adapter = BacktestDecisionAdapter(
        loop_factory=lambda: _OneDecisionLoop(
            {
                "messages": [
                    {
                        "role": "tool",
                        "name": "submit_backtest_decision",
                        "content": json.dumps({"status": "ok"}),
                    }
                ]
            }
        )
    )

    with pytest.raises(BacktestDecisionError, match="invalid structured decision"):
        adapter.run(
            context=_context(tmp_path),
            ticker="AAPL",
            date="2026-01-02T00:00:00Z",
            as_of="2026-01-02T00:00:00Z",
            current_position_pct=0.0,
            execution_enabled=True,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
        )
