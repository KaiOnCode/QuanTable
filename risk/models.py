from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class RiskStatus(StrEnum):
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    PARTIAL = "partial"
    COMPLETE = "complete"


class DecisionTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    ticker: str
    target_position_pct: float
    weight: float
    created_at: str


class DecisionTargetExposure(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RiskStatus
    source: str = "decision_target"
    strategy_id: str
    as_of: str | None
    decision_ids: tuple[str, ...]
    decisions: tuple[DecisionTarget, ...]
    weights: dict[str, float]
    cash_weight: float | None
    gross_exposure: float | None
    warnings: tuple[str, ...]

    @property
    def metrics_available(self) -> bool:
        return self.status == RiskStatus.COMPLETE and bool(self.weights)


class DatedReturn(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str
    value: float


class CorrelationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RiskStatus
    labels: tuple[str, ...]
    matrix: tuple[tuple[float | None, ...], ...]
    warnings: tuple[str, ...] = ()


class ConcentrationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    weights: dict[str, float]
    herfindahl_index: float
    largest_label: str | None
    largest_weight: float


class RiskOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RiskStatus
    source: str = "decision_target"
    strategy_id: str
    as_of: str | None
    return_unit: str = "decimal"
    exposure: DecisionTargetExposure
    observation_count: int
    common_dates: tuple[str, ...]
    portfolio_returns: tuple[float, ...]
    cumulative_curve: tuple[DatedReturn, ...]
    drawdown_curve: tuple[DatedReturn, ...]
    var_95: float | None
    var_99: float | None
    cvar_95: float | None
    max_drawdown: float | None
    correlation: CorrelationResult
    ticker_concentration: ConcentrationResult
    sector_concentration: ConcentrationResult
    warnings: tuple[str, ...]


class HistoricalWorstDay(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str | None
    impact: float | None
    source: str = "historical_portfolio_returns"


class UniformMarketShock(BaseModel):
    model_config = ConfigDict(frozen=True)

    shock: float
    gross_exposure: float | None
    impact: float | None
    assumption: str = "uniform_market_shock"


class StressResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: RiskStatus
    source: str = "decision_target"
    strategy_id: str
    as_of: str | None
    return_unit: str = "decimal"
    decision_ids: tuple[str, ...]
    historical_worst_day: HistoricalWorstDay
    uniform_market_shock: UniformMarketShock
    warnings: tuple[str, ...]
