from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataflow.store import MarketDataStore
from risk.service import RiskAnalyticsService
from server.routes import risk as risk_routes
from storage.store import ContextStore


def _bars(start: date, daily_returns: list[float]) -> list[dict[str, float | str]]:
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
    for offset, daily_return in enumerate(daily_returns, start=1):
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


def _decision(
    store: ContextStore,
    strategy_id: str,
    *,
    decision_id: str,
    ticker: str,
    target_position_pct: float,
) -> None:
    store.record_decision(
        strategy_id,
        {
            "id": decision_id,
            "session_id": f"session-{decision_id}",
            "ticker": ticker,
            "action": "HOLD",
            "target_position_pct": target_position_pct,
            "created_at": "2026-03-20T00:00:00+00:00",
        },
    )


@pytest.fixture
def risk_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ContextStore, MarketDataStore]]:
    context = ContextStore(tmp_path / "context")
    market = MarketDataStore(tmp_path / "market.db")
    for strategy_id in ("complete", "empty", "invalid", "partial"):
        context.register_strategy(
            {"id": strategy_id, "name": strategy_id.title(), "tickers": ["AAPL"]}
        )
    _decision(
        context,
        "complete",
        decision_id="complete-aapl",
        ticker="AAPL",
        target_position_pct=75,
    )
    _decision(
        context,
        "invalid",
        decision_id="invalid-aapl",
        ticker="AAPL",
        target_position_pct=110,
    )
    _decision(
        context,
        "partial",
        decision_id="partial-aapl",
        ticker="SHORT",
        target_position_pct=50,
    )
    market.upsert_ohlcv(
        "AAPL",
        _bars(date(2026, 1, 1), [0.01 if index % 2 else -0.005 for index in range(69)]),
        "risk-api-fixture",
    )
    market.upsert_ohlcv(
        "SHORT", _bars(date(2026, 1, 1), [0.01] * 10), "risk-api-short-fixture"
    )
    service = RiskAnalyticsService(context, market)
    monkeypatch.setattr(risk_routes, "get_store", lambda: context)
    monkeypatch.setattr(risk_routes, "get_risk_service", lambda: service)
    app = FastAPI()
    app.include_router(risk_routes.router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, context, market
    context.close()


def test_overview_and_stress_expose_one_decision_target_snapshot(
    risk_api: tuple[TestClient, ContextStore, MarketDataStore],
) -> None:
    # Given: one registered strategy with a persisted target and enough market history.
    client, _, _ = risk_api

    # When: the overview and supported uniform-shock stress routes are requested.
    overview = client.get("/api/risk/complete/overview?lookback_days=60")
    stress = client.post(
        "/api/risk/complete/stress",
        json={"uniform_market_shock": -0.1, "lookback_days": 60},
    )

    # Then: both return typed decimal results from the same decision provenance.
    assert overview.status_code == 200
    assert stress.status_code == 200
    overview_body = overview.json()
    stress_body = stress.json()
    assert overview_body["status"] == "complete"
    assert overview_body["source"] == "decision_target"
    assert overview_body["return_unit"] == "decimal"
    assert overview_body["exposure"]["weights"] == {"AAPL": 0.75}
    assert stress_body["decision_ids"] == overview_body["exposure"]["decision_ids"]
    assert stress_body["uniform_market_shock"] == {
        "shock": -0.1,
        "gross_exposure": 0.75,
        "impact": pytest.approx(-0.075),
        "assumption": "uniform_market_shock",
    }


@pytest.mark.parametrize(
    ("strategy_id", "expected_status"),
    [("empty", "unavailable"), ("invalid", "invalid"), ("partial", "partial")],
)
def test_overview_preserves_non_complete_domain_states(
    risk_api: tuple[TestClient, ContextStore, MarketDataStore],
    strategy_id: str,
    expected_status: str,
) -> None:
    # Given: a registered strategy with no, invalid, or insufficient risk inputs.
    client, _, _ = risk_api

    # When: its overview is requested.
    response = client.get(f"/api/risk/{strategy_id}/overview")

    # Then: the route keeps the typed state and never supplies zero-valued metrics.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == expected_status
    assert body["var_95"] is None
    assert body["max_drawdown"] is None


def test_missing_strategy_and_invalid_boundaries_fail_explicitly(
    risk_api: tuple[TestClient, ContextStore, MarketDataStore],
) -> None:
    # Given: a mounted Risk API with a known strategy registry.
    client, _, _ = risk_api

    # When: callers use an unknown strategy or unsupported request bounds.
    missing = client.get("/api/risk/missing/overview")
    invalid_lookback = client.get("/api/risk/complete/overview?lookback_days=59")
    invalid_shock = client.post(
        "/api/risk/complete/stress", json={"uniform_market_shock": -1.1}
    )
    unsupported_factor = client.post(
        "/api/risk/complete/stress",
        json={"uniform_market_shock": -0.1, "vix_spike": 20},
    )

    # Then: ownership is 404 and request validation is a stable 422 boundary.
    assert missing.status_code == 404
    assert invalid_lookback.status_code == 422
    assert invalid_shock.status_code == 422
    assert unsupported_factor.status_code == 422


def test_application_registers_risk_routes() -> None:
    # Given: the production FastAPI application.
    from server.main import app

    # When: its OpenAPI contract is inspected.
    paths = app.openapi()["paths"]

    # Then: both deterministic Risk routes are registered.
    assert "/api/risk/{strategy_id}/overview" in paths
    assert "/api/risk/{strategy_id}/stress" in paths
