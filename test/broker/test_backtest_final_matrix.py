from __future__ import annotations

from datetime import date
from typing import Literal

import pandas as pd
import pytest

from agent.backtest_jobs import (
    _canonical_economic_result_hash,
    _canonical_input_snapshot,
)
from agent.backtest_policy import (
    BacktestMode,
    BacktestPolicySnapshot,
    BacktestRunSpec,
    FrozenBrokerConfig,
)
from agent.backtest_policy_executor import BacktestRunDecisionExecutor
from broker.backtest_runner import BacktestResult, BacktestRunner
from broker.config import BrokerConfig
from broker.views import BacktestResultView
from storage.strategy_policy import MomentumPolicy


type Frequency = Literal["daily", "weekly", "monthly"]


def _matrix_prices() -> pd.DataFrame:
    index = pd.bdate_range("2022-01-03", "2023-12-29")
    rows: list[dict[str, float]] = []
    for position in range(len(index)):
        phase = position % 80
        close = 100.0 + phase * 2.0 if phase <= 40 else 180.0 - (phase - 40) * 2.0
        rows.append(
            {
                "Open": close - 0.5,
                "High": close + 1.0,
                "Low": close - 1.5,
                "Close": close,
                "Volume": 1_000.0,
            }
        )
    return pd.DataFrame(rows, index=index)


def _spec(frequency: Frequency) -> BacktestRunSpec:
    return BacktestRunSpec(
        strategy_id="final-matrix-strategy",
        strategy_name="Final Matrix Momentum",
        ticker="AAPL",
        date_from=date(2022, 1, 3),
        date_to=date(2023, 12, 29),
        benchmark="SPY",
        mode=BacktestMode.DETERMINISTIC,
        strategy_execution_frequency="daily",
        run_frequency=frequency,
        policy=BacktestPolicySnapshot(
            mode=BacktestMode.DETERMINISTIC,
            strategy_type="quant",
            policy=MomentumPolicy(
                lookback_bars=20,
                entry_threshold=0.05,
                exit_threshold=-0.02,
                target_position_pct=0.5,
            ),
        ),
        strategy_snapshot_hash="a" * 64,
        policy_hash="b" * 64,
        broker_config=FrozenBrokerConfig(
            initial_cash=100_000.0,
            max_position_pct=1.0,
        ),
        max_drawdown_limit_pct=0.2,
    )


def _expected_signal_dates(index: pd.DatetimeIndex, frequency: Frequency) -> list[str]:
    dates = pd.DatetimeIndex(index)
    executable = dates[:-1]
    match frequency:
        case "daily":
            selected = executable
        case "weekly":
            selected = executable[
                [timestamp.weekday() == 4 for timestamp in executable]
            ]
        case "monthly":
            selected = executable[executable.to_period("M") != dates[1:].to_period("M")]
    return [timestamp.strftime("%Y-%m-%dT00:00:00Z") for timestamp in selected]


def _run(spec: BacktestRunSpec, prices: pd.DataFrame) -> BacktestResult:
    runner = BacktestRunner(
        BrokerConfig(**spec.broker_config.model_dump()),
        decision_executor=BacktestRunDecisionExecutor(spec),
    )
    return runner.run(
        spec.ticker,
        prices,
        spec.date_from.isoformat(),
        spec.date_to.isoformat(),
        benchmark_df=prices * 3.0,
        benchmark_symbol=spec.benchmark,
        frequency=spec.run_frequency,
        strategy_id=spec.strategy_id,
        policy_hash=spec.policy_hash,
    )


def _economic_projection(result: BacktestResultView) -> dict[str, object]:
    return {
        "summary": result.summary,
        "series": result.series,
        "decisions": result.decisions,
        "orders": [order.model_dump(exclude={"order_id"}) for order in result.orders],
        "fills": [
            execution.model_dump(
                exclude={
                    "order_id",
                    "strategy_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                }
            )
            for execution in result.executions
        ],
        "closed_trades": [
            closed_trade.model_dump(
                exclude={"strategy_id", "account_id", "session_id", "decision_id"}
            )
            for closed_trade in result.closed_trades
        ],
        "end_position": result.end_position,
        "warnings": result.warnings,
    }


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly"])
def test_two_year_deterministic_matrix_replays_ten_times_with_independent_ids(
    frequency: Frequency,
) -> None:
    prices = _matrix_prices()
    spec = _spec(frequency)
    benchmark = prices * 3.0
    snapshot_hash = _canonical_input_snapshot(prices, benchmark).content_hash

    results = [_run(spec, prices) for _ in range(10)]
    views = [result.view for result in results]
    hashes = [
        _canonical_economic_result_hash(spec, view, data_snapshot_hash=snapshot_hash)
        for view in views
    ]

    assert {view.status for view in views} == {"completed"}
    assert all(view.outcome == "completed" for view in views)
    assert all(
        decision.status in {"completed", "not_ready"} and decision.error_code is None
        for view in views
        for decision in view.decisions
    )
    assert all(view.closed_trades for view in views)
    assert len(set(hashes)) == 1
    assert all(
        _economic_projection(view) == _economic_projection(views[0])
        for view in views[1:]
    )
    assert [decision.signal_date for decision in views[0].decisions] == (
        _expected_signal_dates(pd.DatetimeIndex(prices.index), frequency)
    )

    order_ids = [order.order_id for view in views for order in view.orders]
    fill_order_ids = [fill.order_id for view in views for fill in view.executions]
    session_ids = {fill.session_id for view in views for fill in view.executions}
    assert order_ids and fill_order_ids and session_ids
    assert len(set(order_ids)) == len(order_ids)
    assert len(set(fill_order_ids)) == len(fill_order_ids)
    assert len(session_ids) == len(views)
