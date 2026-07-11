from __future__ import annotations

from math import isfinite

import numpy as np

from dataflow.store import MarketDataStore
from risk.calculations import (
    common_dates,
    concentration,
    correlation,
    simple_returns,
    unavailable_correlation,
)
from risk.exposure import DecisionTargetExposureResolver
from risk.models import (
    ConcentrationResult,
    CorrelationResult,
    DatedReturn,
    DecisionTargetExposure,
    HistoricalWorstDay,
    RiskOverview,
    RiskStatus,
    StressResult,
    UniformMarketShock,
)
from storage.store import ContextStore


class RiskAnalyticsError(ValueError):
    __slots__ = ()


class RiskAnalyticsService:
    MIN_COMMON_DATES = 60
    MAX_LOOKBACK_DAYS = 252

    def __init__(
        self, context_store: ContextStore, market_store: MarketDataStore
    ) -> None:
        self._market_store = market_store
        self._exposure_resolver = DecisionTargetExposureResolver(context_store)

    def overview(self, strategy_id: str, lookback_days: int = 252) -> RiskOverview:
        if not self.MIN_COMMON_DATES <= lookback_days <= self.MAX_LOOKBACK_DAYS:
            raise RiskAnalyticsError("lookback_days must be between 60 and 252")
        exposure = self._exposure_resolver.resolve(strategy_id)
        empty_correlation = unavailable_correlation(tuple(exposure.weights))
        ticker_concentration = concentration(exposure.weights)
        sector_concentration = self._sector_concentration(exposure.weights)
        if exposure.status != RiskStatus.COMPLETE:
            return self._empty_overview(
                exposure,
                correlation=empty_correlation,
                ticker_concentration=ticker_concentration,
                sector_concentration=sector_concentration,
            )

        closes_by_ticker: dict[str, dict[str, float]] = {}
        warnings = list(exposure.warnings)
        for ticker in exposure.weights:
            closes: dict[str, float] = {}
            for row in self._market_store.get_ohlcv(ticker, "0001-01-01", "9999-12-31"):
                close = row.get("close")
                day = row.get("date")
                if (
                    isinstance(day, str)
                    and isinstance(close, int | float)
                    and isfinite(float(close))
                    and float(close) > 0
                ):
                    closes[day] = float(close)
            if not closes:
                warnings.append(f"{ticker}: no valid close history is available.")
            closes_by_ticker[ticker] = closes

        shared_dates = common_dates(closes_by_ticker, lookback_days)
        if len(shared_dates) < self.MIN_COMMON_DATES:
            warnings.append(
                f"At least {self.MIN_COMMON_DATES} common close dates are required; "
                f"found {len(shared_dates)}."
            )
            return self._empty_overview(
                exposure,
                status=RiskStatus.PARTIAL,
                common_dates=shared_dates,
                warnings=tuple(warnings),
                correlation=empty_correlation,
                ticker_concentration=ticker_concentration,
                sector_concentration=sector_concentration,
            )

        ticker_returns = {
            ticker: simple_returns(closes, shared_dates)
            for ticker, closes in closes_by_ticker.items()
        }
        portfolio = np.zeros(len(shared_dates) - 1, dtype=float)
        for ticker, weight in exposure.weights.items():
            portfolio += ticker_returns[ticker] * weight
        return_dates = shared_dates[1:]
        wealth = np.cumprod(1 + portfolio)
        cumulative = wealth - 1
        running_peak = np.maximum.accumulate(
            np.concatenate((np.asarray([1.0]), wealth))
        )[1:]
        drawdown = wealth / running_peak - 1
        var_95 = float(np.quantile(portfolio, 0.05, method="linear"))
        var_99 = float(np.quantile(portfolio, 0.01, method="linear"))
        return RiskOverview(
            status=RiskStatus.COMPLETE,
            strategy_id=strategy_id,
            as_of=shared_dates[-1],
            exposure=exposure,
            observation_count=len(portfolio),
            common_dates=shared_dates,
            portfolio_returns=tuple(float(value) for value in portfolio),
            cumulative_curve=tuple(
                DatedReturn(date=day, value=float(value))
                for day, value in zip(return_dates, cumulative, strict=True)
            ),
            drawdown_curve=tuple(
                DatedReturn(date=day, value=float(value))
                for day, value in zip(return_dates, drawdown, strict=True)
            ),
            var_95=var_95,
            var_99=var_99,
            cvar_95=float(portfolio[portfolio <= var_95].mean()),
            max_drawdown=float(drawdown.min()),
            correlation=correlation(ticker_returns),
            ticker_concentration=ticker_concentration,
            sector_concentration=sector_concentration,
            warnings=tuple(warnings),
        )

    def stress(
        self,
        strategy_id: str,
        *,
        uniform_market_shock: float,
        lookback_days: int = 252,
    ) -> StressResult:
        if not isfinite(uniform_market_shock) or not -1 <= uniform_market_shock <= 1:
            raise RiskAnalyticsError("uniform_market_shock must be between -1 and 1")
        overview = self.overview(strategy_id, lookback_days)
        if overview.portfolio_returns:
            worst_index = int(np.argmin(np.asarray(overview.portfolio_returns)))
            worst = HistoricalWorstDay(
                date=overview.common_dates[worst_index + 1],
                impact=overview.portfolio_returns[worst_index],
            )
        else:
            worst = HistoricalWorstDay(date=None, impact=None)
        gross = overview.exposure.gross_exposure
        impact = uniform_market_shock * gross if gross is not None else None
        return StressResult(
            status=overview.status,
            strategy_id=strategy_id,
            as_of=overview.as_of,
            decision_ids=overview.exposure.decision_ids,
            historical_worst_day=worst,
            uniform_market_shock=UniformMarketShock(
                shock=uniform_market_shock,
                gross_exposure=gross,
                impact=impact,
            ),
            warnings=overview.warnings,
        )

    def _sector_concentration(self, weights: dict[str, float]) -> ConcentrationResult:
        sectors: dict[str, float] = {}
        for ticker, weight in weights.items():
            metadata = self._market_store.get_ticker_meta(ticker)
            raw_sector = metadata.get("sector") if metadata else None
            sector = (
                raw_sector.strip()
                if isinstance(raw_sector, str) and raw_sector.strip()
                else "Unknown"
            )
            sectors[sector] = sectors.get(sector, 0) + weight
        return concentration(sectors)

    @staticmethod
    def _empty_overview(
        exposure: DecisionTargetExposure,
        *,
        status: RiskStatus | None = None,
        common_dates: tuple[str, ...] = (),
        warnings: tuple[str, ...] | None = None,
        correlation: CorrelationResult,
        ticker_concentration: ConcentrationResult,
        sector_concentration: ConcentrationResult,
    ) -> RiskOverview:
        return RiskOverview(
            status=status if status is not None else exposure.status,
            strategy_id=exposure.strategy_id,
            as_of=common_dates[-1] if common_dates else exposure.as_of,
            exposure=exposure,
            observation_count=0,
            common_dates=common_dates,
            portfolio_returns=(),
            cumulative_curve=(),
            drawdown_curve=(),
            var_95=None,
            var_99=None,
            cvar_95=None,
            max_drawdown=None,
            correlation=correlation,
            ticker_concentration=ticker_concentration,
            sector_concentration=sector_concentration,
            warnings=warnings if warnings is not None else exposure.warnings,
        )
