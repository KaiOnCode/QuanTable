from __future__ import annotations

from datetime import date, timedelta
from math import nan

import pytest
from pydantic import ValidationError

from dataflow.store import MarketDataStore
from scanner.models import ScanCondition, ScanField, ScanOperator
from scanner.service import ScannerService
from scanner.universe import TrackedUniverseResolver
from storage.store import ContextStore


def _seed_prices(store: MarketDataStore, ticker: str, closes: list[float]) -> None:
    start = date(2026, 1, 1)
    store.upsert_ohlcv(
        ticker,
        [
            {
                "date": (start + timedelta(days=index)).isoformat(),
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 1000 + index,
            }
            for index, close in enumerate(closes)
        ],
        source="seeded-cache",
    )


def _service(tmp_path) -> tuple[ScannerService, MarketDataStore]:
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    context_store.register_strategy(
        {"id": "strategy-1", "name": "Scanner", "tickers": ["AAPL", "MSFT", "MISS"]}
    )
    _seed_prices(market_store, "AAPL", [100 + index for index in range(51)])
    _seed_prices(market_store, "MSFT", [200 + index for index in range(51)])
    market_store.upsert_fundamentals(
        "AAPL", "2026-01-31", {"ttm": {"pe": 12, "pb": 2, "market_cap": 1_000_000}}
    )
    market_store.upsert_fundamentals(
        "MSFT", "2026-01-31", {"ttm": {"pe": 15, "pb": 3, "market_cap": 2_000_000}}
    )
    market_store.upsert_ticker_meta("AAPL", sector="Technology", currency="USD")
    market_store.upsert_ticker_meta("MSFT", sector="Technology", currency="USD")
    return ScannerService(
        TrackedUniverseResolver(context_store, market_store), market_store
    ), market_store


def test_scan_requires_all_conditions_sorts_results_and_reports_provenance(
    tmp_path,
) -> None:
    # Given: two fully cached tickers match the same AND rule and one has no cache.
    service, _ = _service(tmp_path)
    conditions = (
        ScanCondition(
            field=ScanField.RSI14, operator=ScanOperator.GREATER_THAN, value=50
        ),
        ScanCondition(
            field=ScanField.PE_RATIO, operator=ScanOperator.BETWEEN, value=10, value2=20
        ),
    )

    # When: the deterministic scanner evaluates the tracked universe.
    response = service.scan(conditions)

    # Then: full matches are deterministic and missing cache is visible rather than zero-filled.
    assert [result.ticker for result in response.results] == ["AAPL", "MSFT"]
    assert response.scanned_count == 3
    assert response.matched_count == 2
    assert response.missing_data_count == 1
    assert response.results[0].snapshot.price.value == 150
    assert response.results[0].snapshot.price.source == "ohlcv:seeded-cache"
    assert response.results[0].snapshot.price.currency == "USD"
    assert response.results[0].source_dates["price"] == "2026-02-20"
    assert "MISS: missing rsi14, pe_ratio" in response.warnings


def test_scan_never_treats_nan_or_absent_cache_as_zero_and_does_not_fetch(
    tmp_path,
) -> None:
    # Given: a cache-only ticker has a NaN close and no remote provider fixture.
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    context_store.register_strategy(
        {"id": "strategy-1", "name": "Scanner", "tickers": ["NAN"]}
    )
    _seed_prices(market_store, "NAN", [100, nan])
    service = ScannerService(
        TrackedUniverseResolver(context_store, market_store), market_store
    )
    cached_rows_before = market_store.get_ohlcv("NAN", "0001-01-01", "9999-12-31")

    # When: a price condition is evaluated against the only cached data.
    response = service.scan(
        (
            ScanCondition(
                field=ScanField.PRICE, operator=ScanOperator.LESS_THAN, value=1
            ),
        )
    )

    # Then: it is missing, never a fabricated zero match, and no scan write/fetch occurred.
    assert response.results == ()
    assert response.missing_data_count == 1
    assert response.warnings == ("NAN: missing price",)
    assert (
        market_store.get_ohlcv("NAN", "0001-01-01", "9999-12-31") == cached_rows_before
    )


@pytest.mark.parametrize(
    ("operator", "value", "value2"),
    [
        (ScanOperator.LESS_THAN, 151, None),
        (ScanOperator.GREATER_THAN, 149, None),
        (ScanOperator.LESS_THAN_OR_EQUAL, 150, None),
        (ScanOperator.GREATER_THAN_OR_EQUAL, 150, None),
        (ScanOperator.EQUAL, 150, None),
        (ScanOperator.BETWEEN, 150, 150),
    ],
)
def test_scan_honors_numeric_operator_boundaries(
    tmp_path, operator: ScanOperator, value: float, value2: float | None
) -> None:
    # Given: AAPL's cached closing price is exactly 150.
    service, _ = _service(tmp_path)
    condition = ScanCondition(
        field=ScanField.PRICE, operator=operator, value=value, value2=value2
    )

    # When: each frozen numeric operator evaluates its boundary.
    response = service.scan((condition,))

    # Then: AAPL is included at the documented inclusive/exclusive boundary.
    assert "AAPL" in [result.ticker for result in response.results]


@pytest.mark.parametrize(
    "payload",
    [
        {"field": "sector", "operator": ">", "value": "Technology"},
        {"field": "price", "operator": "between", "value": 20},
        {"field": "price", "operator": "between", "value": 20, "value2": 10},
        {"field": "price", "operator": "<", "value": "cheap"},
        {"field": "roe", "operator": ">", "value": 10},
    ],
)
def test_condition_contract_rejects_unsupported_or_semantically_invalid_input(
    payload,
) -> None:
    # Given / When / Then: only the frozen typed condition grammar crosses the boundary.
    with pytest.raises(ValidationError):
        ScanCondition.model_validate(payload)
