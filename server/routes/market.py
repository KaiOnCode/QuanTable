"""Market Data REST endpoints.

All data access through DataService — no direct DB reads, no provider calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from dataflow.service import DataService

router = APIRouter(tags=["market"])


def _svc() -> DataService:
    return DataService()


def _default_start(days: int = 30) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@router.get("/market/prices/{ticker}")
async def get_prices(
    ticker: str,
    start_date: str | None = Query(None, alias="start"),
    end_date: str | None = Query(None, alias="end"),
):
    start = start_date or _default_start(30)
    end = end_date or _today()
    bars = _svc().get_prices(ticker, start, end)
    return {"ticker": ticker.upper(), "start_date": start, "end_date": end, "count": len(bars), "bars": bars}


@router.get("/market/fundamentals/{ticker}")
async def get_fundamentals(ticker: str, as_of_date: str | None = Query(None, alias="date")):
    data = _svc().get_fundamentals(ticker, as_of_date)
    return {"ticker": ticker.upper(), "as_of_date": data.get("as_of_date") if data else None, "fundamentals": data}


@router.get("/market/news/{ticker}")
async def get_news(ticker: str, window_days: int = Query(7, ge=1, le=90, alias="days"), limit: int = Query(20, ge=1, le=100)):
    articles = _svc().get_news(ticker, window_days=window_days)
    return {"ticker": ticker.upper(), "window_days": window_days, "count": len(articles), "articles": articles[:limit]}


@router.get("/market/search")
async def search_news(q: str = Query(..., min_length=1), ticker: str | None = Query(None), limit: int = Query(20, ge=1, le=100)):
    results = _svc().search_news(q, ticker=ticker, limit=limit)
    return {"query": q, "ticker": ticker, "count": len(results), "results": results}


@router.get("/market/stats")
async def get_market_stats():
    return _svc().store.get_stats()


@router.get("/market/meta")
async def get_ticker_meta(tickers: str = Query("")):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return {"meta": {}}
    svc = _svc()
    meta = {}
    for t in ticker_list:
        meta[t] = svc.get_meta(t)
    return {"meta": meta}


@router.get("/market/indicators/{ticker}")
async def get_indicators(ticker: str):
    result = _svc().get_indicators(ticker)
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
