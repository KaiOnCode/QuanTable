from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import json
import math
from threading import Event, Lock

import pandas as pd
import pytest

from agentgraph.execution_node import create_execution_node
from broker.backtest_runner import (
    BacktestResult,
    BacktestRunError,
    BacktestRunObserver,
    BacktestRunner,
    BacktestTargetDecision,
)
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderType
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
        self.execution_updates: list[tuple[int, str]] = []

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

    def record_execution(self, sequence: int, execution_date: str) -> None:
        self.execution_updates.append((sequence, execution_date))
        self.decisions[sequence - 1] = self.decisions[sequence - 1].model_copy(
            update={"execution_date": execution_date}
        )


class _WarmupExecutor:
    @property
    def minimum_close_count(self) -> int:
        return 3

    def decide(
        self,
        ticker: str,
        *,
        as_of: str,
        closes: tuple[float, ...],
        current_position_pct: float,
    ) -> BacktestTargetDecision:
        del ticker, as_of, current_position_pct
        return BacktestTargetDecision(
            action="HOLD",
            target_position_pct=0.0,
            confidence=1.0,
            rationale="ready",
            feature_hash=str(len(closes)).zfill(64),
            attempts=1,
        )


class _TargetSequenceExecutor:
    def __init__(self, targets: list[float]) -> None:
        self._targets = iter(targets)

    @property
    def minimum_close_count(self) -> int:
        return 1

    def decide(
        self,
        ticker: str,
        *,
        as_of: str,
        closes: tuple[float, ...],
        current_position_pct: float,
    ) -> BacktestTargetDecision:
        del ticker, as_of, closes, current_position_pct
        target = next(self._targets)
        return BacktestTargetDecision(
            action="HOLD" if target == 0 else "BUY",
            target_position_pct=target,
            confidence=1.0,
            rationale="fixture",
            feature_hash="d" * 64,
            attempts=1,
        )


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


class NakedShortAgent:
    def __init__(self, broker: MockBrokerEngine) -> None:
        self._broker = broker

    def run(
        self,
        ticker: str,
        *,
        strategy_id: str,
        account_id: str,
        session_id: str,
        **_kwargs: object,
    ) -> dict[str, object]:
        self._broker.place_order(
            Order(
                ticker=ticker,
                side=OrderSide.SELL,
                type=OrderType.MARKET,
                qty=10,
                strategy_id=strategy_id,
                account_id=account_id,
                session_id=session_id,
            )
        )
        return {"execution_report": "SELL"}


def _benchmark_prices(price_df: pd.DataFrame) -> pd.DataFrame:
    benchmark = price_df.copy()
    for column in ("Open", "High", "Low", "Close"):
        benchmark[column] = benchmark[column] * 2.0
    return benchmark


@pytest.mark.parametrize(
    ("frequency", "expected_decisions", "first_signal", "last_signal"),
    [
        ("daily", 60, "2024-01-02", "2024-03-27"),
        ("weekly", 12, "2024-01-05", "2024-03-22"),
        ("monthly", 2, "2024-01-31", "2024-02-29"),
    ],
)
def test_2024_nyse_61_session_window_uses_only_executable_period_end_signals(
    frequency: str,
    expected_decisions: int,
    first_signal: str,
    last_signal: str,
) -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    weekdays = pd.bdate_range("2024-01-02", "2024-03-29")
    nyse_holidays = pd.to_datetime(["2024-01-15", "2024-02-19", "2024-03-29"])
    index = weekdays[~weekdays.isin(nyse_holidays)]
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
    assert agent.calls[0]["as_of"] == f"{first_signal}T00:00:00Z"
    assert agent.calls[-1]["as_of"] == f"{last_signal}T00:00:00Z"


def test_backtest_runner_rejects_an_injected_close_bar_broker() -> None:
    close_bar_broker = MockBrokerEngine(BrokerConfig(execution_timing="close_bar"))

    with pytest.raises(BacktestRunError, match="next_open"):
        BacktestRunner(
            BrokerConfig(execution_timing="next_open"),
            broker=close_bar_broker,
            decision_executor=_TargetSequenceExecutor([80.0]),
        )


def test_unfilled_agent_order_keeps_its_original_signal_timestamp() -> None:
    class LimitThenHoldAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker
            self._placed = False

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            if not self._placed:
                self._placed = True
                self._broker.place_order(
                    Order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        type=OrderType.LIMIT,
                        qty=1,
                        limit_price=1.0,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                    )
                )
            return {"execution_report": "HOLD"}

    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=LimitThenHoldAgent(broker))
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.0, 101.0, 102.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-04",
    )

    order = broker.get_orders()[0]
    assert order.created_at.isoformat() == "2024-01-02T00:00:00+00:00"
    assert order.decision_id == "1"
    assert result.view.orders[0].status == "unfilled"
    assert result.view.orders[0].signal_date == "2024-01-02T00:00:00+00:00"


