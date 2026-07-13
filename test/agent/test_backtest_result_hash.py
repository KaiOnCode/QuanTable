from __future__ import annotations

from datetime import UTC, date, datetime

from agent.backtest_jobs import _canonical_economic_result_hash
from agent.backtest_policy import (
    BacktestMode,
    BacktestPolicySnapshot,
    BacktestRunSpec,
    FrozenBrokerConfig,
)
from broker.views import (
    BacktestConfigView,
    BacktestDecisionView,
    BacktestEndPositionView,
    BacktestOrderEvidenceView,
    BacktestProgressView,
    BacktestResultView,
    BacktestSeriesPointView,
    ClosedTradeView,
    PerformanceMetricsView,
    TradeView,
)
from storage.strategy_policy import MomentumPolicy


def _frozen_spec() -> BacktestRunSpec:
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.DETERMINISTIC,
        strategy_type="quant",
        policy=MomentumPolicy(
            lookback_bars=2,
            entry_threshold=0.01,
            exit_threshold=-0.01,
            target_position_pct=0.8,
        ),
    )
    return BacktestRunSpec(
        strategy_id="strategy-a",
        strategy_name="Frozen Momentum",
        ticker="AAPL",
        date_from=date(2024, 1, 2),
        date_to=date(2024, 1, 5),
        benchmark="SPY",
        mode=BacktestMode.DETERMINISTIC,
        strategy_execution_frequency="daily",
        run_frequency="daily",
        policy=policy,
        strategy_snapshot_hash="a" * 64,
        policy_hash="b" * 64,
        broker_config=FrozenBrokerConfig(
            initial_cash=100_000.0,
            max_position_pct=0.8,
        ),
        max_drawdown_limit_pct=0.2,
    )


def _completed_result(spec: BacktestRunSpec) -> BacktestResultView:
    execution = TradeView(
        order_id="order-a",
        timestamp=datetime(2024, 1, 3, tzinfo=UTC),
        ticker=spec.ticker,
        side="buy",
        quantity=10.0,
        price=101.0,
        fee=1.01,
        slippage=0.5,
        trade_value=1_010.0,
        realized_pnl=0.0,
        cash_after=98_988.99,
        equity_after=99_993.99,
        shares_after=10.0,
        avg_cost_after=101.101,
        strategy_id=spec.strategy_id,
        account_id="account-a",
        session_id="session-a",
        decision_id="decision-a",
    )
    return BacktestResultView(
        config=BacktestConfigView(
            ticker=spec.ticker,
            start_date=spec.date_from.isoformat(),
            end_date=spec.date_to.isoformat(),
            benchmark_symbol=spec.benchmark,
            strategy_id=spec.strategy_id,
            account_id="account-a",
            initial_capital=spec.broker_config.initial_cash,
            commission_rate=spec.broker_config.commission_rate,
            slippage_rate=spec.broker_config.slippage_rate,
            execution_timing=spec.broker_config.execution_timing,
            max_position_pct=spec.broker_config.max_position_pct,
            data_snapshot_hash="c" * 64,
        ),
        summary=PerformanceMetricsView(
            number_of_fills=1,
            number_of_closed_trades=1,
            total_fees_usd=1.01,
            total_slippage_usd=0.5,
        ),
        series=[
            BacktestSeriesPointView(
                date="2024-01-02T00:00:00Z",
                strategy_equity=100_000.0,
                benchmark_equity=100_000.0,
            ),
            BacktestSeriesPointView(
                date="2024-01-03T00:00:00Z",
                strategy_equity=99_993.99,
                benchmark_equity=100_001.0,
                strategy_drawdown_pct=-0.00601,
                benchmark_drawdown_pct=0.0,
            ),
        ],
        trades=[execution],
        executions=[execution],
        closed_trades=[
            ClosedTradeView(
                entry_at=datetime(2024, 1, 2, tzinfo=UTC),
                exit_at=datetime(2024, 1, 5, tzinfo=UTC),
                ticker=spec.ticker,
                quantity=10.0,
                entry_vwap=101.0,
                exit_vwap=104.0,
                average_cost_basis=101.101,
                net_realized_pnl=28.99,
                fees=2.05,
                slippage=1.0,
                holding_period_trading_days=3,
                strategy_id=spec.strategy_id,
                account_id="account-a",
                session_id="session-a",
                decision_id="decision-a",
            )
        ],
        warnings=["insufficient_evaluation_bars_lt_63"],
        progress=BacktestProgressView(
            bars_total=4,
            bars_processed=4,
            decisions_total=2,
            decisions_eligible=2,
            decisions_completed=2,
            current_decision_date="2024-01-04T00:00:00Z",
        ),
        decisions=[
            BacktestDecisionView(
                sequence=1,
                signal_date="2024-01-02T00:00:00Z",
                execution_date="2024-01-03T00:00:00Z",
                status="completed",
                attempts=1,
                target_position_pct=80.0,
                confidence=0.9,
                action="BUY",
                rationale="economic threshold crossed",
                feature_hash="d" * 64,
                policy_hash=spec.policy_hash,
            )
        ],
        orders=[
            BacktestOrderEvidenceView(
                order_id="order-a",
                status="executed",
                signal_date="2024-01-02T00:00:00Z",
                execution_date="2024-01-03T00:00:00Z",
                ticker="AAPL",
                side="BUY",
                quantity=10.0,
                order_type="MARKET",
                limit_price=None,
            )
        ],
        end_position=BacktestEndPositionView(ticker=spec.ticker),
    )


