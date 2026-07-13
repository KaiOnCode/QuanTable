from __future__ import annotations

import pytest
from pydantic import ValidationError
from typing import Literal

from agent.backtest_policy import (
    BacktestMode,
    BacktestPolicySnapshot,
    ExecutablePolicy,
    ExperimentalAgentPolicy,
    MomentumPolicy,
    SmaCrossoverPolicy,
    StrategyEligibilityError,
    freeze_backtest_run_spec,
)
from agent.backtest_jobs import BacktestRequest


def _request(**overrides: object) -> BacktestRequest:
    payload: dict[str, object] = {
        "strategy_id": "quant-1",
        "ticker": "AAPL",
        "date_from": "2025-01-02",
        "date_to": "2025-03-31",
        "frequency": "weekly",
        "benchmark": "SPY",
    }
    payload.update(overrides)
    return BacktestRequest.model_validate(payload)


def _quant_strategy(**overrides: object) -> dict[str, object]:
    strategy: dict[str, object] = {
        "id": "quant-1",
        "name": "Momentum",
        "type": "quant",
        "status": "active",
        "tickers": ["AAPL", "MSFT"],
        "quant_strategy_name": "momentum",
        "quant_params": {
            "lookback_bars": 20,
            "entry_threshold": 0.05,
            "exit_threshold": -0.02,
            "target_position_pct": 40,
        },
        "execution_frequency": "monthly",
        "initial_capital": 250_000,
        "max_position_pct": 50,
        "max_drawdown_pct": 20,
        "agent_model": "",
    }
    strategy.update(overrides)
    return strategy


def test_freezes_stable_typed_momentum_policy_and_run_override() -> None:
    first = freeze_backtest_run_spec(_request(), _quant_strategy())
    second = freeze_backtest_run_spec(_request(), _quant_strategy())

    assert first == second
    assert first.mode is BacktestMode.DETERMINISTIC
    assert isinstance(first.policy.policy, MomentumPolicy)
    assert first.policy.policy.target_position_pct == 0.4
    assert first.policy_hash == second.policy_hash
    assert len(first.policy_hash) == 64
    assert first.engine_version == "backtest-engine/v1"
    assert first.strategy_execution_frequency == "monthly"
    assert first.run_frequency == "weekly"
    assert first.broker_config.initial_cash == 250_000
    assert first.broker_config.max_position_pct == 0.5
    assert first.broker_config.allow_short is False
    assert (
        first.model_dump_json()
        == type(first).model_validate_json(first.model_dump_json()).model_dump_json()
    )


def test_freezes_typed_sma_crossover_policy() -> None:
    spec = freeze_backtest_run_spec(
        _request(),
        _quant_strategy(
            quant_strategy_name="sma_crossover",
            quant_params={
                "fast_window": 10,
                "slow_window": 50,
                "target_position_pct": 25,
            },
        ),
    )

    assert isinstance(spec.policy.policy, SmaCrossoverPolicy)
    assert spec.policy.policy.target_position_pct == 0.25
    assert spec.policy.required_lookback_bars == 50


def test_quant_params_cannot_override_canonical_policy_kind() -> None:
    with pytest.raises(StrategyEligibilityError) as caught:
        freeze_backtest_run_spec(
            _request(),
            _quant_strategy(
                quant_params={
                    "kind": "sma_crossover",
                    "fast_window": 10,
                    "slow_window": 50,
                    "target_position_pct": 40,
                }
            ),
        )

    assert caught.value.code == "strategy_config_invalid"
    assert caught.value.http_status == 422


@pytest.mark.parametrize(
    ("mode", "strategy_type", "policy"),
    [
        (
            BacktestMode.DETERMINISTIC,
            "agent",
            ExperimentalAgentPolicy(model="deepseek-chat"),
        ),
        (
            BacktestMode.AGENT_EXPERIMENT,
            "quant",
            MomentumPolicy(
                lookback_bars=20,
                entry_threshold=0.05,
                exit_threshold=-0.02,
                target_position_pct=0.4,
            ),
        ),
    ],
)
def test_backtest_policy_snapshot_rejects_mode_policy_mismatch(
    mode: BacktestMode,
    strategy_type: Literal["quant", "agent"],
    policy: ExecutablePolicy,
) -> None:
    with pytest.raises(ValidationError):
        BacktestPolicySnapshot(mode=mode, strategy_type=strategy_type, policy=policy)


@pytest.mark.parametrize(
    "override",
    [
        {"initial_capital": 10**1000},
        {"max_position_pct": 10**1000},
        {
            "quant_params": {
                "lookback_bars": 20,
                "entry_threshold": 0.05,
                "exit_threshold": -0.02,
                "target_position_pct": 10**1000,
            }
        },
        {
            "quant_params": {
                "lookback_bars": 20,
                "entry_threshold": 10**1000,
                "exit_threshold": -0.02,
                "target_position_pct": 40,
            }
        },
    ],
)
def test_huge_numeric_strategy_values_return_typed_config_error(
    override: dict[str, object],
) -> None:
    with pytest.raises(StrategyEligibilityError) as caught:
        freeze_backtest_run_spec(_request(), _quant_strategy(**override))

    assert caught.value.code == "strategy_config_invalid"
    assert caught.value.http_status == 422


@pytest.mark.parametrize(
    ("strategy", "request_overrides", "code"),
    [
        ({"status": "paused"}, {}, "strategy_inactive"),
        ({"tickers": []}, {}, "strategy_config_invalid"),
        ({"tickers": ["aapl"]}, {}, "strategy_config_invalid"),
        ({}, {"ticker": "TSLA"}, "ticker_not_allowed"),
        ({"initial_capital": 0}, {}, "strategy_config_invalid"),
        ({"initial_capital": float("inf")}, {}, "strategy_config_invalid"),
        ({"max_position_pct": 0}, {}, "strategy_config_invalid"),
        ({"max_position_pct": 101}, {}, "strategy_config_invalid"),
        ({"max_drawdown_pct": float("nan")}, {}, "strategy_config_invalid"),
        (
            {"quant_strategy_name": None, "quant_params": {}},
            {},
            "strategy_not_backtestable",
        ),
        ({"type": "hitl"}, {}, "strategy_type_unsupported"),
        ({"type": "agent"}, {}, "strategy_mode_unsupported"),
    ],
)
def test_deterministic_eligibility_matrix(
    strategy: dict[str, object], request_overrides: dict[str, object], code: str
) -> None:
    with pytest.raises(StrategyEligibilityError) as caught:
        freeze_backtest_run_spec(
            _request(**request_overrides), _quant_strategy(**strategy)
        )

    assert caught.value.code == code
    assert caught.value.http_status == 422


def test_agent_experiment_requires_model_and_provider_capability() -> None:
    request = _request(mode="agent_experiment")
    agent = _quant_strategy(type="agent", quant_strategy_name=None, quant_params={})

    with pytest.raises(StrategyEligibilityError) as missing:
        freeze_backtest_run_spec(request, agent, llm_available=True)
    assert missing.value.code == "agent_model_missing"
    assert missing.value.http_status == 422

    agent["agent_model"] = "deepseek-chat"
    with pytest.raises(StrategyEligibilityError) as unavailable:
        freeze_backtest_run_spec(request, agent, llm_available=False)
    assert unavailable.value.code == "llm_unavailable"
    assert unavailable.value.http_status == 503

    with pytest.raises(StrategyEligibilityError) as unsupported:
        freeze_backtest_run_spec(
            request, agent, llm_available=True, structured_output_supported=False
        )
    assert unsupported.value.code == "provider_capability_unsupported"
    assert unsupported.value.http_status == 503