def test_agent_order_with_own_id_uses_signal_time_and_records_execution() -> None:
    class MarketOrderAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker
            self._placed = False

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            if not self._placed:
                self._placed = True
                self._broker.place_order(
                    Order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        qty=1,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                        decision_id="agent-owned-id",
                    )
                )
            return {"execution_report": "BUY"}

    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(config, broker=broker, agent=MarketOrderAgent(broker))
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 109.0],
            "High": [101.0, 110.0],
            "Low": [99.0, 108.0],
            "Close": [100.0, 109.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-03",
        observer=observer,
    )

    order = broker.get_orders()[0]
    assert order.created_at.isoformat() == "2024-01-02T00:00:00+00:00"
    assert order.decision_id == "1"
    assert result.view.orders[0].signal_date == "2024-01-02T00:00:00+00:00"
    assert observer.decisions[0].execution_date == "2024-01-03T00:00:00Z"
    assert [event.timestamp for event in broker.get_event_log()] == [
        datetime(2024, 1, 2, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    ]


def test_agent_limit_rejection_uses_its_historical_signal_clock() -> None:
    class RejectedLimitAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            self._broker.place_order(
                Order(
                    ticker=ticker,
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    qty=100,
                    limit_price=100.0,
                    strategy_id=strategy_id,
                    account_id=account_id,
                    session_id=session_id,
                )
            )
            return {"execution_report": "BUY"}

    config = BrokerConfig(
        initial_cash=1_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
    )
    broker = MockBrokerEngine(config)
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(config, broker=broker, agent=RejectedLimitAgent(broker))
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 99.0],
            "Close": [100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-03",
        observer=observer,
    )

    signal_time = datetime(2024, 1, 2, tzinfo=UTC)
    order = broker.get_orders()[0]
    assert order.updated_at == signal_time
    assert [event.timestamp for event in broker.get_event_log()] == [
        signal_time,
        signal_time,
        signal_time,
    ]
    assert result.view.orders[0].execution_date == "2024-01-02T00:00:00+00:00"
    assert observer.decisions[0].execution_date == "2024-01-02T00:00:00Z"


def test_agent_order_cancellation_uses_its_historical_signal_clock() -> None:
    class CanceledLimitAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            order = self._broker.place_order(
                Order(
                    ticker=ticker,
                    side=OrderSide.BUY,
                    type=OrderType.LIMIT,
                    qty=1,
                    limit_price=1.0,
                    strategy_id=strategy_id,
                    account_id=account_id,
                    session_id=session_id,
                )
            )
            self._broker.cancel_order(order.id, account_id=account_id)
            return {"execution_report": "CANCEL"}

    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(config, broker=broker, agent=CanceledLimitAgent(broker))
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 99.0],
            "Close": [100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-03",
        observer=observer,
    )

    signal_time = datetime(2024, 1, 2, tzinfo=UTC)
    order = broker.get_orders()[0]
    assert order.updated_at == signal_time
    assert [event.timestamp for event in broker.get_event_log()] == [
        signal_time,
        signal_time,
    ]
    assert result.view.orders[0].status == "cancelled"
    assert result.view.orders[0].execution_date == "2024-01-02T00:00:00+00:00"
    assert observer.decisions[0].execution_date == "2024-01-02T00:00:00Z"


def test_agent_cancellation_of_prior_pending_order_records_same_signal_execution() -> (
    None
):
    class CancelPriorLimitAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker
            self._order_id: str | None = None

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            if self._order_id is None:
                order = self._broker.place_order(
                    Order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        type=OrderType.LIMIT,
                        qty=1,
                        limit_price=1.0,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                    )
                )
                self._order_id = order.id
            else:
                self._broker.cancel_order(self._order_id, account_id=account_id)
            return {"execution_report": "CANCEL"}

    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(config, broker=broker, agent=CancelPriorLimitAgent(broker))
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.0],
            "High": [101.0, 101.0, 101.0],
            "Low": [99.0, 99.0, 99.0],
            "Close": [100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-04",
        observer=observer,
    )

    assert result.view.orders[0].status == "cancelled"
    assert result.view.orders[0].execution_date == "2024-01-03T00:00:00+00:00"
    assert observer.decisions[0].execution_date == "2024-01-03T00:00:00Z"


def test_agent_first_terminal_execution_clock_survives_later_order_cancellation() -> (
    None
):
    class MarketThenCancelLimitAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker
            self._call_count = 0
            self._limit_order_id: str | None = None

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            self._call_count += 1
            if self._call_count == 1:
                self._broker.place_order(
                    Order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        qty=1,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                    )
                )
                limit_order = self._broker.place_order(
                    Order(
                        ticker=ticker,
                        side=OrderSide.BUY,
                        type=OrderType.LIMIT,
                        qty=1,
                        limit_price=1.0,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                    )
                )
                self._limit_order_id = limit_order.id
            elif self._call_count == 3:
                assert self._limit_order_id is not None
                self._broker.cancel_order(self._limit_order_id, account_id=account_id)
            return {"execution_report": "ORDERS"}

    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(
        config,
        broker=broker,
        agent=MarketThenCancelLimitAgent(broker),
    )
    price_df = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.0, 100.0],
            "High": [101.0, 101.0, 101.0, 101.0],
            "Low": [99.0, 99.0, 99.0, 99.0],
            "Close": [100.0, 100.0, 100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-05",
        observer=observer,
    )

    cancelled_order = next(
        order for order in result.view.orders if order.status == "cancelled"
    )
    assert cancelled_order.execution_date == "2024-01-04T00:00:00+00:00"
    assert observer.execution_updates == [(1, "2024-01-03T00:00:00Z")]
    assert observer.decisions[0].execution_date == "2024-01-03T00:00:00Z"


