"""Watchlist CRUD endpoints.

All data stored in system.db (watchlists table).
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["watchlists"])
logger = logging.getLogger(__name__)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _init_watchlists_table():
    """Ensure watchlists table exists in system.db."""
    db = get_store()._system_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS watchlists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tickers_json TEXT DEFAULT '[]',
            notes_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)


def _fetch_ticker_data(ticker: str):
    """Fetch data for a newly added ticker in background thread.
    API returns immediately; data appears when fetch completes.
    Also fetches company name/metadata for display.
    Supports US stocks, HK (.HK), and A-shares (.SS/.SZ).
    """
    import threading

    def _fetch():
        try:
            from dataflow.service import DataService
            from dataflow.store import MarketDataStore
            svc = DataService()
            svc.df_get_prices(ticker, lookback_days=90)
            svc.df_get_fundamentals(ticker)
            svc.df_get_news(ticker, window_days=7, max_items=10)

            # Fetch company name & metadata from YFinance
            try:
                import yfinance as yf
                info = yf.Ticker(ticker).info
                store = MarketDataStore()
                store.upsert_ticker_meta(
                    ticker,
                    name=info.get("longName") or "",
                    short_name=info.get("shortName") or "",
                    sector=info.get("sector") or "",
                    industry=info.get("industry") or "",
                    market=info.get("market") or "",
                    exchange=info.get("exchange") or "",
                    currency=info.get("currency") or "",
                    country=info.get("country") or "",
                )
                logger.info("Meta: %s (%s %s)",
                    info.get("longName") or info.get("shortName") or "",
                    info.get("currency") or "",
                    info.get("country") or "",
                )
            except Exception:
                pass

            logger.info("Background fetch complete for %s", ticker)
        except Exception as exc:
            logger.warning("Background fetch failed for %s: %s", ticker, exc)

    threading.Thread(target=_fetch, daemon=True).start()


# ── CRUD ────────────────────────────────────────────────────


@router.get("/watchlists")
async def list_watchlists():
    """List all watchlists."""
    _init_watchlists_table()
    db = get_store()._system_db()
    rows = db.execute(
        "SELECT * FROM watchlists ORDER BY updated_at DESC"
    ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["tickers"] = json.loads(d.pop("tickers_json", "[]"))
        d["notes"] = json.loads(d.pop("notes_json", "{}"))
        result.append(d)
    return {"watchlists": result, "total": len(result)}


@router.post("/watchlists", status_code=201)
async def create_watchlist(data: dict):
    """Create a new watchlist."""
    _init_watchlists_table()
    wid = str(uuid.uuid4())
    now = _now()
    name = data.get("name", "Untitled Watchlist")
    tickers = data.get("tickers", [])

    db = get_store()._system_db()
    db.execute(
        """INSERT INTO watchlists (id, name, tickers_json, notes_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (wid, name, json.dumps(tickers), json.dumps(data.get("notes", {})), now, now),
    )
    db.commit()
    return {"id": wid, "name": name, "tickers": tickers, "notes": {}, "created_at": now, "updated_at": now}


@router.get("/watchlists/{watchlist_id}")
async def get_watchlist(watchlist_id: str):
    """Get a single watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = db.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    d = dict(row)
    d["tickers"] = json.loads(d.pop("tickers_json", "[]"))
    d["notes"] = json.loads(d.pop("notes_json", "{}"))
    return d


@router.put("/watchlists/{watchlist_id}")
async def update_watchlist(watchlist_id: str, data: dict):
    """Update a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    existing = db.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
    if existing is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")

    name = data.get("name", existing["name"])
    tickers = data.get("tickers", json.loads(existing["tickers_json"]))
    notes = data.get("notes", json.loads(existing["notes_json"]))
    now = _now()

    db.execute(
        "UPDATE watchlists SET name = ?, tickers_json = ?, notes_json = ?, updated_at = ? WHERE id = ?",
        (name, json.dumps(tickers), json.dumps(notes), now, watchlist_id),
    )
    db.commit()
    return {"id": watchlist_id, "name": name, "tickers": tickers, "notes": notes, "updated_at": now}


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(watchlist_id: str):
    """Delete a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    db.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
    db.commit()
    return {"deleted": watchlist_id}


@router.post("/watchlists/{watchlist_id}/tickers")
async def add_ticker(watchlist_id: str, data: dict):
    """Add a ticker to a watchlist. Triggers on-demand data fetch for new tickers."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = db.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")

    tickers = json.loads(row["tickers_json"])
    ticker = data.get("ticker", "").upper()
    if ticker and ticker not in tickers:
        tickers.append(ticker)

        # Trigger on-demand data fetch for the new ticker
        _fetch_ticker_data(ticker)

    now = _now()
    db.execute(
        "UPDATE watchlists SET tickers_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tickers), now, watchlist_id),
    )
    db.commit()
    return {"tickers": tickers}


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}")
async def remove_ticker(watchlist_id: str, ticker: str):
    """Remove a ticker from a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = db.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")

    tickers = json.loads(row["tickers_json"])
    ticker_upper = ticker.upper()
    if ticker_upper in tickers:
        tickers.remove(ticker_upper)

    now = _now()
    db.execute(
        "UPDATE watchlists SET tickers_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tickers), now, watchlist_id),
    )
    db.commit()
    return {"tickers": tickers}
