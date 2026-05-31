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
        scheduler: BackgroundScheduler | None = None,
    ):
        self.tickers = tickers or DEFAULT_WATCH_TICKERS
        self.schedules = schedules or DEFAULT_SCHEDULES
        self._scheduler = scheduler
        self._owns_scheduler = scheduler is None
        self._running = False

    def start(self) -> None:
        """Start the background scheduler."""
        if self._running:
            return

        if self._scheduler is None:
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

        # Discovery job: LLM-driven related ticker discovery (every 4h)
        self._discovery_tickers: list[str] = []
        self._scheduler.add_job(
            self._refresh_discovery,
            IntervalTrigger(hours=4),
            id="refresh_discovery",
            name="Refresh discovery pool",
            replace_existing=True,
        )

        if self._owns_scheduler:
            self._scheduler.start()
        self._running = True
        logger.info(
            "DataCollector started — %d tickers, price every %dm, news every %dm",
            len(self._get_active_tickers()),
            price_interval,
            news_interval,
        )

    def stop(self) -> None:
        """Stop the background scheduler (if we own it)."""
        if self._scheduler and self._running and self._owns_scheduler:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info("DataCollector stopped")

    # ── Refresh jobs ────────────────────────────────────────

    def _get_active_tickers(self) -> list[str]:
        """Return all tickers that should be refreshed: default + watchlist."""
        tickers = set(self.tickers)
        try:
            import json
            from storage import get_store
            db = get_store()._system_db()
            db.execute(
                "CREATE TABLE IF NOT EXISTS watchlists (id TEXT, tickers_json TEXT DEFAULT '[]')"
            )
            rows = db.execute("SELECT tickers_json FROM watchlists").fetchall()
            for r in rows:
                try:
                    tickers.update(json.loads(r[0]))
                except Exception:
                    pass
        except Exception:
            pass
        return list(tickers)

    def _refresh_prices(self) -> None:
        """Fetch latest prices for stale tickers first, then all watched."""
        from dataflow.service import DataService
        from dataflow.store import MarketDataStore
        svc = DataService()
        store = MarketDataStore()

        active = self._get_active_tickers()
        # Prioritize stale tickers (no data in 24h)
        stale = set(store.get_stale_tickers("ohlcv", max_age_hours=24))
        prioritized = list(stale & set(active)) + [t for t in active if t not in stale]

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
        active = self._get_active_tickers()
        count = 0
        for ticker in active:
            try:
                articles = svc.df_get_news(ticker, window_days=1, max_items=10)
                if articles:
                    count += 1
            except Exception:
                pass
        logger.debug("news refresh: %d/%d tickers with new articles", count, len(self._get_active_tickers()))

    def _refresh_sentiment(self) -> None:
        """Pre-compute sentiment for watched tickers."""
        from dataflow.providers.sentiment import df_get_sentiment
        active = self._get_active_tickers()
        count = 0
        for ticker in active:
            try:
                result = df_get_sentiment(ticker, window_days=7, force_refresh=True)
                if result.get("article_count", 0) > 0:
                    count += 1
            except Exception as exc:
                logger.debug("sentiment refresh failed for %s: %s", ticker, exc)
        logger.debug("sentiment refresh: %d/%d tickers", count, len(self._get_active_tickers()))

    def _refresh_macro(self) -> None:
        """Refresh macro calendar cache."""
        from dataflow.service import DataService
        svc = DataService()
        try:
            svc.df_get_macro_calendar(window_days=14)
            logger.debug("macro calendar refreshed")
        except Exception as exc:
            logger.debug("macro refresh failed: %s", exc)

    def _refresh_discovery(self) -> None:
        """LLM-driven discovery: find related tickers based on user context.

        Reads watchlist + recent decisions → LLM suggests new tickers.
        New tickers are added to discovery pool for lazy data collection.
        """
        try:
            from agentgraph.discovery import discover_related_tickers, gather_user_interests
            from storage import get_store
            from dataflow.store import MarketDataStore
            import sqlite3, json, os

            # Gather user interests from watchlists + decisions
            watchlist_tickers: list[str] = []
            decision_tickers: list[str] = []

            # Read watchlists from system.db
            try:
                store = get_store()
                db = store._system_db()
                db.execute("CREATE TABLE IF NOT EXISTS watchlists (id TEXT, tickers_json TEXT DEFAULT '[]')")
                rows = db.execute("SELECT tickers_json FROM watchlists").fetchall()
                for r in rows:
                    tickers = json.loads(r[0]) if r[0] else []
                    watchlist_tickers.extend(tickers)
            except Exception:
                pass

            # Read recent decision tickers
            try:
                decisions = store.get_decisions("default", limit=20)
                decision_tickers = list({d.get("ticker", "") for d in decisions if d.get("ticker")})
            except Exception:
                pass

            interests = gather_user_interests(
                list(set(watchlist_tickers)),
                decision_tickers,
            )

            # Get recent headlines
            news_store = MarketDataStore()
            headlines: list[str] = []
            try:
                news_articles = news_store.get_news(
                    next(iter(set(watchlist_tickers + decision_tickers)), "AAPL"),
                    window_days=3,
                )
                headlines = [a.get("title", "") for a in news_articles[:10]]
            except Exception:
                pass

            if not interests and not headlines:
                logger.debug("Discovery skipped: no interests or headlines")
                return

            # Call LLM
            suggestions = discover_related_tickers(interests, headlines, max_suggestions=5)
            if not suggestions:
                return

            # Add to discovery pool (avoid duplicates with active pool)
            existing = set(self.tickers)
            new_count = 0
            for s in suggestions:
                ticker = s["ticker"]
                if ticker not in existing and ticker not in self._discovery_tickers:
                    self._discovery_tickers.append(ticker)
                    new_count += 1
                    logger.info(
                        "Discovery: +%s (reason: %s, priority: %d)",
                        ticker, s.get("reason", ""), s.get("priority", 2),
                    )

            # Lazy-fetch light data for new discovery tickers
            if new_count > 0:
                from dataflow.service import DataService
                svc = DataService()
                for ticker in self._discovery_tickers[-new_count:]:
                    try:
                        svc.df_get_prices(ticker, lookback_days=5)
                        logger.debug("Discovery: fetched prices for %s", ticker)
                    except Exception:
                        pass

        except Exception as exc:
            logger.warning("Discovery refresh failed: %s", exc)

    @property
    def status(self) -> dict:
        """Return collector status for API/UI."""
        return {
            "running": self._running,
            "tickers": self.tickers,
            "ticker_count": len(self._get_active_tickers()),
            "discovery_tickers": getattr(self, "_discovery_tickers", []),
            "discovery_count": len(getattr(self, "_discovery_tickers", [])),
            "schedules": self.schedules,
        }