@pytest.mark.parametrize(
    ("frequency", "dates", "expected"),
    [
        (
            "weekly",
            ["2024-03-25", "2024-03-26", "2024-03-27", "2024-03-28", "2024-04-01"],
            {pd.Timestamp("2024-03-28")},
        ),
        (
            "monthly",
            ["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"],
            {pd.Timestamp("2024-01-31")},
        ),
    ],
)
def test_period_end_schedule_uses_last_available_session_and_omits_final_partial_period(
    frequency: str, dates: list[str], expected: set[pd.Timestamp]
) -> None:
    runner = BacktestRunner(BrokerConfig(), agent=RecordingBacktestAgent())

    decision_dates, _ = runner._decision_dates(pd.DatetimeIndex(dates), frequency)

    assert decision_dates == expected


def test_signal_fills_at_next_historical_open() -> None:
    price_df = pd.DataFrame(
        [
            {"Open": 90.0, "High": 105.0, "Low": 85.0, "Close": 100.0},
            {"Open": 109.0, "High": 112.0, "Low": 108.0, "Close": 110.0},
            {"Open": 111.0, "High": 113.0, "Low": 110.0, "Close": 112.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    config = BrokerConfig(
        commission_rate=0.0,
        slippage_rate=0.0005,
        execution_timing="next_open",
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=BuyThenHoldAgent(broker))

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-04",
    )
    fill_timestamp = datetime.fromisoformat(str(result.trades.loc[0, "timestamp"]))

    assert result.trades.loc[0, "price"] == pytest.approx(109.0 * 1.0005)
    assert fill_timestamp.isoformat() == "2024-01-03T00:00:00+00:00"


def test_typed_target_is_sized_to_integer_shares_at_next_open() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 125.0, "High": 126.0, "Low": 124.0, "Close": 125.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    config = BrokerConfig(
        initial_cash=100_000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
    )
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(config, decision_executor=_TargetSequenceExecutor([80.0]))

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
        observer=observer,
    )

    expected_price = 125.0 * 1.0005
    expected_shares = math.floor(80_000.0 / expected_price)
    assert result.trades.loc[0, "quantity"] == expected_shares
    assert result.trades.loc[0, "price"] == pytest.approx(expected_price)
    assert runner.broker.get_account().cash >= 0
    assert observer.decisions[0].execution_date == "2024-01-03T00:00:00Z"
    assert result.view.orders[0].signal_date == "2024-01-02T00:00:00+00:00"
    assert result.view.orders[0].execution_date == "2024-01-03T00:00:00+00:00"
    assert result.view.end_position.shares == expected_shares
    assert result.view.end_position.liquidated_at_end is False


def test_unaffordable_typed_target_is_recorded_as_unfilled_order_evidence() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        decision_executor=_TargetSequenceExecutor([80.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
        observer=observer,
    )

    assert result.trades.empty
    assert result.view.orders[0].order_id == "target-intent-1"
    assert result.view.orders[0].status == "unfilled"
    assert result.view.orders[0].reason == "target_not_affordable"
    assert result.view.orders[0].signal_date == "2024-01-02T00:00:00+00:00"
    assert result.view.orders[0].execution_date == "2024-01-03T00:00:00+00:00"
    assert observer.decisions[0].execution_date == "2024-01-03T00:00:00Z"
    assert runner.broker.get_positions() == []
    assert result.view.no_trade_reasons == []


def test_backtest_runner_records_all_hold_as_a_zero_trade_reason() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    runner = BacktestRunner(
        BrokerConfig(commission_rate=0.0, slippage_rate=0.0),
        decision_executor=_TargetSequenceExecutor([0.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.view.outcome == "completed_no_trades"
    assert result.view.summary.number_of_fills == 0
    assert [reason.model_dump() for reason in result.view.no_trade_reasons] == [
        {"code": "all_hold", "count": 1}
    ]


def test_backtest_runner_records_no_signal_window_as_a_zero_trade_reason() -> None:
    prices = pd.DataFrame(
        [{"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0}],
        index=pd.to_datetime(["2024-01-02"]),
    )
    runner = BacktestRunner(BrokerConfig(), agent=RecordingBacktestAgent())

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-02",
    )

    assert result.view.outcome == "completed_no_trades"
    assert [reason.model_dump() for reason in result.view.no_trade_reasons] == [
        {"code": "no_signals", "count": 1}
    ]


def test_unaffordable_target_increase_is_not_silently_treated_as_hold() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
    )
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=2_500.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            max_position_pct=1.0,
        ),
        decision_executor=_TargetSequenceExecutor([80.0, 100.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-04",
        observer=observer,
    )

    assert [order.status for order in result.view.orders] == ["executed", "unfilled"]
    assert result.view.orders[1].order_id == "target-intent-2"
    assert result.view.orders[1].reason == "target_not_affordable"
    assert observer.decisions[1].execution_date == "2024-01-04T00:00:00Z"
    position = runner.broker.get_position("AAPL")
    assert position is not None
    assert position.shares == 2


def test_max_target_at_the_risk_cap_is_not_rejected_after_costs() -> None:
    prices = pd.DataFrame(
        {
            "Open": [180.0, 187.21090309791916],
            "High": [181.0, 189.80157360580037],
            "Low": [179.0, 186.70661676571424],
            "Close": [180.0, 189.4159393310547],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    config = BrokerConfig(
        initial_cash=98_623.44491144689,
        commission_rate=0.001,
        slippage_rate=0.0005,
        max_position_pct=0.8,
    )
    runner = BacktestRunner(config, decision_executor=_TargetSequenceExecutor([80.0]))

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert len(result.trades) == 1
    assert result.view.orders[0].status == "executed"


def test_typed_target_reductions_sell_exact_integer_delta_without_liquidation() -> None:
    prices = pd.DataFrame(
        {
            "Open": [100.0, 100.0, 100.0, 100.0],
            "High": [101.0] * 4,
            "Low": [99.0] * 4,
            "Close": [100.0] * 4,
        },
        index=pd.bdate_range("2024-01-02", periods=4),
    )
    config = BrokerConfig(commission_rate=0.0, slippage_rate=0.0)
    runner = BacktestRunner(
        config, decision_executor=_TargetSequenceExecutor([80.0, 50.0, 0.0])
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-05",
    )

    assert result.trades["side"].tolist() == ["BUY", "SELL", "SELL"]
    assert result.trades["quantity"].tolist() == [800.0, 300.0, 500.0]
    assert runner.broker.get_position("AAPL") is None


def test_next_open_gap_and_cost_oracle_preserves_cash_and_integer_targets() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 125.0, "High": 126.0, "Low": 119.0, "Close": 120.0},
            {"Open": 80.0, "High": 86.0, "Low": 79.0, "Close": 85.0},
            {"Open": 90.0, "High": 91.0, "Low": 89.0, "Close": 90.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        ),
        decision_executor=_TargetSequenceExecutor([80.0, 50.0, 0.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-05",
    )

    assert result.trades["side"].tolist() == ["BUY", "SELL", "SELL"]
    assert result.trades["quantity"].tolist() == [639.0, 195.0, 444.0]
    assert result.trades["price"].tolist() == pytest.approx([125.0625, 79.96, 89.955])
    assert result.trades["fee"].tolist() == pytest.approx(
        [79.9149375, 15.5922, 39.94002]
    )
    assert result.trades["cash_after"].tolist() == pytest.approx(
        [20_005.1475625, 35_581.7553625, 75_481.8353425]
    )
    assert result.trades["equity_after"].tolist() == pytest.approx(
        [99_880.1475625, 71_101.7553625, 75_481.8353425]
    )
    assert result.view.end_position.shares == 0.0


def test_next_open_rejection_is_returned_as_order_evidence() -> None:
    config = BrokerConfig(
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
        max_position_pct=0.4,
        allow_short=False,
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=ScriptedExecutionAgent(broker))
    prices = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 99.0],
            "Close": [100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.trades.empty
    assert result.view.order_count == 1
    assert result.view.orders[0].status == "rejected"
    assert result.view.orders[0].signal_date == "2024-01-02T00:00:00+00:00"
    assert result.view.orders[0].execution_date == "2024-01-03T00:00:00+00:00"


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
    ]
    assert [call["date"] for call in agent.calls] == [
        "2026-01-02T00:00:00Z",
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
    assert len(agent.calls) == 1
    assert [item[0] for item in observer.started] == [1]
    assert [decision.sequence for decision in observer.decisions] == [1]
    assert all(decision.execution_date is None for decision in observer.decisions)
    assert all(decision.policy_hash == "c" * 64 for decision in observer.decisions)
    assert observer.progress[-1].model_dump() == {
        "bars_total": 2,
        "bars_processed": 2,
        "decisions_total": 1,
        "decisions_eligible": 1,
        "decisions_not_ready": 0,
        "decisions_completed": 1,
        "current_decision_date": "2026-01-02T00:00:00Z",
    }


def test_backtest_runner_uses_warmup_for_features_not_performance() -> None:
    observer = RecordingBacktestRunObserver()
    runner = BacktestRunner(BrokerConfig(), decision_executor=_WarmupExecutor())
    history = pd.DataFrame(
        [
            {"Open": 89.0, "High": 91.0, "Low": 88.0, "Close": 90.0},
            {"Open": 90.0, "High": 92.0, "Low": 89.0, "Close": 91.0},
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
        ],
        index=pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-01-05"]),
    )
    evaluation = history.loc["2026-01-02":]

    result = runner.run(
        ticker="AAPL",
        price_df=evaluation,
        benchmark_df=_benchmark_prices(evaluation),
        history_df=history,
        snapshot_benchmark_df=_benchmark_prices(history),
        start_date="2026-01-02",
        end_date="2026-01-05",
        observer=observer,
    )

    assert len(observer.snapshots[0][0]) == 4
    assert [decision.status for decision in observer.decisions] == ["completed"]
    assert len(result.portfolio) == 2


def test_missing_benchmark_bar_does_not_change_target_schedule() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    target = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
            {"Open": 101.0, "High": 103.0, "Low": 100.0, "Close": 102.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )
    benchmark = _benchmark_prices(target).drop(pd.Timestamp("2026-01-05"))

    result = runner.run(
        ticker="AAPL",
        price_df=target,
        benchmark_df=benchmark,
        start_date="2026-01-02",
        end_date="2026-01-06",
    )

    assert len(agent.calls) == 2
    assert len(result.portfolio) == 3


def test_adjusted_series_does_not_dispatch_corporate_action_cash_or_quantity() -> None:
    config = BrokerConfig(execution_timing="next_open")
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=BuyThenHoldAgent(broker))
    prices = pd.DataFrame(
        [
            {
                "Open": 99.0,
                "High": 101.0,
                "Low": 98.0,
                "Close": 100.0,
                "Dividends": 0.0,
                "Stock Splits": 0.0,
            },
            {
                "Open": 100.0,
                "High": 102.0,
                "Low": 99.0,
                "Close": 101.0,
                "Dividends": 5.0,
                "Stock Splits": 2.0,
            },
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2026-01-02",
        end_date="2026-01-05",
    )

    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    position = runner.broker.get_position("AAPL")
    account = runner.broker.get_account()
    assert position is not None
    assert position.shares == pytest.approx(float(trade["quantity"]))
    assert account.cash == pytest.approx(float(trade["cash_after"]))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda frame: frame.set_axis(pd.to_datetime(["2026-01-02", "2026-01-02"])),
            "unique and monotonic",
        ),
        (
            lambda frame: frame.iloc[::-1],
            "unique and monotonic",
        ),
        (
            lambda frame: frame.assign(Volume=[1000.0, -1.0]),
            "volume must not be negative",
        ),
    ],
)
def test_backtest_runner_rejects_invalid_target_frame(
    mutate: Callable[[pd.DataFrame], pd.DataFrame], message: str
) -> None:
    prices = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    invalid = mutate(prices)

    with pytest.raises(BacktestRunError, match=message):
        BacktestRunner(BrokerConfig(), agent=RecordingBacktestAgent()).run(
            ticker="AAPL",
            price_df=invalid,
            benchmark_df=_benchmark_prices(prices),
            start_date="2026-01-02",
            end_date="2026-01-05",
        )


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
    ]
    assert agent_calls == created_as_of


def test_backtest_runner_propagates_strategy_and_account_identity() -> None:
    agent = RecordingBacktestAgent()
    runner = BacktestRunner(BrokerConfig(), agent=agent)
    price_df = pd.DataFrame(
        [
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2026-01-02",
        end_date="2026-01-05",
        strategy_id="strategy-backtest",
        account_id="account-backtest",
    )

    assert agent.calls[0]["strategy_id"] == "strategy-backtest"
    assert agent.calls[0]["account_id"] == "account-backtest"
    assert result.view.config.strategy_id == "strategy-backtest"
    assert result.view.config.account_id == "account-backtest"
    assert list(result.portfolio["strategy_id"]) == [
        "strategy-backtest",
        "strategy-backtest",
    ]
    assert list(result.portfolio["account_id"]) == [
        "account-backtest",
        "account-backtest",
    ]


def test_backtest_runner_returns_structured_trade_and_portfolio_exports() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            execution_timing="next_open",
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            execution_timing="next_open",
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
            },
            {"Open": 109.0, "High": 111.0, "Low": 108.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
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
    assert list(result.portfolio["date"]) == ["2026-01-02", "2026-01-05"]
    assert list(result.portfolio["position_count"]) == [0, 1]
    assert result.metrics["number_of_trades"] == 0


def test_backtest_runner_adds_strategy_and_benchmark_performance_columns() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
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
        101_010.0,
        111_110.0,
        90_910.0,
    ]
    assert list(result.portfolio["strategy_drawdown"]) == [
        0.0,
        0.0,
        pytest.approx(1 - 90_500.0 / 100_500.0),
    ]
    assert list(result.portfolio["benchmark_drawdown"]) == [
        0.0,
        0.0,
        pytest.approx(1 - 90_910.0 / 111_110.0),
    ]


def test_backtest_runner_uses_costed_integer_share_benchmark_with_residual_cash() -> (
    None
):
    config = BrokerConfig(
        initial_cash=1_000.0,
        commission_rate=0.001,
        slippage_rate=0.0005,
        execution_timing="next_open",
    )
    target = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )
    benchmark = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 110.0, "High": 111.0, "Low": 109.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-06"]),
    )
    runner = BacktestRunner(config, agent=RecordingBacktestAgent())

    result = runner.run(
        ticker="AAPL",
        price_df=target,
        benchmark_df=benchmark,
        start_date="2026-01-02",
        end_date="2026-01-06",
    )

    assert [point.benchmark_equity for point in result.view.series] == pytest.approx(
        [998.64955, 998.64955, 1088.64955]
    )
    assert result.view.summary.benchmark_return_pct == pytest.approx(8.864955)
    assert result.view.summary.excess_return_pct == pytest.approx(-8.864955)


def test_winning_closed_trade_has_json_safe_undefined_profit_ratios() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 110.0, "High": 111.0, "Low": 109.0, "Close": 110.0},
            {"Open": 120.0, "High": 121.0, "Low": 119.0, "Close": 120.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]),
    )
    runner = BacktestRunner(
        BrokerConfig(commission_rate=0.0, slippage_rate=0.0),
        decision_executor=_TargetSequenceExecutor([100.0, 0.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2026-01-02",
        end_date="2026-01-06",
    )

    assert len(result.view.closed_trades) == 1
    assert result.view.summary.profit_factor is None
    assert result.view.summary.payoff_ratio is None
    assert json.dumps(result.view.model_dump(mode="json"), allow_nan=False)


@pytest.mark.parametrize(
    ("benchmark", "warning"),
    [
        (
            pd.DataFrame(
                [{"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0}],
                index=pd.to_datetime(["2026-01-02"]),
            ),
            "benchmark_stale_unavailable",
        ),
    ],
)
def test_backtest_runner_marks_unavailable_benchmark_as_null_without_shortening_target(
    benchmark: pd.DataFrame, warning: str
) -> None:
    target_dates = pd.to_datetime(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-12",
        ]
    )
    target = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
        },
        index=target_dates,
    )
    runner = BacktestRunner(BrokerConfig(), agent=RecordingBacktestAgent())

    result = runner.run(
        ticker="AAPL",
        price_df=target,
        benchmark_df=benchmark,
        start_date="2026-01-02",
        end_date="2026-01-12",
    )

    assert [point.date for point in result.view.series] == [
        value.strftime("%Y-%m-%d") for value in target_dates
    ]
    assert result.view.summary.benchmark_return_pct is None
    assert result.view.summary.excess_return_pct is None
    assert warning in result.view.warnings
    if warning == "benchmark_start_unavailable":
        assert all(point.benchmark_equity is None for point in result.view.series)
    else:
        assert result.view.series[-1].benchmark_equity is None


def test_backtest_runner_rejects_zero_overlap_benchmark_without_shrinking_target() -> (
    None
):
    # Given: valid target and benchmark windows have no shared evaluation session.
    target = pd.DataFrame(
        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    benchmark = pd.DataFrame(
        {"Open": 400.0, "High": 401.0, "Low": 399.0, "Close": 400.0},
        index=pd.to_datetime(["2026-01-03", "2026-01-04"]),
    )
    runner = BacktestRunner(BrokerConfig(), agent=RecordingBacktestAgent())

    # When / Then: total non-overlap fails instead of yielding a nullable success.
    with pytest.raises(BacktestRunError, match="overlapping evaluation session"):
        runner.run(
            ticker="AAPL",
            price_df=target,
            benchmark_df=benchmark,
            start_date="2026-01-02",
            end_date="2026-01-05",
        )


def test_backtest_runner_keeps_an_unaffordable_benchmark_entirely_in_cash() -> None:
    target_dates = pd.to_datetime(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-12",
        ]
    )
    target = pd.DataFrame(
        {
            "Open": 100.0,
            "High": 101.0,
            "Low": 99.0,
            "Close": 100.0,
        },
        index=target_dates,
    )
    benchmark = pd.DataFrame(
        [{"Open": 200.0, "High": 201.0, "Low": 199.0, "Close": 200.0}],
        index=pd.to_datetime(["2026-01-02"]),
    )
    runner = BacktestRunner(
        BrokerConfig(initial_cash=100.0, commission_rate=0.0, slippage_rate=0.0),
        agent=RecordingBacktestAgent(),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=target,
        benchmark_df=benchmark,
        start_date="2026-01-02",
        end_date="2026-01-12",
    )

    assert [point.benchmark_equity for point in result.view.series] == pytest.approx(
        [100.0] * len(target_dates)
    )
    assert [
        point.benchmark_drawdown_pct for point in result.view.series
    ] == pytest.approx([0.0] * len(target_dates))
    assert result.view.summary.benchmark_return_pct == pytest.approx(0.0)
    assert result.view.summary.excess_return_pct == pytest.approx(0.0)
    assert "benchmark_stale_unavailable" not in result.view.warnings


def test_backtest_runner_forces_long_only_for_generic_agent_orders() -> None:
    config = BrokerConfig(
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
        allow_short=True,
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=NakedShortAgent(broker))
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2026-01-02",
        end_date="2026-01-05",
    )

    assert result.view.config.allow_short is False
    assert result.view.executions == []
    assert result.view.orders[0].status == "rejected"
    assert result.view.orders[0].reason == "risk_check_failed"
    assert result.view.orders[0].ticker == "AAPL"
    assert result.view.orders[0].side == "SELL"
    assert result.view.orders[0].quantity == 10
    assert result.view.orders[0].order_type == "MARKET"
    assert result.view.orders[0].limit_price is None
    assert broker.get_orders()[0].side is OrderSide.SELL
    assert result.view.end_position.shares == pytest.approx(0.0)


