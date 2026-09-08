from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Literal

import pytest

from agent.backtest_policy import (
    BacktestMode,
    BacktestPolicySnapshot,
    BacktestRunSpec,
    ExperimentalAgentPolicy,
    FrozenBrokerConfig,
)
from agent.backtest_policy_executor import (
    BacktestPolicyExecutor,
    BacktestRunDecisionExecutor,
    ExperimentalDecisionAdapter,
    ExperimentalDecisionInput,
    OpenAIStructuredDecisionProvider,
    PointInTimeFeatureSnapshot,
    ProviderPermanentError,
    ProviderTransientError,
    derive_position_transition,
)
from agent import backtest_jobs
from agent.backtest_jobs import _canonical_economic_result_hash
from storage.strategy_policy import MomentumPolicy, SmaCrossoverPolicy
from broker.backtest_runner import BacktestRunner
from broker.config import BrokerConfig
from broker.views import (
    BacktestConfigView,
    BacktestResultView,
    ClosedTradeView,
    PerformanceMetricsView,
    TradeView,
)
import pandas as pd


def test_deterministic_momentum_and_sma_use_only_point_in_time_closes() -> None:
    features = PointInTimeFeatureSnapshot(
        ticker="AAPL",
        as_of="2026-01-05T00:00:00Z",
        closes=(100.0, 105.0, 110.0),
    )
    momentum = BacktestPolicySnapshot(
        mode=BacktestMode.DETERMINISTIC,
        strategy_type="quant",
        policy=MomentumPolicy(
            lookback_bars=2,
            entry_threshold=0.09,
            exit_threshold=-0.05,
            target_position_pct=0.8,
        ),
    )
    sma = BacktestPolicySnapshot(
        mode=BacktestMode.DETERMINISTIC,
        strategy_type="quant",
        policy=SmaCrossoverPolicy(
            fast_window=2, slow_window=3, target_position_pct=0.5
        ),
    )

    momentum_decision = BacktestPolicyExecutor(momentum).decide(
        features, current_position_pct=0.0
    )
    sma_decision = BacktestPolicyExecutor(sma).decide(
        features, current_position_pct=0.0
    )

    assert momentum_decision.target_position_pct == 80.0
    assert momentum_decision.action == "BUY"
    assert sma_decision.target_position_pct == 50.0
    assert sma_decision.action == "BUY"
    assert momentum_decision.feature_hash == features.feature_hash
    assert momentum_decision.attempts == 1


@pytest.mark.parametrize(
    ("current", "target", "action", "order_required"),
    [
        (0.0, 80.0, "BUY", True),
        (80.0, 50.0, "SELL", True),
        (50.0, 0.0, "SELL", True),
        (50.0, 50.0, "HOLD", False),
    ],
)
def test_long_only_position_transitions_are_derived_from_target_delta(
    current: float, target: float, action: str, order_required: bool
) -> None:
    transition = derive_position_transition(current, target, max_position_pct=80.0)
    assert transition.action == action
    assert transition.order_required is order_required
    assert transition.delta_position_pct == pytest.approx(target - current)


def test_position_transition_rejects_short_or_over_limit_targets() -> None:
    with pytest.raises(ValueError, match="long-only"):
        derive_position_transition(20.0, -1.0, max_position_pct=80.0)
    with pytest.raises(ValueError, match="maximum"):
        derive_position_transition(20.0, 81.0, max_position_pct=80.0)


@pytest.mark.parametrize(
    ("evaluation_bar_count", "closed_trade_count", "expected"),
    [
        (
            62,
            29,
            [
                "insufficient_evaluation_bars_lt_63",
                "insufficient_evaluation_bars_lt_252",
                "insufficient_closed_trades_lt_30",
            ],
        ),
        (63, 30, ["insufficient_evaluation_bars_lt_252"]),
        (
            251,
            29,
            [
                "insufficient_evaluation_bars_lt_252",
                "insufficient_closed_trades_lt_30",
            ],
        ),
        (252, 30, []),
    ],
)
def test_sample_size_warnings_use_strict_declared_thresholds(
    evaluation_bar_count: int, closed_trade_count: int, expected: list[str]
) -> None:
    assert (
        backtest_jobs._sample_size_warnings(
            evaluation_bar_count=evaluation_bar_count,
            closed_trade_count=closed_trade_count,
        )
        == expected
    )


