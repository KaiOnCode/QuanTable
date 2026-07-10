from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import assert_never

from dataflow.store import MarketDataStore
from scanner.models import (
    ScanCondition,
    ScanField,
    ScanOperator,
    ScanResponse,
    ScanResult,
    ScannerSnapshot,
    SnapshotValue,
)
from scanner.universe import TrackedUniverseResolver


class ScannerServiceError(ValueError):
    pass


class ScannerSnapshotBuilder:
    def __init__(self, market_store: MarketDataStore) -> None:
        self._market_store = market_store

    def build(self, ticker: str) -> ScannerSnapshot:
        bars = self._market_store.get_ohlcv(ticker, "0001-01-01", "9999-12-31")
        fundamentals = self._market_store.get_fundamentals(ticker)
        metadata = self._market_store.get_ticker_meta(ticker)
        currency = self._text(metadata, "currency")
        latest = bars[-1] if bars else None
        previous = bars[-2] if len(bars) >= 2 else None
        latest_close = self._number(latest, "close")
        previous_close = self._number(previous, "close")
        change_pct = self._change_pct(latest_close, previous_close)
        closes = [self._number(bar, "close") for bar in bars]
        complete_closes = [close for close in closes if close is not None]
        ohlcv_source = self._source("ohlcv", self._text(latest, "source"))
        ohlcv_as_of = self._text(latest, "date")
        fundamental_source = self._source(
            "fundamentals", self._text(fundamentals, "source")
        )
        fundamental_as_of = self._text(fundamentals, "as_of_date")
        return ScannerSnapshot(
            ticker=ticker,
            price=self._value(
                latest_close, "ticker_currency", currency, ohlcv_source, ohlcv_as_of
            ),
            change_pct=self._value(
                change_pct, "percentage_points", currency, ohlcv_source, ohlcv_as_of
            ),
            volume=self._value(
                self._number(latest, "volume"),
                "shares",
                currency,
                ohlcv_source,
                ohlcv_as_of,
            ),
            rsi14=self._value(
                self._rsi14(complete_closes),
                "0_to_100",
                currency,
                ohlcv_source,
                ohlcv_as_of,
            ),
            sma20=self._value(
                self._sma(complete_closes, 20),
                "ticker_currency",
                currency,
                ohlcv_source,
                ohlcv_as_of,
            ),
            sma50=self._value(
                self._sma(complete_closes, 50),
                "ticker_currency",
                currency,
                ohlcv_source,
                ohlcv_as_of,
            ),
            pe_ratio=self._value(
                self._number(fundamentals, "pe"),
                "multiple",
                currency,
                fundamental_source,
                fundamental_as_of,
            ),
            pb_ratio=self._value(
                self._number(fundamentals, "pb"),
                "multiple",
                currency,
                fundamental_source,
                fundamental_as_of,
            ),
            market_cap=self._value(
                self._number(fundamentals, "market_cap"),
                "absolute_currency",
                currency,
                fundamental_source,
                fundamental_as_of,
            ),
            sector=self._value(
                self._text(metadata, "sector"),
                "string",
                currency,
                "ticker_meta" if metadata else None,
                self._text(metadata, "fetched_at"),
            ),
        )

    @staticmethod
    def _value(
        value: float | str | None,
        unit: str,
        currency: str | None,
        source: str | None,
        as_of: str | None,
    ) -> SnapshotValue:
        return SnapshotValue(
            value=value, unit=unit, currency=currency, source=source, as_of=as_of
        )

    @staticmethod
    def _source(data_type: str, source: str | None) -> str | None:
        return f"{data_type}:{source}" if source else None

    @staticmethod
    def _number(record: dict | None, key: str) -> float | None:
        if record is None:
            return None
        value = record.get(key)
        if not isinstance(value, int | float):
            return None
        parsed = float(value)
        return parsed if isfinite(parsed) else None

    @staticmethod
    def _text(record: dict | None, key: str) -> str | None:
        if record is None:
            return None
        value = record.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _change_pct(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return (current - previous) / previous * 100

    @staticmethod
    def _sma(closes: list[float], window: int) -> float | None:
        if len(closes) < window:
            return None
        return sum(closes[-window:]) / window

    @staticmethod
    def _rsi14(closes: list[float]) -> float | None:
        if len(closes) < 15:
            return None
        changes = [
            later - earlier
            for earlier, later in zip(closes[-15:-1], closes[-14:], strict=True)
        ]
        gain = sum(change for change in changes if change > 0) / 14
        loss = -sum(change for change in changes if change < 0) / 14
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        return 100 - 100 / (1 + gain / loss)


class ScannerService:
    def __init__(
        self, universe_resolver: TrackedUniverseResolver, market_store: MarketDataStore
    ) -> None:
        self._universe_resolver = universe_resolver
        self._snapshot_builder = ScannerSnapshotBuilder(market_store)

    def scan(
        self, conditions: tuple[ScanCondition, ...], universe: str | None = None
    ) -> ScanResponse:
        if not conditions:
            raise ScannerServiceError("at least one scan condition is required")
        tracked = self._universe_resolver.resolve(universe)
        results: list[ScanResult] = []
        warnings: list[str] = []
        missing_data_count = 0
        for tracked_ticker in tracked:
            snapshot = self._snapshot_builder.build(tracked_ticker.ticker)
            missing = tuple(
                condition.field
                for condition in conditions
                if snapshot.value_for(condition.field).value is None
            )
            if missing:
                missing_data_count += 1
                warnings.append(
                    f"{tracked_ticker.ticker}: missing {', '.join(field.value for field in missing)}"
                )
                continue
            if not all(self._matches(snapshot, condition) for condition in conditions):
                continue
            source_dates = {
                field.value: value.as_of
                for field in ScanField
                if (value := snapshot.value_for(field)).as_of is not None
            }
            results.append(
                ScanResult(
                    ticker=tracked_ticker.ticker,
                    match_score=float(len(conditions)),
                    matched_conditions=conditions,
                    snapshot=snapshot,
                    provenance=tracked_ticker.provenance,
                    source_dates=source_dates,
                )
            )
        results.sort(key=lambda result: (-result.match_score, result.ticker))
        return ScanResponse(
            universe=tracked,
            results=tuple(results),
            scanned_count=len(tracked),
            matched_count=len(results),
            missing_data_count=missing_data_count,
            warnings=tuple(warnings),
            scanned_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _matches(snapshot: ScannerSnapshot, condition: ScanCondition) -> bool:
        observed = snapshot.value_for(condition.field).value
        if condition.field == ScanField.SECTOR:
            return isinstance(observed, str) and observed == condition.value
        if not isinstance(observed, float) or not isinstance(condition.value, float):
            return False
        match condition.operator:
            case ScanOperator.LESS_THAN:
                return observed < condition.value
            case ScanOperator.GREATER_THAN:
                return observed > condition.value
            case ScanOperator.LESS_THAN_OR_EQUAL:
                return observed <= condition.value
            case ScanOperator.GREATER_THAN_OR_EQUAL:
                return observed >= condition.value
            case ScanOperator.EQUAL:
                return observed == condition.value
            case ScanOperator.BETWEEN:
                return (
                    isinstance(condition.value2, float)
                    and condition.value <= observed <= condition.value2
                )
            case unreachable:
                assert_never(unreachable)