def test_backtest_runner_returns_completed_backtest_result_view_contract() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
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
    assert result.view.summary.cumulative_return_pct == pytest.approx(0.5)
    assert result.view.summary.benchmark_return_pct == pytest.approx(11.11)
    assert result.view.config.risk_free_rate == pytest.approx(0.0)
    assert result.view.config.periods_per_year == 252
    assert result.view.summary.excess_return_pct == pytest.approx(-10.61)
    assert len(result.view.series) == 2
    assert result.view.series[0].strategy_equity == pytest.approx(100_000.0)
    assert result.view.series[0].benchmark_equity == pytest.approx(101_010.0)
    assert result.view.trades[0].order_id == result.trades.loc[0, "order_id"]
    assert result.view.trades[0].side == "buy"


def test_backtest_runner_reused_same_account_does_not_inherit_prior_broker_state() -> (
    None
):
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
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
    assert first_result.view.end_position is not None
    assert [point.date for point in second_result.view.series] == ["2026-02-02"]
    assert second_result.view.config.start_date == "2026-02-02"
    assert second_result.view.summary.number_of_fills == 0
    assert second_result.view.series[0].strategy_equity == pytest.approx(100_000.0)
    assert second_result.metrics["total_return"] == pytest.approx(0.0)
    assert second_result.view.end_position.shares == pytest.approx(0.0)
    assert second_result.view.end_position.market_value == pytest.approx(0.0)
    assert second_result.view.end_position.unrealized_pnl == pytest.approx(0.0)


