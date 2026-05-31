"""Watchlist CRUD endpoints.

All data stored in system.db (watchlists table).
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["watchlists"])


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
    return {"id": watchlist_id, "name": name, "tickers": tickers, "notes": notes, "updated_at": now}


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(watchlist_id: str):
    """Delete a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    db.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
    return {"deleted": watchlist_id}


@router.post("/watchlists/{watchlist_id}/tickers")
async def add_ticker(watchlist_id: str, data: dict):
    """Add a ticker to a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = db.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")

    tickers = json.loads(row["tickers_json"])
    ticker = data.get("ticker", "").upper()
    if ticker and ticker not in tickers:
        tickers.append(ticker)

    now = _now()
    db.execute(
        "UPDATE watchlists SET tickers_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tickers), now, watchlist_id),
    )
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
    return {"tickers": tickers}
