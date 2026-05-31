"""Market Data REST endpoints.

Serve OHLCV, fundamentals, and news directly from MarketDataStore (SQLite).
Fast, synchronous, no agent involved.

GET  /api/market/prices/:ticker       — OHLCV bars
GET  /api/market/fundamentals/:ticker — latest fundamentals snapshot
GET  /api/market/news/:ticker         — recent news articles
GET  /api/market/search               — FTS5 full-text search on news
GET  /api/market/stats                — data volume summary
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from dataflow.store import MarketDataStore

router = APIRouter(tags=["market"])


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
    """Get OHLCV bars for a ticker. Default: last 30 days."""
    start = start_date or _default_start(30)
    end = end_date or _today()

    bars = _store().get_ohlcv(ticker, start, end)
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
    data = _store().get_fundamentals(ticker, as_of_date)
    if data is None:
        return {
            "ticker": ticker.upper(),
            "fundamentals": None,
            "message": f"No fundamentals data for {ticker.upper()}",
        }
    return {
        "ticker": ticker.upper(),
        "as_of_date": data.get("as_of_date"),
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