def test_momentum_hold_band_keeps_the_declared_target() -> None:
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.DETERMINISTIC,
        strategy_type="quant",
        policy=MomentumPolicy(
            lookback_bars=2,
            entry_threshold=0.10,
            exit_threshold=-0.10,
            target_position_pct=0.8,
        ),
    )
    features = PointInTimeFeatureSnapshot(
        ticker="AAPL",
        as_of="2026-01-05T00:00:00Z",
        closes=(100.0, 101.0, 101.0),
    )

    decision = BacktestPolicyExecutor(policy).decide(
        features, current_position_pct=80.0
    )

    assert decision.target_position_pct == 80.0
    assert decision.action == "HOLD"


@pytest.mark.parametrize(
    ("actual_position_pct", "expected_action"),
    [
        (69.9, "BUY"),
        (80.0, "HOLD"),
        (80.2, "SELL"),
    ],
)
def test_deterministic_executor_derives_hold_band_action_from_actual_position(
    actual_position_pct: float,
    expected_action: Literal["BUY", "SELL", "HOLD"],
) -> None:
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.DETERMINISTIC,
        strategy_type="quant",
        policy=MomentumPolicy(
            lookback_bars=2,
            entry_threshold=0.10,
            exit_threshold=-0.10,
            target_position_pct=0.8,
        ),
    )
    spec = BacktestRunSpec(
        strategy_id="momentum-drift",
        strategy_name="Momentum",
        ticker="AAPL",
        date_from=date(2026, 1, 2),
        date_to=date(2026, 1, 9),
        benchmark="SPY",
        mode=BacktestMode.DETERMINISTIC,
        strategy_execution_frequency="daily",
        run_frequency="daily",
        policy=policy,
        strategy_snapshot_hash="a" * 64,
        policy_hash="b" * 64,
        broker_config=FrozenBrokerConfig(
            initial_cash=100_000,
            max_position_pct=0.8,
        ),
        max_drawdown_limit_pct=0.2,
    )
    executor = BacktestRunDecisionExecutor(spec)

    entry = executor.decide(
        "AAPL",
        as_of="2026-01-05T00:00:00Z",
        closes=(100.0, 100.0, 120.0),
        current_position_pct=0.0,
    )
    hold = executor.decide(
        "AAPL",
        as_of="2026-01-06T00:00:00Z",
        closes=(100.0, 120.0, 105.0),
        current_position_pct=actual_position_pct,
    )

    assert entry.action == "BUY"
    assert entry.target_position_pct == 80.0
    assert hold.action == expected_action
    assert hold.target_position_pct == 80.0


class _ScriptedProvider:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[tuple[ExperimentalDecisionInput, bool]] = []

    def decide(
        self, decision_input: ExperimentalDecisionInput, *, repair: bool
    ) -> Mapping[str, object]:
        self.calls.append((decision_input, repair))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        assert isinstance(output, dict)
        return output


def test_experimental_decision_retries_transient_and_carries_frozen_strategy() -> None:
    provider = _ScriptedProvider(
        [
            ProviderTransientError("secret provider body"),
            {
                "target_position_pct": 60.0,
                "confidence": 0.75,
                "rationale": "Positive point-in-time momentum.",
            },
        ]
    )
    adapter = ExperimentalDecisionAdapter(provider, sleeper=lambda _seconds: None)
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.AGENT_EXPERIMENT,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model="scripted-model"),
    )
    decision_input = ExperimentalDecisionInput(
        ticker="AAPL",
        features=PointInTimeFeatureSnapshot(
            ticker="AAPL", as_of="2026-01-05T00:00:00Z", closes=(99.0, 101.0)
        ),
        current_position_pct=0.0,
        max_position_pct=80.0,
        strategy_name="Research Agent",
        strategy_description="Use price momentum with conservative sizing.",
        beliefs=("Momentum persists",),
        max_drawdown_limit_pct=10.0,
        model="scripted-model",
        mode="agent_experiment",
    )

    decision = adapter.decide(policy, decision_input)

    assert decision.target_position_pct == 60.0
    assert decision.attempts == 2
    assert [repair for _input, repair in provider.calls] == [False, False]
    assert (
        provider.calls[0][0].strategy_description == decision_input.strategy_description
    )


