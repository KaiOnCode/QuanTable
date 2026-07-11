from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from dataflow.store import MarketDataStore
from risk.models import RiskStatus
from risk.service import DecisionTargetExposureResolver, RiskAnalyticsService
from storage.store import ContextStore


def _bars(start: date, returns: list[float]) -> list[dict[str, float | str]]:
    close = 100.0
    rows: list[dict[str, float | str]] = [
        {
            "date": start.isoformat(),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1_000.0,
        }
    ]
    for offset, daily_return in enumerate(returns, start=1):
        close *= 1 + daily_return
        rows.append(
            {
                "date": (start + timedelta(days=offset)).isoformat(),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1_000.0,
            }
        )
    return rows


@pytest.fixture
def stores(tmp_path: Path) -> tuple[ContextStore, MarketDataStore]:
    return ContextStore(tmp_path / "context"), MarketDataStore(tmp_path / "market.db")


def _decision(
    context: ContextStore,
    strategy_id: str,
    *,
    decision_id: str,
    ticker: str,
    weight_pct: float,
    created_at: str,
) -> None:
    context.record_decision(
        strategy_id,
        {
            "id": decision_id,
            "session_id": f"session-{decision_id}",
            "ticker": ticker,
            "action": "HOLD",
            "target_position_pct": weight_pct,
            "created_at": created_at,
        },
    )


def test_resolver_uses_latest_target_per_ticker_and_preserves_provenance(
    stores: tuple[ContextStore, MarketDataStore],
) -> None:
    context, _ = stores
    _decision(
        context,
        "alpha",
        decision_id="old-aapl",
        ticker="aapl",
        weight_pct=70,
        created_at="2025-01-01T00:00:00+00:00",
    )
    _decision(
        context,
        "alpha",
        decision_id="new-aapl",
        ticker="AAPL",
        weight_pct=40,
        created_at="2025-01-03T00:00:00+00:00",
    )
    _decision(
        context,
        "alpha",
        decision_id="msft",
        ticker="MSFT",
        weight_pct=35,
        created_at="2025-01-02T00:00:00+00:00",
    )

    exposure = DecisionTargetExposureResolver(context).resolve("alpha")

    assert exposure.status == RiskStatus.COMPLETE
    assert exposure.source == "decision_target"
    assert exposure.weights == {"AAPL": 0.4, "MSFT": 0.35}
    assert exposure.cash_weight == pytest.approx(0.25)
    assert exposure.gross_exposure == pytest.approx(0.75)
    assert exposure.decision_ids == ("new-aapl", "msft")
    assert exposure.as_of == "2025-01-03T00:00:00+00:00"
    assert [item.decision_id for item in exposure.decisions] == [
        "new-aapl",
        "msft",
    ]


@pytest.mark.parametrize(
    ("weights", "expected"),
    [
        ([], RiskStatus.UNAVAILABLE),
        ([0.0], RiskStatus.UNAVAILABLE),
        ([101.0], RiskStatus.INVALID),
        ([60.0, 50.0], RiskStatus.INVALID),
    ],
)
def test_resolver_has_typed_empty_zero_and_invalid_states(
    stores: tuple[ContextStore, MarketDataStore],
    weights: list[float],
    expected: RiskStatus,
) -> None:
    context, _ = stores
    for index, weight in enumerate(weights):
        _decision(
            context,
            "alpha",
            decision_id=f"d-{index}",
            ticker=f"T{index}",
            weight_pct=weight,
            created_at=f"2025-01-{index + 1:02d}T00:00:00+00:00",
        )

    result = DecisionTargetExposureResolver(context).resolve("alpha")

    assert result.status == expected
    assert result.metrics_available is False


