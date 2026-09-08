"""Watchlist CRUD endpoints.

All data stored in system.db (watchlists table).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from notification import build_manager
from server.routes.settings import _load_settings
from storage import get_store

router = APIRouter(tags=["watchlists"])
logger = logging.getLogger(__name__)
SUPPORTED_ALERT_TYPES = {"price_above", "price_below", "rsi_above", "rsi_below"}


class CreateAlertRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    type: str
    threshold_value: float | str
    notification_channels: list[str] | None = None


class AlertCheckRequest(BaseModel):
    snapshots: dict[str, dict[str, Any]] | None = None
    channels: list[str] | None = None


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _init_watchlists_table():
    """Ensure watchlists table exists in system.db."""
    db = get_store()._system_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS watchlists (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tickers_json TEXT DEFAULT '[]',
            notes_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watchlist_alerts (
            id TEXT PRIMARY KEY,
            watchlist_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            threshold_value TEXT NOT NULL,
            message TEXT DEFAULT '',
            notification_channels_json TEXT DEFAULT '[]',
            is_triggered INTEGER DEFAULT 0,
            triggered_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_watchlist
            ON watchlist_alerts(watchlist_id);
        CREATE INDEX IF NOT EXISTS idx_watchlist_alerts_triggered
            ON watchlist_alerts(is_triggered);
    """)
    db.commit()


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _json_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except Exception:
        return []
    return decoded if isinstance(decoded, list) else []


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _alert_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    alert = dict(row)
    alert["notification_channels"] = _json_list(
        alert.pop("notification_channels_json", "[]")
    )
    alert["threshold_value"] = _coerce_threshold(alert.get("threshold_value"))
    alert["is_triggered"] = bool(alert.get("is_triggered"))
    return alert


def _list_alerts(db: sqlite3.Connection, watchlist_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT * FROM watchlist_alerts WHERE watchlist_id = ? ORDER BY created_at DESC",
        (watchlist_id,),
    ).fetchall()
    return [_alert_to_dict(row) for row in rows]


def _watchlist_to_dict(row: sqlite3.Row, db: sqlite3.Connection) -> dict[str, Any]:
    watchlist = dict(row)
    watchlist["tickers"] = _json_list(watchlist.pop("tickers_json", "[]"))
    watchlist["notes"] = _json_dict(watchlist.pop("notes_json", "{}"))
    watchlist["alerts"] = _list_alerts(db, watchlist["id"])
    return watchlist


def _coerce_threshold(value: Any) -> float | str:
    try:
        return float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)


def _get_watchlist_row(db: sqlite3.Connection, watchlist_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"Watchlist {watchlist_id} not found")
    return row


def _alert_message(alert: dict[str, Any], current_value: float) -> str:
    metric = "price" if str(alert["type"]).startswith("price") else "RSI(14)"
    direction = "above" if str(alert["type"]).endswith("above") else "below"
    return (
        f"{alert['ticker']} {metric} is {current_value:.2f}, "
        f"{direction} alert threshold {float(alert['threshold_value']):.2f}."
    )


def _snapshot_value(alert: dict[str, Any], snapshot: dict[str, Any]) -> float | None:
    alert_type = str(alert.get("type", ""))
    if alert_type.startswith("price"):
        value = snapshot.get("price") or snapshot.get("last") or snapshot.get("c")
    elif alert_type.startswith("rsi"):
        value = snapshot.get("rsi14") or snapshot.get("rsi")
    else:
        value = None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_triggered(
    alert: dict[str, Any], snapshot: dict[str, Any]
) -> tuple[bool, float | None]:
    value = _snapshot_value(alert, snapshot)
    if value is None:
        return False, None
    threshold = float(alert["threshold_value"])
    if str(alert["type"]).endswith("above"):
        return value > threshold, value
    return value < threshold, value


def _fetch_live_snapshot(ticker: str) -> dict[str, Any]:
    from dataflow.service import DataService

    service = DataService()
    snapshot: dict[str, Any] = {}
    prices = service.df_get_prices(ticker, lookback_days=5)
    rows = prices.get("rows", []) if isinstance(prices, dict) else []
    if rows:
        last = rows[-1]
        snapshot["price"] = last.get("c") or last.get("close")
    indicators = service.df_get_indicators(ticker, lookback_days=90)
    if isinstance(indicators, dict):
        snapshot["rsi14"] = indicators.get("rsi14") or indicators.get("rsi")
    return snapshot