def test_experimental_transient_exhaustion_preserves_typed_category() -> None:
    provider = _ScriptedProvider(
        [
            ProviderTransientError("private-1"),
            ProviderTransientError("private-2"),
            ProviderTransientError("private-3"),
        ]
    )
    adapter = ExperimentalDecisionAdapter(provider, sleeper=lambda _seconds: None)
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.AGENT_EXPERIMENT,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model="scripted-model"),
    )
    decision_input = ExperimentalDecisionInput(
        ticker="AAPL",
        features=PointInTimeFeatureSnapshot(
            ticker="AAPL", as_of="2026-01-05T00:00:00Z", closes=(100.0,)
        ),
        current_position_pct=0.0,
        max_position_pct=80.0,
        strategy_name="Agent",
        strategy_description="",
        beliefs=(),
        max_drawdown_limit_pct=10.0,
        model="scripted-model",
        mode="agent_experiment",
    )

    with pytest.raises(Exception) as raised:
        adapter.decide(policy, decision_input)

    assert getattr(raised.value, "code") == "decision_transient_exhausted"
    assert getattr(raised.value, "stage") == "transient"
    assert getattr(raised.value, "attempt") == 3
    assert len(provider.calls) == 3


def test_experimental_schema_repair_is_once_then_typed_failure() -> None:
    provider = _ScriptedProvider(
        [
            {"target_position_pct": "invalid"},
            {"target_position_pct": -10, "confidence": 1.0, "rationale": "short"},
        ]
    )
    adapter = ExperimentalDecisionAdapter(provider, sleeper=lambda _seconds: None)
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.AGENT_EXPERIMENT,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model="scripted-model"),
    )
    decision_input = ExperimentalDecisionInput(
        ticker="AAPL",
        features=PointInTimeFeatureSnapshot(
            ticker="AAPL", as_of="2026-01-05T00:00:00Z", closes=(100.0,)
        ),
        current_position_pct=0.0,
        max_position_pct=80.0,
        strategy_name="Agent",
        strategy_description="",
        beliefs=(),
        max_drawdown_limit_pct=10.0,
        model="scripted-model",
        mode="agent_experiment",
    )

    with pytest.raises(Exception) as raised:
        adapter.decide(policy, decision_input)

    assert getattr(raised.value, "code") == "decision_schema_invalid"
    assert getattr(raised.value, "stage") == "structured_output"
    assert getattr(raised.value, "attempt") == 2
    assert [repair for _input, repair in provider.calls] == [False, True]


@pytest.mark.parametrize(
    ("output", "code", "stage"),
    [
        (ProviderPermanentError("private detail"), "provider_failed", "provider"),
        (
            {
                "target_position_pct": 90.0,
                "confidence": 1.0,
                "rationale": "Exceeds frozen risk.",
            },
            "decision_policy_invalid",
            "policy",
        ),
    ],
)
def test_experimental_provider_and_policy_failures_are_typed(
    output: object, code: str, stage: str
) -> None:
    provider = _ScriptedProvider([output])
    adapter = ExperimentalDecisionAdapter(provider, sleeper=lambda _seconds: None)
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.AGENT_EXPERIMENT,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model="scripted-model"),
    )
    decision_input = ExperimentalDecisionInput(
        ticker="AAPL",
        features=PointInTimeFeatureSnapshot(
            ticker="AAPL", as_of="2026-01-05T00:00:00Z", closes=(100.0,)
        ),
        current_position_pct=0.0,
        max_position_pct=80.0,
        strategy_name="Agent",
        strategy_description="",
        beliefs=(),
        max_drawdown_limit_pct=10.0,
        model="scripted-model",
        mode="agent_experiment",
    )

    with pytest.raises(Exception) as raised:
        adapter.decide(policy, decision_input)

    assert getattr(raised.value, "code") == code
    assert getattr(raised.value, "stage") == stage
    assert getattr(raised.value, "attempt") == 1


