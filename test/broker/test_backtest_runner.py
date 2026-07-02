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


class RecordingBacktestAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, ticker: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"ticker": ticker, **kwargs})
        return {"execution_report": "HOLD"}


class ScriptedExecutionAgent:
    def __init__(self, broker: MockBrokerEngine) -> None:
        self._execution_node = create_execution_node(broker)

    def run(
        self,
        ticker: str,
        date: str | None = None,
        current_position_pct: float = 0.0,
        *,
        as_of: str | None = None,
        execution_enabled: bool = False,
        strategy_id: str = "",
        account_id: str = "default",
        session_id: str = "",
    ) -> dict[str, object]:
        del as_of, current_position_pct
        return self._execution_node(
            {
                "ticker": ticker,
                "date": date,
                "Action": "BUY",
                "Target_position_pct": 50.0,
                "PM_report": "Open a half-sized position.",
                "execution_enabled": execution_enabled,
                "strategy_id": strategy_id,
                "account_id": account_id,
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
        as_of: str | None = None,
        execution_enabled: bool = False,
        strategy_id: str = "",
        account_id: str = "default",
        session_id: str = "",
    ) -> dict[str, object]:
        del date, as_of, current_position_pct
        self._calls += 1
        if self._calls == 1:
            return self._execution_node(
                {
                    "ticker": ticker,
                    "Action": "BUY",
                    "Target_position_pct": 50.0,
                    "PM_report": "Open a half-sized position.",
                    "execution_enabled": execution_enabled,
                    "strategy_id": strategy_id,
                    "account_id": account_id,
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


def test_backtest_runner_passes_as_of_to_each_agent_call() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert [call["as_of"] for call in agent.calls] == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert [call["date"] for call in agent.calls] == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]


def test_backtest_runner_builds_scoped_agent_for_each_as_of_boundary() -> None:
    created_as_of: list[str] = []
    agent_calls: list[str] = []

    class ScopedAgent:
        def __init__(self, as_of: str) -> None:
            self._as_of = as_of

        def run(self, ticker: str, **kwargs: object) -> dict[str, object]:
            del ticker
            agent_calls.append(self._as_of)
            assert kwargs["as_of"] == self._as_of
            return {"execution_report": "HOLD"}

    def scoped_agent_factory(as_of: str, broker: MockBrokerEngine) -> ScopedAgent:
        assert isinstance(broker, MockBrokerEngine)
        created_as_of.append(as_of)
        return ScopedAgent(as_of)

    runner = BacktestRunner(
        BrokerConfig(),
        scoped_agent_factory=scoped_agent_factory,
    )
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert created_as_of == [
        "2026-01-02T00:00:00Z",
        "2026-01-03T00:00:00Z",
    ]
    assert agent_calls == created_as_of


def test_backtest_runner_propagates_strategy_and_account_identity() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [{"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0}],
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-02",
        strategy_id="strategy-backtest",
        account_id="account-backtest",
    )

    assert agent.calls[0]["strategy_id"] == "strategy-backtest"
    assert agent.calls[0]["account_id"] == "account-backtest"
    assert result.view.config.strategy_id == "strategy-backtest"
    assert result.view.config.account_id == "account-backtest"
    assert list(result.portfolio["strategy_id"]) == ["strategy-backtest"]
    assert list(result.portfolio["account_id"]) == ["account-backtest"]


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


def test_backtest_runner_returns_completed_backtest_result_view_contract() -> None:
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
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert result.view.status == "completed"
    assert result.view.config.tickers == ["AAPL"]
    assert result.view.config.benchmark_symbol == "SPY"
    assert result.view.summary.cumulative_return_pct == pytest.approx(5.0)
    assert result.view.summary.benchmark_return_pct == pytest.approx(10.0)
    assert result.view.summary.excess_return_pct == pytest.approx(-5.0)
    assert len(result.view.series) == 2
    assert result.view.series[0].strategy_equity == pytest.approx(100_000.0)
    assert result.view.series[0].benchmark_equity == pytest.approx(100_000.0)
    assert result.view.trades[0].order_id == result.trades.loc[0, "order_id"]
    assert result.view.trades[0].side == "buy"


def test_backtest_runner_view_is_scoped_to_current_session_when_runner_is_reused() -> (
    None
):
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
    first_price_df = pd.DataFrame(
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
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    second_price_df = pd.DataFrame(
        [
            {
                "Open": 119.0,
                "High": 121.0,
                "Low": 118.0,
                "Close": 120.0,
            }
        ],
        index=pd.to_datetime(["2026-02-02"]),
    )

    first_result = runner.run(
        ticker="AAPL",
        price_df=first_price_df,
        start_date="2026-01-02",
        end_date="2026-01-03",
    )
    second_result = runner.run(
        ticker="AAPL",
        price_df=second_price_df,
        start_date="2026-02-02",
        end_date="2026-02-02",
    )

    assert len(first_result.view.series) == 2
    assert [point.date for point in second_result.view.series] == ["2026-02-02"]
    assert second_result.view.config.start_date == "2026-02-02"
    assert all(
        trade.session_id != first_result.view.trades[0].session_id
        for trade in second_result.view.trades
    )
