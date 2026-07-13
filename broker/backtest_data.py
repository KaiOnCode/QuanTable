from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
import math
from typing import Protocol, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from dataflow.store import MarketDataStore


class BacktestDataError(RuntimeError):
    pass


def _yfinance_version() -> str:
    try:
        return version("yfinance")
    except PackageNotFoundError:
        return "unknown"


class ToolDataService(Protocol):
    def get_prices(self, ticker: str, start_date: str, end_date: str) -> list[dict]: ...

    def get_indicators(self, ticker: str) -> dict: ...

    def get_fundamentals(self, ticker: str) -> dict: ...

    def get_news(self, ticker: str, window_days: int = 7) -> list[dict]: ...


class HistoricalPriceLoader(Protocol):
    def preload(
        self,
        ticker: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> None: ...


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
        rows = self.market_store.get_ohlcv_tail(
            ticker, through_date=self.as_of_date.isoformat(), limit=50
        )
        if not rows:
            raise BacktestDataError(
                f"no historical price data for {ticker.upper()} through {self.as_of_date.isoformat()}"
            )
        closes = pd.Series([float(row["close"]) for row in rows], dtype=float)
        highs = pd.Series([float(row["high"]) for row in rows], dtype=float)
        lows = pd.Series([float(row["low"]) for row in rows], dtype=float)
        sma20_series = cast(pd.Series, closes.rolling(20, min_periods=20).mean())
        sma50_series = cast(pd.Series, closes.rolling(50, min_periods=50).mean())
        delta = closes.diff()
        gains = cast(pd.Series, delta.clip(lower=0).rolling(14, min_periods=14).mean())
        losses = cast(
            pd.Series, (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
        )
        relative_strength = gains / losses.replace(0.0, float("nan"))
        rsi14_series = cast(pd.Series, 100.0 - (100.0 / (1.0 + relative_strength)))
        rsi14_series = rsi14_series.mask((losses == 0.0) & (gains > 0.0), 100.0)
        ema12 = closes.ewm(span=12, adjust=False, min_periods=12).mean()
        ema26 = closes.ewm(span=26, adjust=False, min_periods=26).mean()
        macd_series = cast(pd.Series, ema12 - ema26)
        macd_signal = cast(
            pd.Series,
            macd_series.ewm(span=9, adjust=False, min_periods=9).mean(),
        )
        previous_close = closes.shift(1)
        true_range = pd.concat(
            [
                highs - lows,
                (highs - previous_close).abs(),
                (lows - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr14_series = cast(pd.Series, true_range.rolling(14, min_periods=14).mean())

        def latest_or_none(series: pd.Series) -> float | None:
            value = series.iloc[-1]
            return None if pd.isna(value) else float(value)

        sma20 = latest_or_none(sma20_series)
        sma50 = latest_or_none(sma50_series)
        rsi14 = latest_or_none(rsi14_series)
        macd_value = latest_or_none(macd_series)
        signal_value = latest_or_none(macd_signal)
        histogram = (
            macd_value - signal_value
            if macd_value is not None and signal_value is not None
            else None
        )
        atr14 = latest_or_none(atr14_series)
        return {
            "ticker": ticker.upper(),
            "as_of": self.as_of_date.isoformat(),
            "ma": {"sma20": sma20, "sma50": sma50},
            "rsi14": rsi14,
            "macd": {
                "value": macd_value,
                "signal": signal_value,
                "histogram": histogram,
            },
            "atr14": atr14,
            "ready": {
                "sma20": sma20 is not None,
                "sma50": sma50 is not None,
                "rsi14": rsi14 is not None,
                "macd": histogram is not None,
                "atr14": atr14 is not None,
            },
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
    target_history: pd.DataFrame
    benchmark_history: pd.DataFrame
    warmup_bar_count: int


@dataclass(frozen=True, slots=True)
class BacktestDatasetPreparer:
    market_store: MarketDataStore
    history_loader: HistoricalPriceLoader | None = None

    def prepare(
        self,
        *,
        ticker: str,
        benchmark_symbol: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> BacktestDataset:
        start = _as_of_date(date_from)
        end = _as_of_date(date_to)
        if start > end:
            raise BacktestDataError("date_from must not be after date_to")
        if warmup_bars < 0:
            raise BacktestDataError("warmup_bars must not be negative")
        if self.history_loader is not None:
            try:
                self.history_loader.preload(
                    ticker, start.isoformat(), end.isoformat(), warmup_bars
                )
                self.history_loader.preload(
                    benchmark_symbol,
                    start.isoformat(),
                    end.isoformat(),
                    warmup_bars,
                )
            except (TypeError, ValueError) as error:
                raise BacktestDataError(
                    "historical provider returned invalid OHLCV"
                ) from error
        target = self._window(ticker, start, end)
        benchmark = self._window(benchmark_symbol, start, end)
        if target.empty:
            raise BacktestDataError("target requires historical OHLCV")
        if target.index.intersection(benchmark.index).empty:
            raise BacktestDataError(
                "target and benchmark require an overlapping evaluation session"
            )
        target_history = self._history_window(
            ticker,
            start,
            end,
            warmup_bars,
            self._loader_provenance(ticker, start, end, warmup_bars),
        )
        benchmark_history = self._history_window(
            benchmark_symbol,
            start,
            end,
            warmup_bars,
            self._loader_provenance(benchmark_symbol, start, end, warmup_bars),
        )
        self._validate_window(target_history, "target")
        self._validate_unmixed_adjustment_modes(target_history, "target")
        if not benchmark_history.empty:
            self._validate_window(benchmark_history, "benchmark")
            self._validate_unmixed_adjustment_modes(benchmark_history, "benchmark")
        required_adjustment_mode = getattr(self.history_loader, "adjustment_mode", None)
        if isinstance(required_adjustment_mode, str):
            self._validate_adjustment_mode(
                target_history, "target", required_adjustment_mode
            )
            if not benchmark_history.empty:
                self._validate_adjustment_mode(
                    benchmark_history, "benchmark", required_adjustment_mode
                )
        return BacktestDataset(
            target=target,
            benchmark=benchmark,
            target_history=target_history,
            benchmark_history=benchmark_history,
            warmup_bar_count=warmup_bars,
        )

    def _history_window(
        self,
        ticker: str,
        start: date,
        end: date,
        warmup_bars: int,
        loader_provenance: dict[str, object] | None,
    ) -> pd.DataFrame:
        prior = self.market_store.get_ohlcv_tail(
            ticker,
            through_date=(start - timedelta(days=1)).isoformat(),
            limit=warmup_bars,
        )
        evaluation = self.market_store.get_ohlcv(
            ticker, start.isoformat(), end.isoformat()
        )
        frame = self._rows_to_frame([*prior, *evaluation])
        evaluation_days = (end + timedelta(days=1) - start).days
        lookback_days = (
            evaluation_days + math.ceil(warmup_bars * 7 / 5) + (7 if warmup_bars else 0)
        )
        provenance: dict[str, object] = {
            "provider": "yfinance",
            "library_version": _yfinance_version(),
            "ticker": ticker.upper(),
            "date_from": start.isoformat(),
            "date_to": end.isoformat(),
            "end_exclusive": (end + timedelta(days=1)).isoformat(),
            "lookback_days": lookback_days,
            "provider_buffer_days": 100,
            "interval": "1d",
            "auto_adjust": True,
            "actions": False,
            "warmup_bars": warmup_bars,
            "corporate_actions_mode": "provider_adjusted_prices",
            "provider_end_semantics": "exclusive",
            "provider_timezone": "unknown",
            "timezone_normalization": "exchange_session_date_to_UTC_midnight",
        }
        if loader_provenance is not None:
            provider_timezone = loader_provenance.get("provider_timezone")
            lookback_value = loader_provenance.get("lookback_days")
            if isinstance(provider_timezone, str):
                if provider_timezone == "unknown":
                    provenance["provider_timezone"] = provider_timezone
                else:
                    try:
                        provenance["provider_timezone"] = ZoneInfo(
                            provider_timezone
                        ).key
                    except (ValueError, ZoneInfoNotFoundError):
                        provenance["provider_timezone"] = "unknown"
            if isinstance(lookback_value, int) and lookback_value > 0:
                provenance["lookback_days"] = lookback_value
        frame.attrs["backtest_data_provenance"] = provenance
        return frame

    def _loader_provenance(
        self,
        ticker: str,
        start: date,
        end: date,
        warmup_bars: int,
    ) -> dict[str, object] | None:
        owner = self.history_loader
        if owner is None:
            return None
        getter = getattr(owner, "provenance_for", None)
        if not callable(getter):
            return None
        value = getter(ticker, start.isoformat(), end.isoformat(), warmup_bars)
        return value if isinstance(value, dict) else None

    def _window(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        rows = self.market_store.get_ohlcv(ticker, start.isoformat(), end.isoformat())
        return self._rows_to_frame(rows)

    @staticmethod
    def _rows_to_frame(rows: list[dict]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(
                columns=pd.Index(["Open", "High", "Low", "Close", "Volume"])
            )
        frame = pd.DataFrame(rows)
        adjustment_mode_column = (
            frame["adjustment_mode"]
            if "adjustment_mode" in frame.columns
            else pd.Series(["unknown"] * len(frame), index=frame.index)
        )
        adjustment_modes = tuple(str(value) for value in adjustment_mode_column)
        frame.index = pd.to_datetime(frame.pop("date"), utc=True)
        normalized = pd.DataFrame(
            {
                "Open": frame["open"],
                "High": frame["high"],
                "Low": frame["low"],
                "Close": frame["close"],
                "Volume": frame["volume"],
            },
            index=frame.index,
        )
        normalized.attrs["adjustment_modes"] = adjustment_modes
        return normalized

    @staticmethod
    def _validate_window(frame: pd.DataFrame, label: str) -> None:
        if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
            raise BacktestDataError(f"{label} dates must be unique and monotonic")
        numeric = frame[["Open", "High", "Low", "Close", "Volume"]]
        try:
            finite = all(
                math.isfinite(float(value))
                for row in numeric.itertuples(index=False, name=None)
                for value in row
            )
        except (TypeError, ValueError) as error:
            raise BacktestDataError(f"{label} requires finite OHLCV") from error
        if not finite:
            raise BacktestDataError(f"{label} requires finite OHLCV")
        invalid_ohlc = (
            (numeric["Open"] <= 0)
            | (numeric["High"] <= 0)
            | (numeric["Low"] <= 0)
            | (numeric["Close"] <= 0)
            | (numeric["High"] < numeric[["Open", "Close", "Low"]].max(axis=1))
            | (numeric["Low"] > numeric[["Open", "Close", "High"]].min(axis=1))
        )
        if invalid_ohlc.any():
            raise BacktestDataError(f"{label} requires valid OHLC")
        if (numeric["Volume"] < 0).any():
            raise BacktestDataError(f"{label} volume must not be negative")

    @staticmethod
    def _validate_adjustment_mode(
        frame: pd.DataFrame, label: str, required_mode: str
    ) -> None:
        modes = frame.attrs.get("adjustment_modes")
        if not isinstance(modes, tuple) or any(mode != required_mode for mode in modes):
            raise BacktestDataError(
                f"{label} adjustment mode does not match provider contract"
            )

    @staticmethod
    def _validate_unmixed_adjustment_modes(frame: pd.DataFrame, label: str) -> None:
        modes = frame.attrs.get("adjustment_modes")
        if not isinstance(modes, tuple) or len(set(modes)) > 1:
            raise BacktestDataError(f"{label} adjustment modes must not be mixed")