@pytest.mark.parametrize("choices", [[], "malformed"])
def test_malformed_successful_structured_response_is_typed_provider_failure(
    choices: object,
) -> None:
    class Completions:
        @staticmethod
        def create(**_kwargs: object) -> object:
            return type("Response", (), {"choices": choices})()

    client = type(
        "Client",
        (),
        {"chat": type("Chat", (), {"completions": Completions()})()},
    )()
    provider = OpenAIStructuredDecisionProvider(
        "structured-model", client_factory=lambda: client
    )
    adapter = ExperimentalDecisionAdapter(provider, sleeper=lambda _seconds: None)
    policy = BacktestPolicySnapshot(
        mode=BacktestMode.AGENT_EXPERIMENT,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model="structured-model"),
    )
    decision_input = ExperimentalDecisionInput(
        ticker="AAPL",
        features=PointInTimeFeatureSnapshot(
            ticker="AAPL", as_of="2026-01-05T00:00:00Z", closes=(100.0,)
        ),
        current_position_pct=0.0,
        max_position_pct=80.0,
        strategy_name="Agent",
        strategy_description="",
        beliefs=(),
        max_drawdown_limit_pct=10.0,
        model="structured-model",
        mode="agent_experiment",
    )

    with pytest.raises(Exception) as raised:
        adapter.decide(policy, decision_input)

    assert getattr(raised.value, "code") == "provider_failed"
    assert getattr(raised.value, "stage") == "provider"
    assert getattr(raised.value, "attempt") == 1


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly"])
def test_deterministic_61_bar_run_completes_without_agent_loop(
    frequency: Literal["daily", "weekly", "monthly"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agent.loop.AgentLoop.__init__",
        lambda *_args, **_kwargs: pytest.fail(
            "deterministic run instantiated AgentLoop"
        ),
    )
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
    spec = BacktestRunSpec(
        strategy_id="quant-1",
        strategy_name="Frozen Momentum",
        ticker="AAPL",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 3, 31),
        benchmark="SPY",
        mode=BacktestMode.DETERMINISTIC,
        strategy_execution_frequency="daily",
        run_frequency=frequency,
        policy=policy,
        strategy_snapshot_hash="a" * 64,
        policy_hash="b" * 64,
        broker_config=FrozenBrokerConfig(
            initial_cash=100_000,
            max_position_pct=0.8,
        ),
        max_drawdown_limit_pct=0.2,
    )
    index = pd.bdate_range("2026-01-01", periods=61)
    closes = [100.0 + index for index in range(61)]
    prices = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 1 for value in closes],
            "Low": [value - 1 for value in closes],
            "Close": closes,
            "Volume": 1_000,
        },
        index=index,
    )
    runner = BacktestRunner(
        BrokerConfig(**spec.broker_config.model_dump()),
        decision_executor=BacktestRunDecisionExecutor(spec),
    )

    result = runner.run(
        "AAPL",
        prices,
        str(index[0])[:10],
        str(index[-1])[:10],
        benchmark_df=prices * 2,
        frequency=frequency,
        strategy_id=spec.strategy_id,
        policy_hash=spec.policy_hash,
    )

    assert len(result.portfolio) == 61
    replay_runner = BacktestRunner(
        BrokerConfig(**spec.broker_config.model_dump()),
        decision_executor=BacktestRunDecisionExecutor(spec),
    )
    replay = replay_runner.run(
        "AAPL",
        prices,
        str(index[0])[:10],
        str(index[-1])[:10],
        benchmark_df=prices * 2,
        frequency=frequency,
        strategy_id=spec.strategy_id,
        policy_hash=spec.policy_hash,
    )
    first_hash = _canonical_economic_result_hash(
        spec, result.view, data_snapshot_hash="a" * 64
    )
    assert first_hash == _canonical_economic_result_hash(
        spec, replay.view, data_snapshot_hash="a" * 64
    )
    assert len(first_hash) == 64
    first_trade = TradeView(
        order_id="operation-a",
        timestamp=datetime(2026, 1, 5, tzinfo=UTC),
        ticker="AAPL",
        side="buy",
        quantity=10,
        price=101,
        fee=1,
        slippage=0.5,
        trade_value=1010,
        realized_pnl=0,
        cash_after=98989,
        equity_after=99999,
        shares_after=10,
        avg_cost_after=101.1,
        strategy_id=spec.strategy_id,
        session_id="session-a",
        decision_id="decision-a",
    )
    second_trade = first_trade.model_copy(
        update={
            "order_id": "operation-b",
            "session_id": "session-b",
            "decision_id": "decision-b",
        }
    )
    assert first_trade.order_id != second_trade.order_id
    first_with_execution = result.view.model_copy(update={"executions": [first_trade]})
    second_with_execution = result.view.model_copy(
        update={"executions": [second_trade]}
    )
    assert _canonical_economic_result_hash(
        spec, first_with_execution, data_snapshot_hash="a" * 64
    ) == _canonical_economic_result_hash(
        spec, second_with_execution, data_snapshot_hash="a" * 64
    )
    later_fill = second_trade.model_copy(
        update={"timestamp": datetime(2026, 1, 6, tzinfo=UTC)}
    )
    assert _canonical_economic_result_hash(
        spec, first_with_execution, data_snapshot_hash="a" * 64
    ) != _canonical_economic_result_hash(
        spec,
        result.view.model_copy(update={"executions": [later_fill]}),
        data_snapshot_hash="a" * 64,
    )
    assert _canonical_economic_result_hash(
        spec, result.view, data_snapshot_hash="a" * 64
    ) != _canonical_economic_result_hash(spec, result.view, data_snapshot_hash="b" * 64)