def test_overview_exact_returns_tail_risk_drawdown_correlation_and_concentration(
    stores: tuple[ContextStore, MarketDataStore],
) -> None:
    context, market = stores
    _decision(
        context,
        "alpha",
        decision_id="aapl-target",
        ticker="AAPL",
        weight_pct=60,
        created_at="2025-04-01T00:00:00+00:00",
    )
    _decision(
        context,
        "alpha",
        decision_id="msft-target",
        ticker="MSFT",
        weight_pct=30,
        created_at="2025-04-01T00:00:01+00:00",
    )
    aapl_returns = [0.01 if index % 3 else -0.02 for index in range(69)]
    msft_returns = [-0.005 if index % 4 else 0.015 for index in range(69)]
    market.upsert_ohlcv("AAPL", _bars(date(2025, 1, 1), aapl_returns), "fixture")
    market.upsert_ohlcv("MSFT", _bars(date(2025, 1, 1), msft_returns), "fixture")
    market.upsert_ticker_meta("AAPL", sector="Technology")
    market.upsert_ticker_meta("MSFT", sector="Technology")

    result = RiskAnalyticsService(context, market).overview("alpha")
    expected = np.asarray(aapl_returns) * 0.6 + np.asarray(msft_returns) * 0.3
    var_95 = float(np.quantile(expected, 0.05, method="linear"))

    assert result.status == RiskStatus.COMPLETE
    assert result.source == "decision_target"
    assert result.return_unit == "decimal"
    assert result.portfolio_returns == pytest.approx(tuple(expected))
    assert result.var_95 == pytest.approx(var_95)
    assert result.var_99 == pytest.approx(
        float(np.quantile(expected, 0.01, method="linear"))
    )
    assert result.cvar_95 == pytest.approx(float(expected[expected <= var_95].mean()))
    wealth = np.cumprod(1 + expected)
    running_peak = np.maximum.accumulate(np.concatenate((np.asarray([1.0]), wealth)))[
        1:
    ]
    expected_drawdown = wealth / running_peak - 1
    assert result.max_drawdown == pytest.approx(float(expected_drawdown.min()))
    assert result.correlation.labels == ("AAPL", "MSFT")
    assert result.correlation.matrix[0][0] == 1.0
    assert result.correlation.matrix[1][1] == 1.0
    assert result.correlation.matrix[0][1] == pytest.approx(
        result.correlation.matrix[1][0]
    )
    assert result.ticker_concentration.herfindahl_index == pytest.approx(0.45)
    assert result.sector_concentration.weights == {"Technology": pytest.approx(0.9)}
    assert result.as_of == "2025-03-11"

    stress = RiskAnalyticsService(context, market).stress(
        "alpha", uniform_market_shock=-0.2
    )
    assert stress.status == RiskStatus.COMPLETE
    assert stress.historical_worst_day.impact == pytest.approx(float(expected.min()))
    assert stress.uniform_market_shock.shock == -0.2
    assert stress.uniform_market_shock.impact == pytest.approx(-0.18)
    assert stress.uniform_market_shock.assumption == "uniform_market_shock"


def test_two_strategies_with_different_targets_have_different_results(
    stores: tuple[ContextStore, MarketDataStore],
) -> None:
    context, market = stores
    _decision(
        context,
        "alpha",
        decision_id="a",
        ticker="AAPL",
        weight_pct=80,
        created_at="2025-04-01T00:00:00+00:00",
    )
    _decision(
        context,
        "beta",
        decision_id="b",
        ticker="MSFT",
        weight_pct=80,
        created_at="2025-04-01T00:00:00+00:00",
    )
    market.upsert_ohlcv("AAPL", _bars(date(2025, 1, 1), [0.01] * 69), "fixture")
    market.upsert_ohlcv("MSFT", _bars(date(2025, 1, 1), [-0.01] * 69), "fixture")

    service = RiskAnalyticsService(context, market)

    assert (
        service.overview("alpha").portfolio_returns
        != service.overview("beta").portfolio_returns
    )


def test_insufficient_overlap_and_missing_ticker_are_partial_not_zero_metrics(
    stores: tuple[ContextStore, MarketDataStore],
) -> None:
    context, market = stores
    _decision(
        context,
        "short",
        decision_id="short",
        ticker="AAPL",
        weight_pct=50,
        created_at="2025-02-01T00:00:00+00:00",
    )
    market.upsert_ohlcv("AAPL", _bars(date(2025, 1, 1), [0.01] * 58), "fixture")
    _decision(
        context,
        "missing",
        decision_id="missing-a",
        ticker="AAPL",
        weight_pct=50,
        created_at="2025-02-01T00:00:00+00:00",
    )
    _decision(
        context,
        "missing",
        decision_id="missing-b",
        ticker="MSFT",
        weight_pct=25,
        created_at="2025-02-01T00:00:00+00:00",
    )

    short = RiskAnalyticsService(context, market).overview("short")
    missing = RiskAnalyticsService(context, market).overview("missing")

    assert short.status == RiskStatus.PARTIAL
    assert short.exposure.status == RiskStatus.COMPLETE
    assert short.var_95 is None
    assert any("60" in warning for warning in short.warnings)
    assert missing.status == RiskStatus.PARTIAL
    assert missing.var_95 is None
    assert any("MSFT" in warning for warning in missing.warnings)


def test_single_ticker_and_missing_sector_are_explicit(
    stores: tuple[ContextStore, MarketDataStore],
) -> None:
    context, market = stores
    _decision(
        context,
        "alpha",
        decision_id="a",
        ticker="AAPL",
        weight_pct=50,
        created_at="2025-04-01T00:00:00+00:00",
    )
    market.upsert_ohlcv("AAPL", _bars(date(2025, 1, 1), [0.01, -0.01] * 35), "fixture")

    result = RiskAnalyticsService(context, market).overview("alpha")

    assert result.status == RiskStatus.COMPLETE
    assert result.correlation.status == RiskStatus.UNAVAILABLE
    assert result.correlation.labels == ("AAPL",)
    assert result.correlation.matrix == ((1.0,),)
    assert result.sector_concentration.weights == {"Unknown": pytest.approx(0.5)}
