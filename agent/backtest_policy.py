from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, NoReturn, Protocol, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from storage.strategy_policy import (
    MomentumPolicy,
    SmaCrossoverPolicy,
    StrategyEligibilityError,
    validate_quant_strategy_definition,
)


class BacktestMode(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT_EXPERIMENT = "agent_experiment"


class ExperimentalAgentPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["agent_experiment"] = "agent_experiment"
    version: Literal["v1"] = "v1"
    model: str = Field(min_length=1)


ExecutablePolicy = Annotated[
    MomentumPolicy | SmaCrossoverPolicy | ExperimentalAgentPolicy,
    Field(discriminator="kind"),
]
type BacktestFrequency = Literal["daily", "weekly", "monthly"]


class BacktestPolicySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: BacktestMode
    strategy_type: Literal["quant", "agent"]
    policy: ExecutablePolicy

    @model_validator(mode="after")
    def validate_mode_policy_pair(self) -> BacktestPolicySnapshot:
        deterministic_policy = isinstance(
            self.policy, MomentumPolicy | SmaCrossoverPolicy
        )
        if self.mode is BacktestMode.DETERMINISTIC:
            if self.strategy_type != "quant" or not deterministic_policy:
                raise ValueError("deterministic mode requires a quant policy")
        elif self.strategy_type != "agent" or deterministic_policy:
            raise ValueError("agent experiment mode requires an agent policy")
        return self

    @property
    def required_lookback_bars(self) -> int:
        match self.policy:
            case MomentumPolicy(lookback_bars=lookback):
                return lookback
            case SmaCrossoverPolicy(slow_window=window):
                return window
            case ExperimentalAgentPolicy():
                return 0
        raise AssertionError("unreachable policy variant")


class FrozenBrokerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    initial_cash: float = Field(gt=0)
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    execution_timing: Literal["next_open"] = "next_open"
    max_position_pct: float = Field(gt=0, le=1)
    allow_short: Literal[False] = False


class BacktestRunSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["backtest-run/v1"] = "backtest-run/v1"
    engine_version: Literal["backtest-engine/v1"] = "backtest-engine/v1"
    strategy_id: str
    strategy_name: str
    strategy_description: str = ""
    strategy_beliefs: tuple[str, ...] = ()
    ticker: str
    date_from: date
    date_to: date
    benchmark: str
    mode: BacktestMode
    strategy_execution_frequency: BacktestFrequency
    run_frequency: BacktestFrequency
    policy: BacktestPolicySnapshot
    strategy_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    broker_config: FrozenBrokerConfig
    max_drawdown_limit_pct: float = Field(gt=0, le=1)
    max_drawdown_limit_enforced: Literal[False] = False

    @property
    def frequency(self) -> BacktestFrequency:
        return self.run_frequency


class BacktestRequestLike(Protocol):
    strategy_id: str
    ticker: str
    date_from: date
    date_to: date
    benchmark: str
    frequency: BacktestFrequency
    mode: BacktestMode


def freeze_backtest_run_spec(
    request: BacktestRequestLike,
    strategy: dict[str, object],
    *,
    llm_available: bool = True,
    structured_output_supported: bool = True,
) -> BacktestRunSpec:
    _validate_common_strategy(request, strategy)
    policy = _freeze_policy(
        request,
        strategy,
        llm_available=llm_available,
        structured_output_supported=structured_output_supported,
    )
    max_position_percent = _finite_percent(strategy, "max_position_pct")
    max_drawdown_percent = _finite_percent(strategy, "max_drawdown_pct")
    initial_capital = _finite_positive(strategy, "initial_capital")
    policy_hash = _canonical_hash(policy.model_dump(mode="json", exclude_none=True))
    execution_frequency = strategy.get("execution_frequency", "daily")
    if execution_frequency not in {"daily", "weekly", "monthly"}:
        _invalid("execution_frequency must be daily, weekly, or monthly")
    return BacktestRunSpec(
        strategy_id=request.strategy_id,
        strategy_name=str(strategy.get("name", "")),
        strategy_description=str(strategy.get("description", "")),
        strategy_beliefs=_strategy_beliefs(strategy),
        ticker=request.ticker,
        date_from=request.date_from,
        date_to=request.date_to,
        benchmark=request.benchmark,
        mode=request.mode,
        strategy_execution_frequency=cast(BacktestFrequency, execution_frequency),
        run_frequency=request.frequency,
        policy=policy,
        strategy_snapshot_hash=_canonical_hash(
            {
                "id": request.strategy_id,
                "name": str(strategy.get("name", "")),
                "description": str(strategy.get("description", "")),
                "beliefs": _strategy_beliefs(strategy),
                "type": strategy.get("type"),
                "status": strategy.get("status"),
                "tickers": strategy.get("tickers"),
                "execution_frequency": execution_frequency,
                "initial_capital": initial_capital,
                "max_position_pct": max_position_percent,
                "max_drawdown_pct": max_drawdown_percent,
                "policy": policy.model_dump(mode="json"),
            }
        ),
        policy_hash=policy_hash,
        broker_config=FrozenBrokerConfig(
            initial_cash=initial_capital,
            max_position_pct=max_position_percent / 100,
        ),
        max_drawdown_limit_pct=max_drawdown_percent / 100,
    )


def _validate_common_strategy(
    request: BacktestRequestLike, strategy: dict[str, object]
) -> None:
    if strategy.get("status") != "active":
        raise StrategyEligibilityError("strategy_inactive", "Strategy must be active")
    tickers = strategy.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        _invalid("tickers must be a non-empty uppercase symbol list")
    ticker_list = cast(list[object], tickers)
    if any(
        not isinstance(item, str) or not item or item != item.upper()
        for item in ticker_list
    ):
        _invalid("tickers must be a non-empty uppercase symbol list")
    if request.ticker not in ticker_list:
        raise StrategyEligibilityError(
            "ticker_not_allowed", "Ticker is not allowed by this Strategy"
        )
    _finite_positive(strategy, "initial_capital")
    _finite_percent(strategy, "max_position_pct")
    _finite_percent(strategy, "max_drawdown_pct")


def _freeze_policy(
    request: BacktestRequestLike,
    strategy: dict[str, object],
    *,
    llm_available: bool,
    structured_output_supported: bool,
) -> BacktestPolicySnapshot:
    strategy_type = strategy.get("type")
    if strategy_type == "hitl":
        raise StrategyEligibilityError(
            "strategy_type_unsupported",
            "HITL Strategies cannot run historical backtests",
        )
    if request.mode is BacktestMode.DETERMINISTIC:
        if strategy_type != "quant":
            raise StrategyEligibilityError(
                "strategy_type_unsupported",
                "Deterministic mode requires a quant Strategy",
            )
        policy = _freeze_deterministic_policy(strategy)
        return BacktestPolicySnapshot(
            mode=request.mode, strategy_type="quant", policy=policy
        )
    if strategy_type != "agent":
        raise StrategyEligibilityError(
            "strategy_type_unsupported",
            "Agent experiment mode requires an agent Strategy",
        )
    model = strategy.get("agent_model")
    if not isinstance(model, str) or not model.strip():
        raise StrategyEligibilityError(
            "agent_model_missing", "Agent experiment requires an agent model"
        )
    if not llm_available:
        raise StrategyEligibilityError(
            "provider_capability_unsupported",
            "LLM provider credentials are not configured",
            http_status=503,
        )
    if not structured_output_supported:
        raise StrategyEligibilityError(
            "provider_capability_unsupported",
            "The configured provider does not support forced structured output",
            http_status=503,
        )
    return BacktestPolicySnapshot(
        mode=request.mode,
        strategy_type="agent",
        policy=ExperimentalAgentPolicy(model=model.strip()),
    )


def _freeze_deterministic_policy(
    strategy: dict[str, object],
) -> MomentumPolicy | SmaCrossoverPolicy:
    return validate_quant_strategy_definition(strategy)


def _finite_positive(strategy: dict[str, object], field: str) -> float:
    value = strategy.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _invalid(f"{field} must be finite and greater than zero")
    try:
        number = float(cast(int | float, value))
    except OverflowError:
        _invalid(f"{field} must be finite and greater than zero")
    if not math.isfinite(number) or number <= 0:
        _invalid(f"{field} must be finite and greater than zero")
    return number


def _strategy_beliefs(strategy: dict[str, object]) -> tuple[str, ...]:
    raw = strategy.get("beliefs", [])
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        _invalid("beliefs must be a list of strings")
    return tuple(cast(list[str], raw))


def _finite_percent(strategy: dict[str, object], field: str) -> float:
    number = _finite_positive(strategy, field)
    if number > 100:
        _invalid(f"{field} must be at most 100 percent")
    return number


def _invalid(message: str) -> NoReturn:
    raise StrategyEligibilityError("strategy_config_invalid", message)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
