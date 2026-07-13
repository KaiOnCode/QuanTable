from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from agentgraph.execution_node import create_execution_node
from broker.backtest_runner import BacktestRunError, BacktestRunObserver, BacktestRunner
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.views import BacktestConfigView, BacktestDecisionView, BacktestProgressView


class StubAgent:
    def run(self, *args, **kwargs):  # pragma: no cover - should stay unused here
        raise AssertionError("empty backtests should not invoke the agent")


class RecordingBacktestAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, ticker: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"ticker": ticker, **kwargs})
        return {"execution_report": "HOLD"}


class RecordingBacktestRunObserver(BacktestRunObserver):
    def __init__(self) -> None:
        self.snapshots: list[tuple[pd.DataFrame, pd.DataFrame]] = []
        self.progress: list[BacktestProgressView] = []
        self.started: list[tuple[int, str, str]] = []
        self.decisions: list[BacktestDecisionView] = []

    def bind_input_snapshot(
        self, target: pd.DataFrame, benchmark: pd.DataFrame
    ) -> None:
        self.snapshots.append((target.copy(), benchmark.copy()))

    def record_progress(self, progress: BacktestProgressView) -> None:
        self.progress.append(progress.model_copy(deep=True))

    def begin_decision(
        self, sequence: int, decision_date: str, policy_hash: str
    ) -> None:
        self.started.append((sequence, decision_date, policy_hash))

    def record_decision(self, decision: BacktestDecisionView) -> None:
        self.decisions.append(decision.model_copy(deep=True))


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


def _benchmark_prices(price_df: pd.DataFrame) -> pd.DataFrame:
    benchmark = price_df.copy()
    for column in ("Open", "High", "Low", "Close"):
        benchmark[column] = benchmark[column] * 2.0
    return benchmark


@pytest.mark.parametrize(
    ("frequency", "expected_decisions"),
    [("daily", 61), ("weekly", 13), ("monthly", 3)],
)
def test_characterizes_current_61_bar_decision_counts(
    frequency: str, expected_decisions: int
) -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    index = pd.bdate_range("2024-01-02", periods=61)
    price_df = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
        },
        index=index,
    )

    runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date=str(index[0])[:10],
        end_date=str(index[-1])[:10],
        frequency=frequency,
    )

    assert len(agent.calls) == expected_decisions


def test_characterizes_current_same_close_fill_and_runtime_timestamp() -> None:
    before_run = datetime.now(timezone.utc)
    price_df = pd.DataFrame(
        [{"Open": 90.0, "High": 105.0, "Low": 85.0, "Close": 100.0}],
        index=pd.to_datetime(["2024-01-02"]),
    )
    runner = BacktestRunner(
        BrokerConfig(commission_rate=0.0, slippage_rate=0.0),
        scoped_agent_factory=lambda _as_of, broker: ScriptedExecutionAgent(broker),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-02",
    )
    after_run = datetime.now(timezone.utc)
    fill_timestamp = datetime.fromisoformat(str(result.trades.loc[0, "timestamp"]))

    assert result.trades.loc[0, "price"] == pytest.approx(100.0)
    assert before_run <= fill_timestamp <= after_run
    assert fill_timestamp.date().isoformat() != "2024-01-02"


def test_backtest_runner_returns_empty_exports_for_an_empty_price_window() -> None:
    runner = BacktestRunner(BrokerConfig(), agent=StubAgent())

    with pytest.raises(BacktestRunError, match="non-empty"):
        runner.run(
            ticker="AAPL",
            price_df=pd.DataFrame(columns=pd.Index(["Open", "High", "Low", "Close"])),
            benchmark_df=pd.DataFrame(
                columns=pd.Index(["Open", "High", "Low", "Close"])
            ),
            start_date="2026-01-01",
            end_date="2026-01-31",
        )


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
        benchmark_df=_benchmark_prices(price_df),
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


def test_backtest_runner_binds_snapshot_before_persisting_decision_progress() -> None:
    # Given: a two-session target/benchmark window and a recorder owned outside the broker.
    agent = RecordingBacktestAgent()
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    prices = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    # When: the runner receives an observer and immutable policy hash.
    runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2026-01-02",
        end_date="2026-01-03",
        policy_hash="c" * 64,
        observer=observer,
    )

    # Then: snapshot capture happens once before both decision records and final progress is exact.
    assert len(observer.snapshots) == 1
    assert len(agent.calls) == 2
    assert [item[0] for item in observer.started] == [1, 2]
    assert [decision.sequence for decision in observer.decisions] == [1, 2]
    assert all(decision.execution_date is None for decision in observer.decisions)
    assert all(decision.policy_hash == "c" * 64 for decision in observer.decisions)
    assert observer.progress[-1].model_dump() == {
        "bars_total": 2,
        "bars_processed": 2,
        "decisions_total": 2,
        "decisions_eligible": 2,
        "decisions_not_ready": 0,
        "decisions_completed": 2,
        "current_decision_date": "2026-01-03T00:00:00Z",
    }


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
        benchmark_df=_benchmark_prices(price_df),
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
        benchmark_df=_benchmark_prices(price_df),
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
        benchmark_df=_benchmark_prices(price_df),
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
        benchmark_df=_benchmark_prices(price_df),
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
        benchmark_df=_benchmark_prices(price_df),
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert result.view.status == "completed"
    assert result.view.config.ticker == "AAPL"
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
        benchmark_df=_benchmark_prices(first_price_df),
        start_date="2026-01-02",
        end_date="2026-01-03",
    )
    second_result = runner.run(
        ticker="AAPL",
        price_df=second_price_df,
        benchmark_df=_benchmark_prices(second_price_df),
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


def test_backtest_runner_rebalances_weekly_but_records_daily_equity() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
            {"Open": 101.0, "High": 103.0, "Low": 100.0, "Close": 102.0},
            {"Open": 102.0, "High": 104.0, "Low": 101.0, "Close": 103.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2026-01-02",
        end_date="2026-01-07",
        frequency="weekly",
    )

    assert len(agent.calls) == 2
    assert len(result.view.series) == 4
    assert result.view.config.frequency == "weekly"


def test_backtest_config_view_frequency_round_trips_as_canonical_json() -> None:
    view = BacktestConfigView(
        ticker="AAPL",
        start_date="2026-01-02",
        end_date="2026-01-03",
        frequency="monthly",
        benchmark_symbol="SPY",
    )

    restored = BacktestConfigView.model_validate_json(view.model_dump_json())

    assert restored == view