def test_canonical_hash_ignores_operational_progress_retry_and_legacy_alias() -> None:
    # Given: a frozen result whose financial evidence remains unchanged.
    spec = _frozen_spec()
    baseline = _completed_result(spec)
    changed_execution = baseline.executions[0].model_copy(
        update={
            "order_id": "order-b",
            "account_id": "account-b",
            "session_id": "session-b",
            "decision_id": "decision-b",
        }
    )
    operationally_changed = baseline.model_copy(
        update={
            "trades": [changed_execution.model_copy(update={"price": 777.0})],
            "executions": [changed_execution],
            "progress": BacktestProgressView(
                bars_total=4,
                bars_processed=1,
                decisions_total=2,
                decisions_eligible=2,
                current_decision_date="2024-01-02T00:00:00Z",
            ),
            "decisions": [baseline.decisions[0].model_copy(update={"attempts": 3})],
            "orders": [baseline.orders[0].model_copy(update={"order_id": "order-b"})],
        }
    )

    # When: only operational state and the redundant legacy alias differ.
    baseline_hash = _canonical_economic_result_hash(
        spec, baseline, data_snapshot_hash="c" * 64
    )
    changed_hash = _canonical_economic_result_hash(
        spec, operationally_changed, data_snapshot_hash="c" * 64
    )

    # Then: the canonical economic hash remains stable.
    assert changed_hash == baseline_hash


def test_canonical_hash_binds_decision_action_and_order_economics_only() -> None:
    # Given: rejected order economics and non-economic evidence can mutate independently.
    spec = _frozen_spec()
    baseline = _completed_result(spec).model_copy(
        update={
            "orders": [
                _completed_result(spec)
                .orders[0]
                .model_copy(
                    update={"status": "rejected", "reason": "risk_check_failed"}
                )
            ]
        }
    )
    baseline_hash = _canonical_economic_result_hash(
        spec, baseline, data_snapshot_hash="c" * 64
    )
    economic_variants = [
        baseline.model_copy(
            update={
                "decisions": [
                    baseline.decisions[0].model_copy(update={"action": "SELL"})
                ]
            }
        ),
        *[
            baseline.model_copy(
                update={
                    "orders": [baseline.orders[0].model_copy(update={field: value})]
                }
            )
            for field, value in (
                ("ticker", "MSFT"),
                ("side", "SELL"),
                ("quantity", 11.0),
                ("order_type", "LIMIT"),
                ("limit_price", 99.0),
            )
        ],
    ]
    evidence_only = baseline.model_copy(
        update={
            "decisions": [
                baseline.decisions[0].model_copy(update={"rationale": "new wording"})
            ],
            "orders": [baseline.orders[0].model_copy(update={"order_id": "order-b"})],
        }
    )

    # When / Then: economics change the commitment; rationale and IDs do not.
    assert all(
        _canonical_economic_result_hash(spec, item, data_snapshot_hash="c" * 64)
        != baseline_hash
        for item in economic_variants
    )
    assert (
        _canonical_economic_result_hash(
            spec, evidence_only, data_snapshot_hash="c" * 64
        )
        == baseline_hash
    )


