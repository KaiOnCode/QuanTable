from __future__ import annotations

from collections.abc import Sequence
import re
from typing import Final

from dataflow.store import MarketDataStore
from scanner.models import TrackedTicker, UniverseSource
from storage.store import ContextStore

TICKER_PATTERN: Final = re.compile(r"^\^?[A-Z0-9]+(?:[.-][A-Z0-9]+)*$")


class UnsupportedUniverseError(ValueError):
    pass


class TrackedUniverseResolver:
    def __init__(
        self, context_store: ContextStore, market_store: MarketDataStore
    ) -> None:
        self._context_store = context_store
        self._market_store = market_store

    def resolve(self, universe: str | None = None) -> tuple[TrackedTicker, ...]:
        if universe is not None and universe.strip().lower() != "tracked":
            raise UnsupportedUniverseError("only the tracked universe is supported")
        provenance: dict[str, set[UniverseSource]] = {}
        for strategy in self._context_store.list_strategies():
            tickers = strategy.get("tickers", [])
            if isinstance(tickers, list):
                self._add_tickers(
                    provenance,
                    [ticker for ticker in tickers if isinstance(ticker, str)],
                    UniverseSource.STRATEGY,
                )
        self._add_tickers(
            provenance,
            self._context_store.list_watchlist_tickers(),
            UniverseSource.WATCHLIST,
        )
        self._add_tickers(
            provenance,
            self._market_store.list_known_tickers(),
            UniverseSource.MARKET_STORE,
        )
        return tuple(
            TrackedTicker(
                ticker=ticker,
                provenance=tuple(sorted(sources, key=lambda source: source.value)),
            )
            for ticker, sources in sorted(provenance.items())
        )

    @staticmethod
    def _add_tickers(
        provenance: dict[str, set[UniverseSource]],
        values: Sequence[str],
        source: UniverseSource,
    ) -> None:
        for value in values:
            if ticker := TrackedUniverseResolver._normalize_ticker(value):
                provenance.setdefault(ticker, set()).add(source)

    @staticmethod
    def _normalize_ticker(value: str) -> str | None:
        ticker = value.strip().upper()
        return ticker if TICKER_PATTERN.fullmatch(ticker) else None