def test_backtest_runner_uses_run_config_initial_cash_with_injected_broker() -> None:
    runner_config = BrokerConfig(
        initial_cash=100_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
    )
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=50_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    runner = BacktestRunner(
        runner_config,
        broker=broker,
        agent=RecordingBacktestAgent(),
    )
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2026-01-02",
        end_date="2026-01-03",
    )

    assert [point.strategy_equity for point in result.view.series] == pytest.approx(
        [100_000.0, 100_000.0]
    )
    assert result.metrics["total_return"] == pytest.approx(0.0)


def test_backtest_runner_serializes_concurrent_same_account_runs() -> None:
    class ObservableBroker(MockBrokerEngine):
        def __init__(self, config: BrokerConfig) -> None:
            super().__init__(config)
            self.second_reset = Event()
            self._reset_count = 0
            self._reset_lock = Lock()

        def reset_account(self, account_id: str = "default") -> None:
            with self._reset_lock:
                self._reset_count += 1
                if self._reset_count == 2:
                    self.second_reset.set()
            super().reset_account(account_id)

    class BlockingHoldAgent:
        def __init__(self, entered: Event, release: Event) -> None:
            self._entered = entered
            self._release = release
            self._calls = 0
            self._calls_lock = Lock()

        def run(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            with self._calls_lock:
                self._calls += 1
                is_first_decision = self._calls == 1
            if is_first_decision:
                self._entered.set()
                if not self._release.wait(timeout=2):
                    raise AssertionError("first backtest decision was not released")
            return {"execution_report": "HOLD"}

    config = BrokerConfig(
        initial_cash=100_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
    )
    broker = ObservableBroker(config)
    first_agent_call = Event()
    release_first_agent_call = Event()
    runner = BacktestRunner(
        config,
        broker=broker,
        agent=BlockingHoldAgent(first_agent_call, release_first_agent_call),
    )
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
        ],
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )

    def run_once() -> BacktestResult:
        return runner.run(
            ticker="AAPL",
            price_df=prices.copy(),
            benchmark_df=_benchmark_prices(prices),
            start_date="2026-01-02",
            end_date="2026-01-03",
            account_id="shared-account",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(run_once)
        assert first_agent_call.wait(timeout=2)
        second_future = executor.submit(run_once)
        try:
            assert not broker.second_reset.wait(timeout=0.2)
        finally:
            release_first_agent_call.set()
        first_result = first_future.result(timeout=2)
        second_result = second_future.result(timeout=2)

    for result in (first_result, second_result):
        assert result.metrics["total_return"] == pytest.approx(0.0)
        assert [point.strategy_equity for point in result.view.series] == pytest.approx(
            [100_000.0, 100_000.0]
        )
        assert result.view.end_position.shares == pytest.approx(0.0)
    assert broker.get_positions(account_id="shared-account") == []
    assert broker.get_account(account_id="shared-account").equity == pytest.approx(
        100_000.0
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

    assert len(agent.calls) == 1
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


def test_backtest_runner_uses_configured_initial_capital_for_an_entry_only_result() -> (
    None
):
    class EntryOnlyAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            self._broker.place_order(
                Order(
                    ticker=ticker,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    qty=10,
                    strategy_id=strategy_id,
                    account_id=account_id,
                    session_id=session_id,
                )
            )
            return {"execution_report": "BUY"}

    config = BrokerConfig(
        initial_cash=100_000.0,
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=EntryOnlyAgent(broker))
    price_df = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 593.0, "Low": 99.0, "Close": 592.4975},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=_benchmark_prices(price_df),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.metrics["total_return"] == pytest.approx(0.04924975)
    assert result.view.summary.total_return_pct == pytest.approx(4.924975)
    assert len(result.view.executions) == 1
    assert result.view.closed_trades == []
    assert result.metrics["realized_pnl"] == pytest.approx(0.0)
    assert result.metrics["unrealized_pnl"] == pytest.approx(4_924.975)


def test_backtest_runner_exposes_all_in_open_episode_end_position() -> None:
    class OpenEpisodeAgent:
        def __init__(self, broker: MockBrokerEngine) -> None:
            self._broker = broker
            self._calls = 0

        def run(
            self,
            ticker: str,
            *,
            strategy_id: str,
            account_id: str,
            session_id: str,
            **_kwargs: object,
        ) -> dict[str, object]:
            self._calls += 1
            if self._calls == 1:
                side = OrderSide.BUY
                quantity = 10
            elif self._calls == 2:
                side = OrderSide.BUY
                quantity = 10
            else:
                side = OrderSide.SELL
                quantity = 5
            self._broker.place_order(
                Order(
                    ticker=ticker,
                    side=side,
                    type=OrderType.MARKET,
                    qty=quantity,
                    strategy_id=strategy_id,
                    account_id=account_id,
                    session_id=session_id,
                )
            )
            return {"execution_report": side.value}

    config = BrokerConfig(
        initial_cash=100_000.0,
        commission_rate=0.01,
        slippage_rate=0.0,
        execution_timing="next_open",
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=OpenEpisodeAgent(broker))
    prices = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0},
            {"Open": 110.0, "High": 111.0, "Low": 109.0, "Close": 110.0},
            {"Open": 120.0, "High": 121.0, "Low": 109.0, "Close": 110.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-05",
    )

    assert result.trades["order_id"].tolist() == result.executions["order_id"].tolist()
    assert len(result.view.trades) == 3
    assert len(result.view.executions) == 3
    assert result.closed_trades.empty
    assert result.view.closed_trades == []
    assert result.view.end_position.shares == pytest.approx(15.0)
    end_position = result.view.end_position.model_dump()
    assert end_position["average_cost_basis"] == pytest.approx(106.05)
    assert end_position["unrealized_pnl"] == pytest.approx(59.25)