def test_canonical_hash_ignores_execution_closed_trade_and_account_operational_ids() -> (
    None
):
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
    spec = BacktestRunSpec(
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
    execution = TradeView(
        order_id="order-a",
        timestamp=datetime(2024, 1, 3, tzinfo=UTC),
        ticker="AAPL",
        side="sell",
        quantity=15.0,
        price=120.0,
        fee=6.0,
        slippage=0.0,
        trade_value=1_800.0,
        realized_pnl=63.75,
        cash_after=98_473.0,
        equity_after=100_123.0,
        shares_after=15.0,
        avg_cost_after=106.05,
        strategy_id=spec.strategy_id,
        account_id="account-a",
        session_id="session-a",
        decision_id="decision-a",
    )
    closed_trade = ClosedTradeView(
        entry_at=datetime(2024, 1, 2, tzinfo=UTC),
        exit_at=datetime(2024, 1, 5, tzinfo=UTC),
        ticker="AAPL",
        quantity=20.0,
        entry_vwap=105.0,
        exit_vwap=97.5,
        average_cost_basis=106.05,
        net_realized_pnl=-190.5,
        fees=40.5,
        slippage=0.0,
        holding_period_trading_days=3,
        strategy_id=spec.strategy_id,
        account_id="account-a",
        session_id="session-a",
        decision_id="decision-a",
    )
    first = BacktestResultView(
        config=BacktestConfigView(
            ticker=spec.ticker,
            start_date=spec.date_from.isoformat(),
            end_date=spec.date_to.isoformat(),
            strategy_id=spec.strategy_id,
            account_id="account-a",
        ),
        summary=PerformanceMetricsView(
            number_of_fills=1,
            number_of_closed_trades=1,
            realized_pnl_usd=-190.5,
        ),
        trades=[execution],
        executions=[execution],
        closed_trades=[closed_trade],
    )
    changed_identity_execution = execution.model_copy(
        update={
            "order_id": "order-b",
            "account_id": "account-b",
            "session_id": "session-b",
            "decision_id": "decision-b",
        }
    )
    changed_identity_closed_trade = closed_trade.model_copy(
        update={
            "account_id": "account-b",
            "session_id": "session-b",
            "decision_id": "decision-b",
        }
    )
    same_economics = first.model_copy(
        update={
            "config": first.config.model_copy(update={"account_id": "account-b"}),
            "trades": [changed_identity_execution],
            "executions": [changed_identity_execution],
            "closed_trades": [changed_identity_closed_trade],
        }
    )

    assert _canonical_economic_result_hash(
        spec, first, data_snapshot_hash="a" * 64
    ) == _canonical_economic_result_hash(
        spec, same_economics, data_snapshot_hash="a" * 64
    )

    changed_economics = same_economics.model_copy(
        update={
            "executions": [
                changed_identity_execution.model_copy(update={"price": 121.0})
            ]
        }
    )
    assert _canonical_economic_result_hash(
        spec, first, data_snapshot_hash="a" * 64
    ) != _canonical_economic_result_hash(
        spec, changed_economics, data_snapshot_hash="a" * 64
    )

    changed_historical_timestamp = same_economics.model_copy(
        update={
            "executions": [
                changed_identity_execution.model_copy(
                    update={"timestamp": datetime(2024, 1, 4, tzinfo=UTC)}
                )
            ]
        }
    )
    assert _canonical_economic_result_hash(
        spec, first, data_snapshot_hash="a" * 64
    ) != _canonical_economic_result_hash(
        spec, changed_historical_timestamp, data_snapshot_hash="a" * 64
    )