def _get_snapshot(
    ticker: str,
    snapshots: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    if snapshots:
        return snapshots.get(ticker) or snapshots.get(ticker.upper()) or {}
    return _fetch_live_snapshot(ticker)


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

            svc = DataService()
            svc.get_prices(ticker, _today_minus(90))
            svc.get_fundamentals(ticker)
            svc.get_news(ticker, window_days=7)
            svc.get_meta(ticker)
            logger.info("Background fetch complete for %s", ticker)
        except Exception as exc:
            logger.warning("Background fetch failed for %s: %s", ticker, exc)

    threading.Thread(target=_fetch, daemon=True).start()


def _today_minus(days: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# ── CRUD ────────────────────────────────────────────────────


@router.get("/watchlists")
async def list_watchlists():
    """List all watchlists."""
    _init_watchlists_table()
    db = get_store()._system_db()
    rows = db.execute("SELECT * FROM watchlists ORDER BY updated_at DESC").fetchall()
    result = [_watchlist_to_dict(row, db) for row in rows]
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
    return {
        "id": wid,
        "name": name,
        "tickers": tickers,
        "alerts": [],
        "notes": {},
        "created_at": now,
        "updated_at": now,
    }


@router.get("/watchlists/{watchlist_id}")
async def get_watchlist(watchlist_id: str):
    """Get a single watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = _get_watchlist_row(db, watchlist_id)
    return _watchlist_to_dict(row, db)


@router.put("/watchlists/{watchlist_id}")
async def update_watchlist(watchlist_id: str, data: dict):
    """Update a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    existing = _get_watchlist_row(db, watchlist_id)

    name = data.get("name", existing["name"])
    tickers = data.get("tickers", json.loads(existing["tickers_json"]))
    notes = data.get("notes", json.loads(existing["notes_json"]))
    now = _now()

    db.execute(
        "UPDATE watchlists SET name = ?, tickers_json = ?, notes_json = ?, updated_at = ? WHERE id = ?",
        (name, json.dumps(tickers), json.dumps(notes), now, watchlist_id),
    )
    db.commit()
    return {
        "id": watchlist_id,
        "name": name,
        "tickers": tickers,
        "alerts": _list_alerts(db, watchlist_id),
        "notes": notes,
        "updated_at": now,
    }


@router.delete("/watchlists/{watchlist_id}")
async def delete_watchlist(watchlist_id: str):
    """Delete a watchlist."""
    _init_watchlists_table()
    db = get_store()._system_db()
    db.execute("DELETE FROM watchlist_alerts WHERE watchlist_id = ?", (watchlist_id,))
    db.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
    db.commit()
    return {"deleted": watchlist_id}


@router.post("/watchlists/{watchlist_id}/tickers")
async def add_ticker(watchlist_id: str, data: dict):
    """Add a ticker to a watchlist. Triggers on-demand data fetch for new tickers."""
    _init_watchlists_table()
    db = get_store()._system_db()
    row = _get_watchlist_row(db, watchlist_id)

    tickers = json.loads(row["tickers_json"])
    ticker = _normalize_ticker(data.get("ticker", ""))
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
    row = _get_watchlist_row(db, watchlist_id)

    tickers = json.loads(row["tickers_json"])
    ticker_upper = _normalize_ticker(ticker)
    if ticker_upper in tickers:
        tickers.remove(ticker_upper)

    now = _now()
    db.execute(
        "UPDATE watchlists SET tickers_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tickers), now, watchlist_id),
    )
    db.commit()
    return {"tickers": tickers}


@router.post("/watchlists/{watchlist_id}/alerts")
async def create_alert(watchlist_id: str, request: CreateAlertRequest):
    """Create a watchlist alert in the existing SQLite-backed watchlist store."""
    if request.type not in SUPPORTED_ALERT_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported alert type '{request.type}'."
        )

    _init_watchlists_table()
    db = get_store()._system_db()
    row = _get_watchlist_row(db, watchlist_id)
    ticker = _normalize_ticker(request.ticker)
    tickers = _json_list(row["tickers_json"])
    if ticker not in tickers:
        tickers.append(ticker)
        db.execute(
            "UPDATE watchlists SET tickers_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tickers), _now(), watchlist_id),
        )
        _fetch_ticker_data(ticker)

    now = _now()
    alert_id = str(uuid.uuid4())
    threshold = _coerce_threshold(request.threshold_value)
    alert_message = f"{ticker} {request.type.replace('_', ' ')} {float(threshold):.2f}"
    db.execute(
        """INSERT INTO watchlist_alerts
           (id, watchlist_id, ticker, type, threshold_value, message,
            notification_channels_json, is_triggered, triggered_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)""",
        (
            alert_id,
            watchlist_id,
            ticker,
            request.type,
            str(threshold),
            alert_message,
            json.dumps(request.notification_channels or []),
            now,
        ),
    )
    db.commit()
    row = db.execute(
        "SELECT * FROM watchlist_alerts WHERE id = ?", (alert_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Alert was not persisted.")
    return _alert_to_dict(row)


@router.post("/watchlists/check-alerts")
async def check_alerts(request: AlertCheckRequest | None = None):
    """Evaluate active watchlist alerts and publish notification events once."""
    _init_watchlists_table()
    db = get_store()._system_db()
    req = request or AlertCheckRequest()
    manager = build_manager(_load_settings())
    triggered: list[dict[str, Any]] = []

    rows = db.execute(
        "SELECT * FROM watchlist_alerts WHERE is_triggered = 0 ORDER BY created_at ASC"
    ).fetchall()
    for row in rows:
        alert = _alert_to_dict(row)
        snapshot = _get_snapshot(str(alert["ticker"]), req.snapshots)
        matched, current_value = _is_triggered(alert, snapshot)
        if not matched or current_value is None:
            continue

        message = _alert_message(alert, current_value)
        channels = alert.get("notification_channels") or req.channels
        results = await manager.send(
            message=message,
            title=f"Watchlist Alert: {alert['ticker']}",
            priority="high",
            channels=channels,
        )
        triggered_at = _now()
        db.execute(
            """UPDATE watchlist_alerts
               SET is_triggered = 1, triggered_at = ?, message = ?
               WHERE id = ?""",
            (triggered_at, message, alert["id"]),
        )
        alert["is_triggered"] = True
        alert["triggered_at"] = triggered_at
        alert["message"] = message
        triggered.append(
            {
                "alert": alert,
                "current_value": current_value,
                "notification_results": {
                    name: {
                        "channel": result.channel,
                        "ok": result.ok,
                        "message": result.message,
                    }
                    for name, result in results.items()
                },
            }
        )

    if triggered:
        db.commit()

    return {"triggered_count": len(triggered), "triggered": triggered}
