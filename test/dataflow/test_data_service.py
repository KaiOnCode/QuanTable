from __future__ import annotations

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderType
from dataflow.history import DataServiceHistoryLoader
from dataflow.service import DataService
from dataflow.store import MarketDataStore


def test_data_service_reads_position_from_injected_broker() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    data_service = DataService(broker=broker)
    position = data_service.df_get_position("AAPL")

    assert position["side"] == "long"
    assert position["qty_pct"] == pytest.approx(1_000.0 / 99_998.4995)
    assert position["avg_cost"] == pytest.approx(100.05)


def test_history_loader_fetches_exact_window_into_injected_store(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a provider result and an isolated production-shaped market store.
    calls: list[tuple[str, int, str | None]] = []

    def fake_get_prices(
        ticker: str,
        lookback_days: int,
        end_date: str | None = None,
    ) -> dict:
        calls.append((ticker, lookback_days, end_date))
        return {
            "ticker": ticker,
            "rows": [
                {
                    "ts": "2024-01-02T00:00:00Z",
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                    "v": 1000.0,
                },
                {
                    "ts": "2024-03-29T00:00:00Z",
                    "o": 110.0,
                    "h": 111.0,
                    "l": 109.0,
                    "c": 110.5,
                    "v": 1200.0,
                },
            ],
        }

    monkeypatch.setattr("dataflow.service.df_get_prices", fake_get_prices)
    store = MarketDataStore(tmp_path / "market.db")
    loader = DataServiceHistoryLoader(store)

    # When: the Backtest preload requests an inclusive historical window.
    loader.preload("AAPL", "2024-01-02", "2024-03-29")

    # Then: provider end exclusivity is handled and rows land in the same store.
    assert calls == [("AAPL", 88, "2024-03-30")]
    rows = store.get_ohlcv("AAPL", "2024-01-02", "2024-03-29")
    assert [row["date"] for row in rows] == ["2024-01-02", "2024-03-29"]


def test_history_loader_persists_when_general_market_cache_is_disabled(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: general market-data caching is disabled but Backtest needs its store.
    monkeypatch.setattr("dataflow.service.STORE_ENABLED", False)
    monkeypatch.setattr(
        "dataflow.service.df_get_prices",
        lambda *args, **kwargs: {
            "rows": [
                {
                    "ts": "2024-01-02T00:00:00Z",
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                    "v": 1000.0,
                }
            ]
        },
    )
    store = MarketDataStore(tmp_path / "market.db")

    # When: the dedicated historical loader preloads a Backtest window.
    DataServiceHistoryLoader(store).preload("AAPL", "2024-01-02", "2024-01-02")

    # Then: the Backtest-owned store still receives the fetched row.
    assert len(store.get_ohlcv("AAPL", "2024-01-02", "2024-01-02")) == 1


def test_history_loader_propagates_backtest_store_write_failure(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a provider response succeeds but the Backtest store write fails.
    monkeypatch.setattr("dataflow.service.STORE_ENABLED", False)
    monkeypatch.setattr(
        "dataflow.service.df_get_prices",
        lambda *args, **kwargs: {
            "rows": [
                {
                    "ts": "2024-01-02T00:00:00Z",
                    "o": 100.0,
                    "h": 101.0,
                    "l": 99.0,
                    "c": 100.5,
                    "v": 1000.0,
                }
            ]
        },
    )
    store = MarketDataStore(tmp_path / "market.db")
    monkeypatch.setattr(
        store,
        "upsert_ohlcv",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
    )

    # When/Then: persistence failure escapes to the Backtest job error boundary.
    with pytest.raises(RuntimeError, match="disk full"):
        DataServiceHistoryLoader(store).preload("AAPL", "2024-01-02", "2024-01-02")
