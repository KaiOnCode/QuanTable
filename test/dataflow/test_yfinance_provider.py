from __future__ import annotations

import pandas as pd
import pytest

from dataflow.providers import YFinance as yfinance_provider


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
