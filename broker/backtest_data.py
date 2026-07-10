from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol

import pandas as pd

from dataflow.store import MarketDataStore


class BacktestDataError(RuntimeError):
    pass


class ToolDataService(Protocol):
    def get_prices(self, ticker: str, start_date: str, end_date: str) -> list[dict]: ...

    def get_indicators(self, ticker: str) -> dict: ...

    def get_fundamentals(self, ticker: str) -> dict: ...

    def get_news(self, ticker: str, window_days: int = 7) -> list[dict]: ...


def _as_of_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as error:
        raise BacktestDataError(f"invalid as_of date: {value}") from error


@dataclass(frozen=True, slots=True)
class BacktestDataService:
    as_of: str | date
    market_store: MarketDataStore

    @property
    def as_of_date(self) -> date:
        return _as_of_date(self.as_of)

    def get_prices(self, ticker: str, start_date: str, end_date: str) -> list[dict]:
        bounded_end = min(_as_of_date(end_date), self.as_of_date).isoformat()
        rows = self.market_store.get_ohlcv(ticker, start_date[:10], bounded_end)
        if not rows:
            raise BacktestDataError(
                f"no historical price data for {ticker.upper()} through {bounded_end}"
            )
        return rows

    def get_indicators(self, ticker: str) -> dict:
        lookback_start = (self.as_of_date - timedelta(days=100)).isoformat()
        rows = self.get_prices(ticker, lookback_start, self.as_of_date.isoformat())
        closes = pd.Series([float(row["close"]) for row in rows], dtype=float)
        sma20 = float(closes.tail(20).mean())
        sma50 = float(closes.tail(50).mean())
        return {
            "ticker": ticker.upper(),
            "as_of": self.as_of_date.isoformat(),
            "ma": {"sma20": sma20, "sma50": sma50},
            "rsi14": None,
            "macd": {},
            "atr20": None,
        }

    def get_fundamentals(self, ticker: str) -> dict:
        result = self.market_store.get_fundamentals(
            ticker, as_of_date=self.as_of_date.isoformat()
        )
        if result is None:
            raise BacktestDataError(
                f"no point-in-time fundamentals for {ticker.upper()} through {self.as_of_date.isoformat()}"
            )
        return result

    def get_news(self, ticker: str, window_days: int = 7) -> list[dict]:
        if window_days <= 0:
            raise BacktestDataError("news window_days must be positive")
        start_date = (self.as_of_date - timedelta(days=window_days)).isoformat()
        return self.market_store.get_news_as_of(
            ticker,
            start_date,
            self.as_of_date.isoformat(),
        )


@dataclass(frozen=True, slots=True)
class BacktestDataset:
    target: pd.DataFrame
    benchmark: pd.DataFrame


@dataclass(frozen=True, slots=True)
class BacktestDatasetPreparer:
    market_store: MarketDataStore

    def prepare(
        self,
        *,
        ticker: str,
        benchmark_symbol: str,
        date_from: str,
        date_to: str,
    ) -> BacktestDataset:
        start = _as_of_date(date_from)
        end = _as_of_date(date_to)
        if start > end:
            raise BacktestDataError("date_from must not be after date_to")
        target = self._window(ticker, start, end)
        benchmark = self._window(benchmark_symbol, start, end)
        if target.empty or benchmark.empty:
            raise BacktestDataError("target and benchmark require historical OHLCV")
        return BacktestDataset(target=target, benchmark=benchmark)

    def _window(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        rows = self.market_store.get_ohlcv(ticker, start.isoformat(), end.isoformat())
        if not rows:
            return pd.DataFrame(
                columns=pd.Index(["Open", "High", "Low", "Close", "Volume"])
            )
        frame = pd.DataFrame(rows)
        frame.index = pd.to_datetime(frame.pop("date"), utc=True)
        return pd.DataFrame(
            {
                "Open": frame["open"],
                "High": frame["high"],
                "Low": frame["low"],
                "Close": frame["close"],
                "Volume": frame["volume"],
            },
            index=frame.index,
        )
