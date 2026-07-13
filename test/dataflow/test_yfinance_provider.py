from __future__ import annotations

import pandas as pd
import pytest

from dataflow.providers import YFinance as yfinance_provider


def test_price_history_uses_explicit_adjustment_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class _Ticker:
        def history(self, **kwargs: object) -> pd.DataFrame:
            calls.append(kwargs)
            return pd.DataFrame()

    monkeypatch.setattr(yfinance_provider.yf, "Ticker", lambda _ticker: _Ticker())

    yfinance_provider._get_price_history("AAPL", lookback_days=10)

    assert calls[0]["interval"] == "1d"
    assert calls[0]["auto_adjust"] is True
    assert calls[0]["actions"] is False


def test_adjusted_history_drops_corporate_action_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range("2024-01-02", periods=2, freq="B")

    class _Ticker:
        def history(self, **_kwargs: object) -> pd.DataFrame:
            return pd.DataFrame(
                {
                    "Open": [100.0, 101.0],
                    "High": [101.0, 102.0],
                    "Low": [99.0, 100.0],
                    "Close": [100.5, 101.5],
                    "Volume": [1000.0, 1100.0],
                    "Dividends": [0.0, 5.0],
                    "Stock Splits": [0.0, 2.0],
                },
                index=index,
            )

    monkeypatch.setattr(yfinance_provider.yf, "Ticker", lambda _ticker: _Ticker())

    result = yfinance_provider._get_price_history("AAPL", lookback_days=10)

    assert list(result.columns) == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]


def test_price_rows_respect_exclusive_end_and_never_fallback_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-05"]),
            "open": [100.0, 999.0],
            "high": [101.0, 1000.0],
            "low": [99.0, 998.0],
            "close": [100.5, 999.5],
            "volume": [1000.0, 1000.0],
        }
    )
    monkeypatch.setattr(
        yfinance_provider,
        "_get_price_history",
        lambda *_args, **_kwargs: frame.copy(),
    )

    result = yfinance_provider.df_get_prices(
        "AAPL", lookback_days=10, end_date="2026-01-04"
    )

    assert [row["ts"][:10] for row in result["rows"]] == ["2026-01-02"]
    with pytest.raises(ValueError, match="invalid historical end_date"):
        yfinance_provider.df_get_prices("AAPL", lookback_days=10, end_date="not-a-date")


def test_indicators_preserve_trading_dates_in_ohlcv_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: provider history with an explicit date column and a RangeIndex.
    dates = pd.date_range("2024-01-02", periods=80, freq="B")
    closes = [100.0 + index for index in range(len(dates))]
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": [close - 1.0 for close in closes],
            "high": [close + 1.0 for close in closes],
            "low": [close - 2.0 for close in closes],
            "close": closes,
            "volume": [1000.0 for _ in dates],
        }
    )
    monkeypatch.setattr(
        yfinance_provider,
        "_get_price_history",
        lambda *_args, **_kwargs: frame.copy(),
    )

    # When: indicators expose their cacheable raw OHLCV rows.
    result = yfinance_provider.df_get_indicators("AAPL", lookback_days=60)

    # Then: rows use ISO trading dates rather than dataframe positions.
    rows = result["_ohlcv_rows"]
    assert rows[0]["date"] == "2024-01-02"
    assert rows[-1]["date"] == dates[-1].strftime("%Y-%m-%d")
