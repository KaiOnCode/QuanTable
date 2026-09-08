from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

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


def test_history_loader_requests_trading_bar_warmup_without_future_execution_bar(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, str | None]] = []

    def fake_get_prices(
        ticker: str, lookback_days: int, end_date: str | None
    ) -> dict[str, object]:
        calls.append((ticker, lookback_days, end_date))
        return {
            "rows": [
                {
                    "ts": trading_date,
                    "o": close,
                    "h": close + 1,
                    "l": close - 1,
                    "c": close,
                    "v": 1000,
                }
                for trading_date, close in (
                    ("2023-12-28T00:00:00Z", 98.0),
                    ("2023-12-29T00:00:00Z", 99.0),
                    ("2024-01-02T00:00:00Z", 100.0),
                )
            ]
        }

    monkeypatch.setattr("dataflow.service.df_get_prices", fake_get_prices)
    store = MarketDataStore(tmp_path / "market.db")

    DataServiceHistoryLoader(store).preload(
        "AAPL", "2024-01-02", "2024-01-02", warmup_bars=2
    )

    assert calls == [("AAPL", 11, "2024-01-03")]
    assert [
        row["date"] for row in store.get_ohlcv("AAPL", "2023-12-01", "2024-01-31")
    ] == ["2023-12-28", "2023-12-29", "2024-01-02"]


def test_history_loader_keeps_provenance_scoped_to_each_backtest_window(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    barrier = Barrier(2)

    def fake_get_prices(
        _ticker: str, _lookback_days: int, end_date: str | None = None
    ) -> dict:
        barrier.wait(timeout=1)
        return {
            "rows": [],
            "tz": (
                "America/New_York"
                if end_date == "2024-01-03"
                else "America/Los_Angeles"
            ),
        }

    monkeypatch.setattr(
        "dataflow.service.df_get_prices",
        fake_get_prices,
    )
    loader = DataServiceHistoryLoader(MarketDataStore(tmp_path / "market.db"))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_preload = executor.submit(
            loader.preload, "AAPL", "2024-01-02", "2024-01-02"
        )
        second_preload = executor.submit(
            loader.preload, "AAPL", "2024-02-01", "2024-02-10"
        )
        first_preload.result()
        second_preload.result()

    first = loader.provenance_for("AAPL", "2024-01-02", "2024-01-02", 0)
    second = loader.provenance_for("AAPL", "2024-02-01", "2024-02-10", 0)
    assert first is not None
    assert second is not None
    assert first["lookback_days"] == 1
    assert second["lookback_days"] == 10
    assert first["provider_timezone"] == "America/New_York"
    assert second["provider_timezone"] == "America/Los_Angeles"


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
