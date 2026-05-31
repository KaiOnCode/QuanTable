"""Market Data REST endpoints.

Serve OHLCV, fundamentals, news, indicators, and ticker metadata
directly from MarketDataStore (SQLite). When data is missing, trigger
live fetch from YFinance and store to DB for future requests.

All endpoints follow: check DB → missing → live fetch + write → return.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from dataflow.store import MarketDataStore

router = APIRouter(tags=["market"])
logger = logging.getLogger(__name__)


def _store() -> MarketDataStore:
    return MarketDataStore()


def _default_start(days: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Prices ──────────────────────────────────────────────────


@router.get("/market/prices/{ticker}")
async def get_prices(
    ticker: str,
    start_date: str | None = Query(None, alias="start"),
    end_date: str | None = Query(None, alias="end"),
):
    """Get OHLCV bars for a ticker. Default: last 30 days.
    If DB has no data, fetches live from YFinance and stores.
    """
    start = start_date or _default_start(30)
    end = end_date or _today()

    store = _store()
    bars = store.get_ohlcv(ticker, start, end)

    # DB miss: live fetch + store + retry
    if not bars:
        try:
            from dataflow.service import DataService
            svc = DataService()
            svc.df_get_prices(ticker, lookback_days=90)
            bars = store.get_ohlcv(ticker, start, end)
        except Exception:
            pass

    return {
        "ticker": ticker.upper(),
        "start_date": start,
        "end_date": end,
        "count": len(bars),
        "bars": bars,
    }


# ── Fundamentals ────────────────────────────────────────────


@router.get("/market/fundamentals/{ticker}")
async def get_fundamentals(
    ticker: str,
    as_of_date: str | None = Query(None, alias="date"),
):
    """Get the latest fundamentals snapshot for a ticker."""
    store = _store()
    data = store.get_fundamentals(ticker, as_of_date)

    # DB miss: live fetch + store + retry
    if data is None:
        try:
            from dataflow.service import DataService
            svc = DataService()
            svc.df_get_fundamentals(ticker)
            data = store.get_fundamentals(ticker, as_of_date)
        except Exception:
            pass

    return {
        "ticker": ticker.upper(),
        "as_of_date": data.get("as_of_date") if data else None,
        "fundamentals": data,
    }


# ── News ────────────────────────────────────────────────────


@router.get("/market/news/{ticker}")
async def get_news(
    ticker: str,
    window_days: int = Query(7, ge=1, le=90, alias="days"),
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent news articles for a ticker."""
    articles = _store().get_news(ticker, window_days=window_days)

    # DB miss: live fetch + store + retry
    if not articles:
        try:
            from dataflow.service import DataService
            svc = DataService()
            svc.df_get_news(ticker, window_days=window_days, max_items=10)
            articles = _store().get_news(ticker, window_days=window_days)
        except Exception:
            pass

    return {
        "ticker": ticker.upper(),
        "window_days": window_days,
        "count": len(articles),
        "articles": articles[:limit],
    }


# ── News Search ─────────────────────────────────────────────


@router.get("/market/search")
async def search_news(
    q: str = Query(..., min_length=1, description="FTS5 search query"),
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Full-text search across all news articles."""
    results = _store().search_news(q, ticker=ticker, limit=limit)
    return {
        "query": q,
        "ticker": ticker,
        "count": len(results),
        "results": results,
    }


# ── Stats ───────────────────────────────────────────────────


@router.get("/market/stats")
async def get_market_stats():
    """Get summary statistics about stored market data."""
    return _store().get_stats()


# ── Ticker Metadata ─────────────────────────────────────────


@router.get("/market/meta")
async def get_ticker_meta(tickers: str = Query("")):
    """Get metadata (company name, currency, country, exchange) for tickers.
    Accepts comma-separated: ?tickers=AAPL,0700.HK
    Missing tickers are fetched live from YFinance and stored.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"meta": {}}

    store = _store()
    meta = store.get_ticker_meta_batch(ticker_list)

    # Find missing tickers and fetch live
    missing = [t for t in ticker_list if meta.get(t) is None]
    if missing:
        try:
            import yfinance as yf
            for t in missing:
                try:
                    info = yf.Ticker(t).info
                    store.upsert_ticker_meta(
                        t,
                        name=info.get("longName") or "",
                        short_name=info.get("shortName") or "",
                        sector=info.get("sector") or "",
                        industry=info.get("industry") or "",
                        market=info.get("market") or "",
                        exchange=info.get("exchange") or "",
                        currency=info.get("currency") or "",
                        country=info.get("country") or "",
                    )
                except Exception:
                    pass
            # Re-query to include freshly written data
            meta = store.get_ticker_meta_batch(ticker_list)
        except Exception:
            pass

    return {"meta": {t: meta.get(t) for t in ticker_list}}


# ── Indicators ──────────────────────────────────────────────


@router.get("/market/indicators/{ticker}")
async def get_indicators(ticker: str):
    """Get latest technical indicators (RSI, MACD, SMA, ATR).
    Fetches live OHLCV from YFinance, computes indicators, and
    stores the OHLCV data to DB so the prices endpoint benefits.
    """
    try:
        from dataflow.providers.YFinance import df_get_indicators
        result = df_get_indicators(ticker, lookback_days=30)

        # Store fetched OHLCV in DB so prices endpoint hits cache next time
        _try_store_indicators_ohlcv(ticker, result)

        macd = result.get("macd", {}) or {}
        ma = result.get("ma", {}) or {}
        return {
            "ticker": ticker.upper(),
            "rsi14": float(result["rsi14"]) if result.get("rsi14") is not None else None,
            "macd_signal": "bullish" if macd.get("hist", 0) > 0 else "bearish",
            "sma20": float(ma["sma20"]) if ma.get("sma20") is not None else None,
            "sma50": float(ma["sma50"]) if ma.get("sma50") is not None else None,
            "atr14": float(result["atr20"]) if result.get("atr20") is not None else None,
        }
    except Exception:
        return {"ticker": ticker.upper(), "rsi14": None, "macd_signal": None}


def _try_store_indicators_ohlcv(ticker: str, result: dict):
    """Extract OHLCV data from indicator result and store to DB.
    df_get_indicators internally calls _get_price_history which returns
    a DataFrame. We store the raw OHLCV for the prices endpoint.
    """
    try:
        rows = result.get("_ohlcv_rows")
        if not rows:
            return
        store = MarketDataStore()
        store.upsert_ohlcv(ticker, rows)
    except Exception:
        pass
