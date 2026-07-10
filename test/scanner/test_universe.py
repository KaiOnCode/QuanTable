from __future__ import annotations

import json

import pytest

from dataflow.store import MarketDataStore
from scanner.models import UniverseSource
from scanner.universe import TrackedUniverseResolver, UnsupportedUniverseError
from storage.store import ContextStore


def _seed_watchlist(store: ContextStore, tickers: list[str]) -> None:
    db = store._system_db()
    db.execute(
        """CREATE TABLE watchlists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tickers_json TEXT DEFAULT '[]',
            notes_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    db.execute(
        """INSERT INTO watchlists
           (id, name, tickers_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            "watchlist-1",
            "Scanner inputs",
            json.dumps(tickers),
            "2026-01-01",
            "2026-01-01",
        ),
    )
    db.commit()


def test_resolver_builds_sorted_union_with_all_source_provenance(tmp_path) -> None:
    # Given: independent strategy, watchlist, and cached-market ticker sources.
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    context_store.register_strategy(
        {"id": "strategy-1", "name": "Scanner", "tickers": [" aapl ", "MSFT"]}
    )
    _seed_watchlist(context_store, ["msft", " GOOG "])
    market_store.upsert_ohlcv(
        "goog",
        [{"date": "2026-01-02", "open": 100, "high": 101, "low": 99, "close": 100}],
    )
    market_store.upsert_ticker_meta("tsla", sector="Technology", currency="USD")

    # When: Scanner resolves its only supported tracked universe.
    universe = TrackedUniverseResolver(context_store, market_store).resolve()

    # Then: values are normalized, deduplicated, sorted, and retain every owner.
    assert [item.ticker for item in universe] == ["AAPL", "GOOG", "MSFT", "TSLA"]
    assert universe[0].provenance == (UniverseSource.STRATEGY,)
    assert universe[1].provenance == (
        UniverseSource.MARKET_STORE,
        UniverseSource.WATCHLIST,
    )
    assert universe[2].provenance == (
        UniverseSource.STRATEGY,
        UniverseSource.WATCHLIST,
    )
    assert universe[3].provenance == (UniverseSource.MARKET_STORE,)


def test_resolver_returns_empty_and_rejects_demo_universes(tmp_path) -> None:
    # Given: no tracked source contains a ticker.
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    resolver = TrackedUniverseResolver(context_store, market_store)

    # When / Then: empty is an honest result and fixture universes are unsupported.
    assert resolver.resolve() == ()
    with pytest.raises(UnsupportedUniverseError, match="tracked"):
        resolver.resolve("sp500")


def test_resolver_rejects_malformed_tickers_from_every_tracked_source(tmp_path) -> None:
    # Given: each persisted source contains a valid ticker and punctuation-corrupted values.
    context_store = ContextStore(tmp_path / "context")
    market_store = MarketDataStore(tmp_path / "market.db")
    context_store.register_strategy(
        {"id": "strategy-1", "name": "Scanner", "tickers": ["AAPL", "A'A"]}
    )
    _seed_watchlist(context_store, ["BRK.B", "A'P"])
    for ticker in ("000001.SZ", "A'A", "A'A'P", "A'A'P'L", "A'P", "APP,", "APP,E"):
        market_store.upsert_ticker_meta(ticker, sector="Technology", currency="USD")

    # When: the tracked resolver combines all persisted sources.
    universe = TrackedUniverseResolver(context_store, market_store).resolve()

    # Then: valid US and China symbols survive while malformed data never enters scans.
    assert [item.ticker for item in universe] == ["000001.SZ", "AAPL", "BRK.B"]