def test_canonical_hash_binds_each_mutable_frozen_spec_economic() -> None:
    # Given: typed frozen specs that each mutate one economic outside result.config.
    spec = _frozen_spec()
    result = _completed_result(spec)
    baseline_payload = spec.model_dump(mode="json")
    mutated_payloads: list[dict[str, object]] = []
    for field, value in (
        ("ticker", "MSFT"),
        ("date_from", "2024-01-03"),
        ("date_to", "2024-01-06"),
        ("benchmark", "QQQ"),
        ("run_frequency", "weekly"),
        ("max_drawdown_limit_pct", 0.1),
    ):
        payload = {**baseline_payload, field: value}
        mutated_payloads.append(payload)
    for field, value in (
        ("initial_cash", 120_000.0),
        ("commission_rate", 0.002),
        ("slippage_rate", 0.001),
        ("max_position_pct", 0.7),
    ):
        payload = {**baseline_payload}
        payload["broker_config"] = {
            **baseline_payload["broker_config"],
            field: value,
        }
        mutated_payloads.append(payload)
    mode_payload = {**baseline_payload, "mode": "agent_experiment"}
    mode_payload["policy"] = {
        "mode": "agent_experiment",
        "strategy_type": "agent",
        "policy": {
            "kind": "agent_experiment",
            "version": "v1",
            "model": "frozen-model",
        },
    }
    mutated_payloads.append(mode_payload)
    mutated_specs = [BacktestRunSpec.model_validate(item) for item in mutated_payloads]
    mutated_results = [
        result.model_copy(
            update={
                "config": result.config.model_copy(
                    update={
                        "ticker": mutated_spec.ticker,
                        "start_date": mutated_spec.date_from.isoformat(),
                        "end_date": mutated_spec.date_to.isoformat(),
                        "benchmark_symbol": mutated_spec.benchmark,
                        "mode": mutated_spec.mode.value,
                        "run_frequency": mutated_spec.run_frequency,
                        "initial_capital": mutated_spec.broker_config.initial_cash,
                        "commission_rate": (mutated_spec.broker_config.commission_rate),
                        "slippage_rate": mutated_spec.broker_config.slippage_rate,
                        "max_position_pct": (
                            mutated_spec.broker_config.max_position_pct
                        ),
                        "max_drawdown_limit_pct": (mutated_spec.max_drawdown_limit_pct),
                    }
                )
            }
        )
        for mutated_spec in mutated_specs
    ]

    # When: the same result and explicit snapshot are hashed against each frozen spec.
    baseline_hash = _canonical_economic_result_hash(
        spec, result, data_snapshot_hash="c" * 64
    )
    mutated_hashes = [
        _canonical_economic_result_hash(
            mutated_spec,
            mutated_result,
            data_snapshot_hash="c" * 64,
        )
        for mutated_spec, mutated_result in zip(
            mutated_specs, mutated_results, strict=True
        )
    ]

    # Then: every independently typed frozen economic changes the canonical hash.
    assert all(mutated_hash != baseline_hash for mutated_hash in mutated_hashes)