def test_backtest_runner_summary_counts_actual_rejection_without_fills() -> None:
    config = BrokerConfig(
        commission_rate=0.0,
        slippage_rate=0.0,
        execution_timing="next_open",
        max_position_pct=0.4,
        allow_short=False,
    )
    broker = MockBrokerEngine(config)
    runner = BacktestRunner(config, broker=broker, agent=ScriptedExecutionAgent(broker))
    prices = pd.DataFrame(
        {
            "Open": [100.0, 100.0],
            "High": [101.0, 101.0],
            "Low": [99.0, 99.0],
            "Close": [100.0, 100.0],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.trades.empty
    assert result.executions.empty
    assert result.closed_trades.empty
    assert result.view.trades == []
    assert result.view.executions == []
    assert result.view.closed_trades == []
    assert [order.order_id for order in result.view.orders] == [
        runner.broker.get_orders()[0].id
    ]
    summary = result.view.summary.model_dump()
    assert summary["number_of_orders"] == 1
    assert summary["number_of_rejections"] == 1
    assert summary["number_of_fills"] == 0
    assert [reason.model_dump() for reason in result.view.no_trade_reasons] == [
        {"code": "all_rejected", "count": 1}
    ]


def test_backtest_runner_does_not_count_unaffordable_target_intent_as_order() -> None:
    prices = pd.DataFrame(
        [
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
            {"Open": 1_000.0, "High": 1_001.0, "Low": 999.0, "Close": 1_000.0},
        ],
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        decision_executor=_TargetSequenceExecutor([80.0]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=prices,
        benchmark_df=_benchmark_prices(prices),
        start_date="2024-01-02",
        end_date="2024-01-03",
    )

    assert result.trades.empty
    assert result.executions.empty
    assert result.closed_trades.empty
    assert result.view.trades == []
    assert result.view.executions == []
    assert result.view.closed_trades == []
    assert len(result.view.orders) == 1
    intent = result.view.orders[0]
    assert intent.order_id == "target-intent-1"
    assert intent.status == "unfilled"
    assert intent.signal_date == "2024-01-02T00:00:00+00:00"
    assert intent.execution_date == "2024-01-03T00:00:00+00:00"
    assert intent.reason == "target_not_affordable"
    summary = result.view.summary.model_dump()
    assert summary["number_of_orders"] == 0
    assert summary["number_of_rejections"] == 0
    assert summary["number_of_fills"] == 0
