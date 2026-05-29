"""Periodic data collector — scheduled market data accumulation.

Runs via APScheduler (in-process). Fetches and caches market data,
news sentiment, and macro events on configurable intervals.

Implements the periodic fetching described in docs/architecture.md §10.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from dataflow.cache import invalidate_cache, cache_key

logger = logging.getLogger(__name__)

# Default watch list for periodic data collection
DEFAULT_WATCH_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "SPY", "QQQ",
]

DEFAULT_SCHEDULES = {
    "price_cache": {"interval_minutes": 15},
    "news_cache": {"interval_minutes": 30},
    "sentiment_cache": {"interval_minutes": 60},
    "macro_cache": {"interval_minutes": 60, "on_startup": False},
}


class DataCollector:
    """Background data collector using APScheduler.

    Usage:
        collector = DataCollector()
        collector.start()
        # ... app runs ...
        collector.stop()
    """

    def __init__(
        self,
        tickers: list[str] | None = None,
        schedules: dict | None = None,
    ):
        self.tickers = tickers or DEFAULT_WATCH_TICKERS
        self.schedules = schedules or DEFAULT_SCHEDULES
        self._scheduler: BackgroundScheduler | None = None
        self._running = False

    def start(self) -> None:
        """Start the background scheduler."""
        if self._running:
            return

        self._scheduler = BackgroundScheduler(
            timezone="UTC",
            job_defaults={"misfire_grace_time": 300, "coalesce": True},
        )

        # Price refresh
        price_interval = self.schedules["price_cache"]["interval_minutes"]
        self._scheduler.add_job(
            self._refresh_prices,
            IntervalTrigger(minutes=price_interval),
            id="refresh_prices",
            name="Refresh price cache",
            replace_existing=True,
        )

        # News cache refresh
        news_interval = self.schedules["news_cache"]["interval_minutes"]
        self._scheduler.add_job(
            self._refresh_news,
            IntervalTrigger(minutes=news_interval),
            id="refresh_news",
            name="Refresh news cache",
            replace_existing=True,
        )

        # Sentiment refresh
        sent_interval = self.schedules["sentiment_cache"]["interval_minutes"]
        self._scheduler.add_job(
            self._refresh_sentiment,
            IntervalTrigger(minutes=sent_interval),
            id="refresh_sentiment",
            name="Refresh sentiment cache",
            replace_existing=True,
        )

        # Macro calendar refresh (daily at 8:00 UTC)
        self._scheduler.add_job(
            self._refresh_macro,
            CronTrigger(hour=8, minute=0),
            id="refresh_macro",
            name="Refresh macro calendar",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        logger.info(
            "DataCollector started — %d tickers, price every %dm, news every %dm",
            len(self.tickers),
            price_interval,
            news_interval,
        )

    def stop(self) -> None:
        """Stop the background scheduler."""
        if self._scheduler and self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("DataCollector stopped")

    # ── Refresh jobs ────────────────────────────────────────

    def _refresh_prices(self) -> None:
        """Fetch latest prices for stale tickers first, then all watched."""
        from dataflow.service import DataService
        from dataflow.store import MarketDataStore
        svc = DataService()
        store = MarketDataStore()

        # Prioritize stale tickers (no data in 24h)
        stale = set(store.get_stale_tickers("ohlcv", max_age_hours=24))
        prioritized = list(stale) + [t for t in self.tickers if t not in stale]

        count = 0
        for ticker in prioritized:
            try:
                result = svc.df_get_prices(ticker, lookback_days=5)
                if result:
                    count += 1
            except Exception as exc:
                store.mark_error(ticker, "ohlcv", str(exc))
                logger.debug("price refresh failed for %s: %s", ticker, exc)
        logger.debug("price refresh: %d/%d tickers updated (%d stale)", count, len(prioritized), len(stale))

    def _refresh_news(self) -> None:
        """Fetch and store news for watched tickers."""
        from dataflow.service import DataService
        svc = DataService()
        count = 0
        for ticker in self.tickers:
            try:
                articles = svc.df_get_news(ticker, window_days=1, max_items=10)
                if articles:
                    count += 1
            except Exception:
                pass
        logger.debug("news refresh: %d/%d tickers with new articles", count, len(self.tickers))

    def _refresh_sentiment(self) -> None:
        """Pre-compute sentiment for watched tickers."""
        from dataflow.providers.sentiment import df_get_sentiment
        count = 0
        for ticker in self.tickers:
            try:
                result = df_get_sentiment(ticker, window_days=7, force_refresh=True)
                if result.get("article_count", 0) > 0:
                    count += 1
            except Exception as exc:
                logger.debug("sentiment refresh failed for %s: %s", ticker, exc)
        logger.debug("sentiment refresh: %d/%d tickers", count, len(self.tickers))

    def _refresh_macro(self) -> None:
        """Refresh macro calendar cache."""
        from dataflow.service import DataService
        svc = DataService()
        try:
            svc.df_get_macro_calendar(window_days=14)
            logger.debug("macro calendar refreshed")
        except Exception as exc:
            logger.debug("macro refresh failed: %s", exc)

    @property
    def status(self) -> dict:
        """Return collector status for API/UI."""
        return {
            "running": self._running,
            "tickers": self.tickers,
            "ticker_count": len(self.tickers),
            "schedules": self.schedules,
        }
