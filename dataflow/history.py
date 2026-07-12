from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dataflow.service import DataService
from dataflow.store import MarketDataStore


@dataclass(frozen=True, slots=True)
class DataServiceHistoryLoader:
    market_store: MarketDataStore

    def preload(self, ticker: str, date_from: str, date_to: str) -> None:
        start = date.fromisoformat(date_from)
        end_exclusive = date.fromisoformat(date_to) + timedelta(days=1)
        lookback_days = (end_exclusive - start).days
        data = DataService(market_store=self.market_store).df_get_prices(
            ticker,
            lookback_days=lookback_days,
            end_date=end_exclusive.isoformat(),
        )
        rows = data.get("rows", [])
        if rows:
            self.market_store.upsert_ohlcv(ticker, rows)
