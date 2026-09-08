from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Annotated, Literal, NoReturn, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_validator,
)


class StrategyEligibilityError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class MomentumPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["momentum"] = "momentum"
    version: Literal["v1"] = "v1"
    lookback_bars: int = Field(ge=2, le=252)
    entry_threshold: float
    exit_threshold: float
    target_position_pct: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_thresholds(self) -> MomentumPolicy:
        if not all(
            math.isfinite(value)
            for value in (self.entry_threshold, self.exit_threshold)
        ):
            raise ValueError("thresholds must be finite")
        if self.exit_threshold > self.entry_threshold:
            raise ValueError("exit_threshold must not exceed entry_threshold")
        return self


class SmaCrossoverPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sma_crossover"] = "sma_crossover"
    version: Literal["v1"] = "v1"
    fast_window: int = Field(ge=2, le=100)
    slow_window: int = Field(ge=3, le=252)
    target_position_pct: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_windows(self) -> SmaCrossoverPolicy:
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must exceed fast_window")
        return self


QuantPolicy = Annotated[
    MomentumPolicy | SmaCrossoverPolicy, Field(discriminator="kind")
]
_QUANT_POLICY_ADAPTER = TypeAdapter(QuantPolicy)


def validate_quant_strategy_definition(
    strategy: Mapping[str, object],
) -> MomentumPolicy | SmaCrossoverPolicy:
    """Parse one stored quant strategy into its executable typed policy."""
    name = strategy.get("quant_strategy_name")
    params = strategy.get("quant_params")
    if name not in {"momentum", "sma_crossover"} or not isinstance(params, dict):
        raise StrategyEligibilityError(
            "strategy_not_backtestable",
            "Quant Strategy requires a supported executable definition",
        )
    if "kind" in params or "version" in params:
        _invalid("Quant Strategy parameters are invalid")
    max_position = _finite_percent(strategy, "max_position_pct") / 100
    normalized = dict(params)
    target = normalized.get("target_position_pct")
    if isinstance(target, bool) or not isinstance(target, (int, float)):
        _invalid("target_position_pct must be a finite percent")
    try:
        target_number = float(cast(int | float, target))
    except OverflowError:
        _invalid("target_position_pct must be a finite percent")
    if not math.isfinite(target_number):
        _invalid("target_position_pct must be a finite percent")
    normalized["target_position_pct"] = target_number / 100
    try:
        policy = _QUANT_POLICY_ADAPTER.validate_python(
            {"kind": name, "version": "v1", **normalized}
        )
    except ValidationError as exc:
        raise StrategyEligibilityError(
            "strategy_config_invalid", "Quant Strategy parameters are invalid"
        ) from exc
    if policy.target_position_pct > max_position:
        _invalid("target_position_pct must not exceed Strategy max_position_pct")
    return policy


def _finite_positive(strategy: Mapping[str, object], field: str) -> float:
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


def _finite_percent(strategy: Mapping[str, object], field: str) -> float:
    number = _finite_positive(strategy, field)
    if number > 100:
        _invalid(f"{field} must be at most 100 percent")
    return number


def _invalid(message: str) -> NoReturn:
    raise StrategyEligibilityError("strategy_config_invalid", message)
