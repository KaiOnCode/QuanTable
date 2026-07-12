from __future__ import annotations

from datetime import date

import pytest

from broker.backtest_data import (
    BacktestDataError,
    BacktestDataService,
    BacktestDatasetPreparer,
)
from dataflow.store import MarketDataStore


def _seed_prices(
    store: MarketDataStore, ticker: str, rows: list[tuple[str, float]]
) -> None:
    store.upsert_ohlcv(
        ticker,
        [
            {
                "date": trading_date,
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 100,
            }
            for trading_date, close in rows
        ],
    )


class _FixtureHistoryLoader:
    def __init__(self, store: MarketDataStore) -> None:
        self._store = store
        self.calls: list[tuple[str, str, str]] = []

    def preload(self, ticker: str, date_from: str, date_to: str) -> None:
        self.calls.append((ticker, date_from, date_to))
        close = 100.0 if ticker == "AAPL" else 400.0
        _seed_prices(
            self._store,
            ticker,
            [(date_from, close), (date_to, close + 1.0)],
        )


def test_backtest_data_service_hides_future_sentinel_from_all_scoped_reads(
    tmp_path,
) -> None:
    # Given: the store contains a future price, fundamental snapshot, and news record.
    store = MarketDataStore(str(tmp_path / "market.db"))
    _seed_prices(
        store,
        "AAPL",
        [("2026-01-02", 100.0), ("2026-01-03", 101.0), ("2026-01-10", 999.0)],
    )
    store.upsert_fundamentals("AAPL", "2026-01-02", {"ttm": {"pe": 10.0}})
    store.upsert_fundamentals("AAPL", "2026-01-10", {"ttm": {"pe": 999.0}})
    store.add_news_articles(
        "AAPL",
        [
            {
                "title": "known",
                "url": "https://example.test/known",
                "published_at": "2026-01-02T00:00:00Z",
            },
            {
                "title": "future sentinel",
                "url": "https://example.test/future",
                "published_at": "2026-01-10T00:00:00Z",
            },
        ],
    )
    service = BacktestDataService(as_of="2026-01-03T00:00:00Z", market_store=store)

    # When: a backtest-scoped financial service asks for every supported data type.
    prices = service.get_prices("AAPL", "2026-01-01", "2026-01-31")
    fundamentals = service.get_fundamentals("AAPL")
    news = service.get_news("AAPL")
    indicators = service.get_indicators("AAPL")

    # Then: no response can reveal data newer than the decision boundary.
    assert [row["close"] for row in prices] == [100.0, 101.0]
    assert fundamentals["pe"] == 10.0
    assert [article["title"] for article in news] == ["known"]
    assert indicators["as_of"] == "2026-01-03"


def test_characterizes_current_early_sma_as_shortened_window(tmp_path) -> None:
    store = MarketDataStore(str(tmp_path / "market.db"))
    _seed_prices(store, "AAPL", [("2026-01-02", 100.0), ("2026-01-03", 110.0)])
    service = BacktestDataService(as_of="2026-01-03", market_store=store)

    indicators = service.get_indicators("AAPL")

    assert indicators["ma"] == {"sma20": 105.0, "sma50": 105.0}


def test_backtest_data_service_fails_when_history_is_not_available(tmp_path) -> None:
    # Given: only a future price exists for the requested ticker.
    store = MarketDataStore(str(tmp_path / "market.db"))
    _seed_prices(store, "AAPL", [("2026-01-10", 999.0)])
    service = BacktestDataService(as_of=date(2026, 1, 3), market_store=store)

    # When / Then: the scoped boundary fails rather than fetching live data.
    with pytest.raises(BacktestDataError, match="no historical price data"):
        service.get_prices("AAPL", "2026-01-01", "2026-01-03")


def test_dataset_preparer_returns_distinct_target_and_benchmark_windows(
    tmp_path,
) -> None:
    # Given: target and benchmark have deliberately different histories.
    store = MarketDataStore(str(tmp_path / "market.db"))
    _seed_prices(store, "AAPL", [("2026-01-02", 100.0), ("2026-01-03", 110.0)])
    _seed_prices(store, "SPY", [("2026-01-02", 400.0), ("2026-01-03", 404.0)])
    preparer = BacktestDatasetPreparer(market_store=store)

    # When: the job preloads its request window.
    dataset = preparer.prepare(
        ticker="AAPL",
        benchmark_symbol="SPY",
        date_from="2026-01-02",
        date_to="2026-01-03",
    )

    # Then: the dataframes retain independent close histories.
    assert list(dataset.target["Close"]) == [100.0, 110.0]
    assert list(dataset.benchmark["Close"]) == [400.0, 404.0]


def test_dataset_preparer_preloads_missing_target_and_benchmark_windows(
    tmp_path,
) -> None:
    # Given: the production-shaped cache is empty and a historical loader owns fills.
    store = MarketDataStore(str(tmp_path / "market.db"))
    loader = _FixtureHistoryLoader(store)
    preparer = BacktestDatasetPreparer(
        market_store=store,
        history_loader=loader,
    )

    # When: a backtest requests a target and independent benchmark window.
    dataset = preparer.prepare(
        ticker="AAPL",
        benchmark_symbol="SPY",
        date_from="2024-01-02",
        date_to="2024-03-29",
    )

    # Then: both exact windows are preloaded before the cache-only dataset is built.
    assert loader.calls == [
        ("AAPL", "2024-01-02", "2024-03-29"),
        ("SPY", "2024-01-02", "2024-03-29"),
    ]
    assert list(dataset.target["Close"]) == [100.0, 101.0]
    assert list(dataset.benchmark["Close"]) == [400.0, 401.0]


def test_dataset_preparer_refreshes_partial_request_window(tmp_path) -> None:
    # Given: target cache has only an interior bar while benchmark is empty.
    store = MarketDataStore(str(tmp_path / "market.db"))
    _seed_prices(store, "AAPL", [("2024-02-01", 105.0)])
    loader = _FixtureHistoryLoader(store)
    preparer = BacktestDatasetPreparer(store, history_loader=loader)

    # When: the complete request window is prepared.
    dataset = preparer.prepare(
        ticker="AAPL",
        benchmark_symbol="SPY",
        date_from="2024-01-02",
        date_to="2024-03-29",
    )

    # Then: both symbols are refreshed before cache-only reads begin.
    assert loader.calls == [
        ("AAPL", "2024-01-02", "2024-03-29"),
        ("SPY", "2024-01-02", "2024-03-29"),
    ]
    assert list(dataset.target["Close"]) == [100.0, 105.0, 101.0]