class MonitorRunner:
    """Scheduled execution of MonitorTasks.

    Periodically reads active monitor tasks from system.db and executes them
    according to their configured frequency. Uses the same APScheduler instance
    as the DataCollector.
    """

    def __init__(self, scheduler: BackgroundScheduler):
        self._scheduler = scheduler
        self._job_ids: set[str] = set()

    def start(self) -> None:
        # Register a master refresh job that picks up new/changed tasks
        self._scheduler.add_job(
            self._refresh_and_run,
            IntervalTrigger(minutes=5),
            id="monitor_master",
            name="MonitorTask master refresh",
            replace_existing=True,
        )
        logger.info("MonitorRunner started (refresh every 5 min)")

    def stop(self) -> None:
        for jid in list(self._job_ids):
            try:
                self._scheduler.remove_job(jid)
            except Exception:
                pass
        self._job_ids.clear()
        logger.info("MonitorRunner stopped")

    def _refresh_and_run(self) -> None:
        """Read active tasks from DB and trigger those due to run."""
        try:
            from storage import get_store
            store = get_store()
            tasks = store.list_monitors(status="active")
        except Exception as exc:
            logger.warning("MonitorRunner: failed to read tasks: %s", exc)
            return

        now = datetime.now(timezone.utc)
        for task in tasks:
            if not self._should_run(task, now):
                continue
            self._execute(task)

    def _should_run(self, task: dict, now) -> bool:
        """Check if a task is due to run based on its schedule."""
        schedule = task.get("schedule", {})
        freq = schedule.get("frequency", "daily")
        last_run = task.get("last_run_at")

        if not last_run:
            return True  # Never run before

        try:
            last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        except Exception:
            return True

        since_minutes = (now - last_dt).total_seconds() / 60

        if freq == "hourly":
            return since_minutes >= 55
        elif freq == "daily":
            time_str = schedule.get("time", "09:00")
            target_hour, target_min = map(int, time_str.split(":"))
            return (
                since_minutes >= 20 * 60  # At least 20h since last run
                and now.hour >= target_hour
                and now.minute >= target_min
            )
        elif freq == "weekly":
            return since_minutes >= 6 * 24 * 60  # Roughly a week
        return False

    def _execute(self, task: dict) -> None:
        """Execute one monitor task in a background thread."""
        import threading

        def _run():
            try:
                # Touch last_run first to avoid duplicate execution
                store = get_store()
                store.touch_monitor_run(task["id"])

                # Import and execute
                from server.routes.monitor import _execute_monitor_task
                report = _execute_monitor_task(task)
                report["monitor_id"] = task["id"]
                rid = store.save_monitoring_report(report)
                logger.info(
                    "MonitorRunner: executed %s → report %s (%d findings)",
                    task.get("name", ""), rid[:8], len(report.get("key_findings", [])),
                )
            except Exception as exc:
                logger.warning("MonitorRunner: execution failed for %s: %s",
                              task.get("name", ""), exc)

        threading.Thread(target=_run, daemon=True).start()
