from __future__ import annotations

from datetime import date

import pandas as pd

from agent.backtest_jobs import (
    BacktestRequest,
    _canonical_economic_result_hash,
    _canonical_input_snapshot,
)
from agent.backtest_policy import BacktestRunSpec, freeze_backtest_run_spec
from broker.views import (
    BacktestConfigView,
    BacktestResultView,
    BacktestSeriesPointView,
    PerformanceMetricsView,
)


def _frozen_spec(entry_threshold: float) -> BacktestRunSpec:
    request = BacktestRequest(
        strategy_id="strategy-a",
        ticker="AAPL",
        date_from=date(2024, 1, 2),
        date_to=date(2024, 1, 5),
        frequency="daily",
        benchmark="SPY",
    )
    return freeze_backtest_run_spec(
        request,
        {
            "id": "strategy-a",
            "name": "Frozen Momentum",
            "type": "quant",
            "status": "active",
            "tickers": ["AAPL"],
            "quant_strategy_name": "momentum",
            "quant_params": {
                "lookback_bars": 2,
                "entry_threshold": entry_threshold,
                "exit_threshold": -0.01,
                "target_position_pct": 80,
            },
            "execution_frequency": "daily",
            "initial_capital": 100_000,
            "max_position_pct": 80,
            "max_drawdown_pct": 20,
        },
    )


def _completed_result(spec: BacktestRunSpec) -> BacktestResultView:
    return BacktestResultView(
        config=BacktestConfigView(
            ticker=spec.ticker,
            start_date=spec.date_from.isoformat(),
            end_date=spec.date_to.isoformat(),
            frequency=spec.frequency,
            benchmark_symbol=spec.benchmark,
            initial_capital=spec.broker_config.initial_cash,
            commission_rate=spec.broker_config.commission_rate,
            slippage_rate=spec.broker_config.slippage_rate,
            execution_timing=spec.broker_config.execution_timing,
            max_position_pct=spec.broker_config.max_position_pct,
        ),
        summary=PerformanceMetricsView(),
        series=[
            BacktestSeriesPointView(
                date="2024-01-02T00:00:00Z",
                strategy_equity=100_000.0,
                benchmark_equity=100_000.0,
            )
        ],
    )


def _ohlcv(close: float) -> pd.DataFrame:
    return pd.DataFrame(
        [[close - 0.5, close + 0.5, close - 1.0, close, 1_000.0]],
        columns=pd.Index(["Open", "High", "Low", "Close", "Volume"]),
        index=pd.to_datetime(["2024-01-02"], utc=True),
    )


def test_canonical_hash_changes_for_each_economic_input_mutation() -> None:
    # Given: a frozen deterministic run and canonical snapshots that differ by one OHLC field.
    baseline_spec = _frozen_spec(0.01)
    policy_changed_spec = _frozen_spec(0.02)
    baseline_result = _completed_result(baseline_spec)
    target = _ohlcv(100.5)
    benchmark = _ohlcv(400.5)
    baseline_snapshot = _canonical_input_snapshot(target, benchmark)
    changed_target = target.copy()
    changed_target.loc[changed_target.index[0], "Close"] = 100.6
    ohlc_changed_snapshot = _canonical_input_snapshot(changed_target, benchmark)
    cost_changed_result = baseline_result.model_copy(
        update={
            "config": baseline_result.config.model_copy(
                update={"commission_rate": 0.002}
            )
        }
    )
    engine_changed_spec = baseline_spec.model_copy(
        update={"engine_version": "backtest-engine/v2"}
    )
    engine_changed_result = baseline_result.model_copy(
        update={
            "config": baseline_result.config.model_copy(
                update={"engine_version": "backtest-engine/v2"}
            )
        }
    )

    # When: each economic input is independently supplied to the canonical payload.
    baseline_hash = _canonical_economic_result_hash(
        baseline_spec,
        baseline_result,
        data_snapshot_hash=baseline_snapshot.content_hash,
    )
    ohlc_changed_hash = _canonical_economic_result_hash(
        baseline_spec,
        baseline_result,
        data_snapshot_hash=ohlc_changed_snapshot.content_hash,
    )
    policy_changed_hash = _canonical_economic_result_hash(
        policy_changed_spec,
        baseline_result,
        data_snapshot_hash=baseline_snapshot.content_hash,
    )
    cost_changed_hash = _canonical_economic_result_hash(
        baseline_spec,
        cost_changed_result,
        data_snapshot_hash=baseline_snapshot.content_hash,
    )
    engine_changed_hash = _canonical_economic_result_hash(
        engine_changed_spec,
        engine_changed_result,
        data_snapshot_hash=baseline_snapshot.content_hash,
    )

    # Then: each frozen economic mutation changes the result hash.
    assert ohlc_changed_snapshot.content_hash != baseline_snapshot.content_hash
    assert policy_changed_spec.policy_hash != baseline_spec.policy_hash
    assert ohlc_changed_hash != baseline_hash
    assert policy_changed_hash != baseline_hash
    assert cost_changed_hash != baseline_hash
    assert engine_changed_hash != baseline_hash
