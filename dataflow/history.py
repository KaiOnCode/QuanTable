from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dataflow.service import DataService
from dataflow.store import MarketDataStore


@dataclass(slots=True)
class DataServiceHistoryLoader:
    market_store: MarketDataStore
    _provenance: dict[tuple[str, str, str, int], dict[str, object]] = field(
        default_factory=dict,
        init=False,
    )

    @property
    def adjustment_mode(self) -> str:
        return "provider_adjusted_prices"

    @staticmethod
    def _safe_provider_timezone(value: object) -> str:
        if not isinstance(value, str):
            return "unknown"
        try:
            return ZoneInfo(value).key
        except (ValueError, ZoneInfoNotFoundError):
            return "unknown"

    def preload(
        self,
        ticker: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> None:
        start = date.fromisoformat(date_from)
        end_exclusive = date.fromisoformat(date_to) + timedelta(days=1)
        evaluation_days = (end_exclusive - start).days
        extra_days = math.ceil(warmup_bars * 7 / 5) + (7 if warmup_bars else 0)
        for _attempt in range(4):
            lookback_days = evaluation_days + extra_days
            data = DataService(market_store=self.market_store).df_get_prices(
                ticker,
                lookback_days=lookback_days,
                end_date=end_exclusive.isoformat(),
            )
            self._provenance[(ticker.upper(), date_from, date_to, warmup_bars)] = {
                "provider": "yfinance",
                "provider_timezone": self._safe_provider_timezone(data.get("tz")),
                "lookback_days": lookback_days,
                "provider_buffer_days": 100,
                "provider_end_semantics": "exclusive",
                "timezone_normalization": ("exchange_session_date_to_UTC_midnight"),
            }
            rows = data.get("rows", [])
            if rows:
                self.market_store.upsert_ohlcv(
                    ticker,
                    rows,
                    source="yfinance",
                    adjustment_mode=self.adjustment_mode,
                )
            available = self.market_store.get_ohlcv_tail(
                ticker,
                through_date=(start - timedelta(days=1)).isoformat(),
                limit=warmup_bars,
            )
            if len(available) >= warmup_bars:
                return
            extra_days = max(extra_days * 2, 14)

    def provenance_for(
        self,
        ticker: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> dict[str, object] | None:
        provenance = self._provenance.get(
            (ticker.upper(), date_from, date_to, warmup_bars)
        )
        return dict(provenance) if provenance is not None else None
