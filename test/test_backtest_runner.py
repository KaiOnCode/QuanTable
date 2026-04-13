from __future__ import annotations

import pandas as pd
import pytest

from agentgraph.execution_node import create_execution_node
from broker.backtest_runner import BacktestRunner
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine


class StubAgent:
    def run(self, *args, **kwargs):  # pragma: no cover - should stay unused here
        raise AssertionError("empty backtests should not invoke the agent")


class ScriptedExecutionAgent:
    def __init__(self, broker: MockBrokerEngine) -> None:
        self._execution_node = create_execution_node(broker)

    def run(
        self,
        ticker: str,
        date: str | None = None,
        current_position_pct: float = 0.0,
        *,
        execution_enabled: bool = False,
        session_id: str = "",
    ) -> dict[str, object]:
        del current_position_pct
        return self._execution_node(
            {
                "ticker": ticker,
                "date": date,
                "Action": "BUY",
                "Target_position_pct": 50.0,
                "PM_report": "Open a half-sized position.",
                "execution_enabled": execution_enabled,
                "session_id": session_id,
            }
        )


class BuyThenHoldAgent:
    def __init__(self, broker: MockBrokerEngine) -> None:
        self._execution_node = create_execution_node(broker)
        self._calls = 0

    def run(
        self,
        ticker: str,
        date: str | None = None,
        current_position_pct: float = 0.0,
        *,
        execution_enabled: bool = False,
        session_id: str = "",
    ) -> dict[str, object]:
        del date, current_position_pct
        self._calls += 1
        if self._calls == 1:
            return self._execution_node(
                {
                    "ticker": ticker,
                    "Action": "BUY",
                    "Target_position_pct": 50.0,
                    "PM_report": "Open a half-sized position.",
                    "execution_enabled": execution_enabled,
                    "session_id": session_id,
                }
            )
        return {
            "execution_report": "HOLD — 无需执行",
        }


def test_backtest_runner_returns_empty_exports_for_an_empty_price_window() -> None:
    runner = BacktestRunner(BrokerConfig(), agent=StubAgent())

    result = runner.run(
        ticker="AAPL",
        price_df=pd.DataFrame(columns=pd.Index(["Open", "High", "Low", "Close"])),
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert result.trades.empty
    assert result.portfolio.empty
    assert result.metrics["number_of_trades"] == 0


def test_backtest_runner_returns_structured_trade_and_portfolio_exports() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        ),
        broker=broker,
        agent=ScriptedExecutionAgent(broker),
    )
    price_df = pd.DataFrame(
        [
            {
                "Open": 99.0,
                "High": 101.0,
                "Low": 98.0,
                "Close": 100.0,
            }
        ],
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert list(result.trades["ticker"]) == ["AAPL"]
    assert list(result.trades["side"]) == ["BUY"]
    assert list(result.trades["quantity"]) == [500.0]
    assert list(result.portfolio["date"]) == ["2026-01-02"]
    assert list(result.portfolio["position_count"]) == [1]
    assert result.metrics["number_of_trades"] == 1


def test_backtest_runner_adds_strategy_and_benchmark_performance_columns() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        broker=broker,
        agent=BuyThenHoldAgent(broker),
    )
    price_df = pd.DataFrame(
        [
            {
                "Open": 99.0,
                "High": 101.0,
                "Low": 98.0,
                "Close": 100.0,
            },
            {
                "Open": 109.0,
                "High": 111.0,
                "Low": 108.0,
                "Close": 110.0,
            },
            {
                "Open": 89.0,
                "High": 91.0,
                "Low": 88.0,
                "Close": 90.0,
            },
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03", "2026-01-04"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-04",
    )

    assert list(result.portfolio["close"]) == [100.0, 110.0, 90.0]
    assert list(result.portfolio["benchmark_equity"]) == [
        100_000.0,
        110_000.0,
        90_000.0,
    ]
    assert list(result.portfolio["strategy_drawdown"]) == [
        0.0,
        0.0,
        pytest.approx(1 - 95_000.0 / 105_000.0),
    ]
    assert list(result.portfolio["benchmark_drawdown"]) == [
        0.0,
        0.0,
        pytest.approx(1 - 90_000.0 / 110_000.0),
    ]