def test_canonical_hash_ignores_explicitly_excluded_identity_and_runtime_fields() -> (
    None
):
    # Given: excluded strategy labels, IDs, aliases, attempts, and runtime UUIDs mutate independently.
    spec = _frozen_spec()
    result = _completed_result(spec)
    baseline_hash = _canonical_economic_result_hash(
        spec, result, data_snapshot_hash="c" * 64
    )
    excluded_variants = [
        (
            spec.model_copy(update={"strategy_id": "strategy-b"}),
            result,
        ),
        (
            spec.model_copy(update={"strategy_name": "Renamed Strategy"}),
            result,
        ),
        (
            spec.model_copy(update={"strategy_execution_frequency": "weekly"}),
            result,
        ),
        (
            spec,
            result.model_copy(
                update={
                    "config": result.config.model_copy(
                        update={
                            "strategy_id": "strategy-b",
                            "account_id": "account-b",
                            "agent_model": "runtime-model",
                            "strategy_execution_frequency": "weekly",
                            "frequency": "weekly",
                            "commission_bps": 999.0,
                            "slippage_bps": 999.0,
                        }
                    )
                }
            ),
        ),
        (
            spec,
            result.model_copy(
                update={
                    "decisions": [
                        result.decisions[0].model_copy(update={"attempts": 9})
                    ],
                    "orders": [
                        result.orders[0].model_copy(update={"order_id": "order-b"})
                    ],
                    "executions": [
                        result.executions[0].model_copy(
                            update={
                                "order_id": "order-b",
                                "strategy_id": "strategy-b",
                                "account_id": "account-b",
                                "session_id": "session-b",
                                "decision_id": "decision-b",
                            }
                        )
                    ],
                    "closed_trades": [
                        result.closed_trades[0].model_copy(
                            update={
                                "strategy_id": "strategy-b",
                                "account_id": "account-b",
                                "session_id": "session-b",
                                "decision_id": "decision-b",
                            }
                        )
                    ],
                }
            ),
        ),
    ]

    # When: each excluded-only variant is hashed with the same economic commitments.
    hashes = [
        _canonical_economic_result_hash(
            variant_spec,
            variant_result,
            data_snapshot_hash="c" * 64,
        )
        for variant_spec, variant_result in excluded_variants
    ]

    # Then: the explicit allowlist keeps every excluded-only mutation hash-stable.
    assert all(candidate == baseline_hash for candidate in hashes)


def test_canonical_hash_binds_required_config_dates_snapshot_and_outputs() -> None:
    # Given: a baseline with independently mutable economic config, history, and outcome values.
    spec = _frozen_spec()
    result = _completed_result(spec)
    baseline_hash = _canonical_economic_result_hash(
        spec, result, data_snapshot_hash="c" * 64
    )
    variants = [
        result.model_copy(
            update={"config": result.config.model_copy(update={"ticker": "MSFT"})}
        ),
        result.model_copy(
            update={
                "config": result.config.model_copy(update={"start_date": "2024-01-03"})
            }
        ),
        result.model_copy(
            update={
                "config": result.config.model_copy(update={"run_frequency": "weekly"})
            }
        ),
        result.model_copy(
            update={
                "config": result.config.model_copy(update={"commission_rate": 0.002})
            }
        ),
        result.model_copy(
            update={
                "decisions": [
                    result.decisions[0].model_copy(
                        update={"signal_date": "2024-01-03T00:00:00Z"}
                    )
                ]
            }
        ),
        result.model_copy(
            update={"summary": result.summary.model_copy(update={"net_pnl_usd": 1.0})}
        ),
    ]

    # When: each economic value or the explicit data commitment changes.
    variant_hashes = [
        _canonical_economic_result_hash(spec, variant, data_snapshot_hash="c" * 64)
        for variant in variants
    ]
    changed_snapshot_hash = _canonical_economic_result_hash(
        spec, result, data_snapshot_hash="e" * 64
    )

    # Then: every required economic mutation changes the canonical result hash.
    assert all(candidate != baseline_hash for candidate in variant_hashes)
    assert changed_snapshot_hash != baseline_hash
