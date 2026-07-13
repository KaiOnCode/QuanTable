from __future__ import annotations

import sqlite3

import pytest

from dataflow.store import MarketDataStore


def test_ohlcv_upsert_rejects_non_iso_trading_date(tmp_path) -> None:
    # Given: an isolated market store and a provider row with a positional date.
    store = MarketDataStore(tmp_path / "market.db")
    row = {
        "date": "0",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 1000.0,
    }

    # When / Then: the storage boundary rejects the row without partial writes.
    with pytest.raises(ValueError, match="ISO trading date"):
        store.upsert_ohlcv("AAPL", [row])
    assert store.get_stats()["ohlcv_bars"] == 0


def test_store_initialization_removes_legacy_non_iso_ohlcv_dates(tmp_path) -> None:
    # Given: an older database containing one valid and one positional OHLCV date.
    db_path = tmp_path / "market.db"
    MarketDataStore(db_path)
    with sqlite3.connect(db_path) as db:
        db.executemany(
            """INSERT INTO ohlcv
               (ticker, date, open, high, low, close, volume, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("AAPL", "2024-01-02", 99, 101, 98, 100, 1000, "fixture", "now"),
                ("AAPL", "0", 99, 101, 98, 100, 1000, "fixture", "now"),
            ],
        )

    # When: the store runs its idempotent schema initialization.
    repaired = MarketDataStore(db_path)

    # Then: only the valid historical bar remains available and counted.
    assert repaired.get_stats()["ohlcv_bars"] == 1
    assert repaired.get_ohlcv("AAPL", "2024-01-01", "2024-01-03")[0]["date"] == (
        "2024-01-02"
    )


def test_store_migrates_and_persists_adjustment_mode(tmp_path) -> None:
    db_path = tmp_path / "legacy-market.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """CREATE TABLE ohlcv (
               ticker TEXT NOT NULL, date TEXT NOT NULL,
               open REAL, high REAL, low REAL, close REAL, volume REAL,
               source TEXT DEFAULT 'yfinance', fetched_at TEXT NOT NULL,
               PRIMARY KEY (ticker, date))"""
        )

    store = MarketDataStore(db_path)
    store.upsert_ohlcv(
        "AAPL",
        [
            {
                "date": "2024-01-02",
                "open": 99,
                "high": 101,
                "low": 98,
                "close": 100,
                "volume": 1000,
            }
        ],
        adjustment_mode="provider_adjusted_prices",
    )

    row = store.get_ohlcv("AAPL", "2024-01-02", "2024-01-02")[0]
    assert row["adjustment_mode"] == "provider_adjusted_prices"
