"""Watchlist and alert endpoints.

Alerts are stored locally and notify configured social channels on first trigger.
The check endpoint accepts optional snapshots for tests or fetches live data when
snapshots are omitted.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from notification import build_manager
from server.routes.settings import _load_settings

router = APIRouter(tags=["watchlists"])

WATCHLISTS_PATH = Path("data/watchlists.json")
SUPPORTED_ALERT_TYPES = {
    "price_above",
    "price_below",
    "rsi_above",
    "rsi_below",
}


class WatchlistCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    tickers: list[str] = Field(default_factory=list)


class AddTickerRequest(BaseModel):
    ticker: str = Field(..., min_length=1)


class CreateAlertRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    type: str
    threshold_value: float | str
    notification_channels: list[str] | None = None


class AlertCheckRequest(BaseModel):
    snapshots: dict[str, dict[str, Any]] | None = None
    channels: list[str] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _default_data() -> dict[str, Any]:
    now = _now()
    return {
        "watchlists": [
            {
                "id": "my-positions",
                "name": "My Positions",
                "tickers": ["AAPL", "MSFT", "NVDA"],
                "alerts": [],
                "notes": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "ai-stocks",
                "name": "AI Stocks",
                "tickers": ["NVDA", "AMD", "SMCI", "GOOGL"],
                "alerts": [],
                "notes": {},
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "dividend",
                "name": "Dividend",
                "tickers": ["JPM", "XOM"],
                "alerts": [],
                "notes": {},
                "created_at": now,
                "updated_at": now,
            },
        ]
    }


def _load_data() -> dict[str, Any]:
    if not WATCHLISTS_PATH.exists():
        return _default_data()
    with WATCHLISTS_PATH.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _save_data(data: dict[str, Any]) -> None:
    WATCHLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with WATCHLISTS_PATH.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def _find_watchlist(data: dict[str, Any], watchlist_id: str) -> dict[str, Any]:
    for watchlist in data.get("watchlists", []):
        if watchlist["id"] == watchlist_id:
            return watchlist
    raise HTTPException(status_code=404, detail=f"Watchlist '{watchlist_id}' not found.")


def _alert_message(alert: dict[str, Any], current_value: float) -> str:
    metric = "price" if alert["type"].startswith("price") else "RSI(14)"
    direction = "above" if alert["type"].endswith("above") else "below"
    return (
        f"{alert['ticker']} {metric} is {current_value:.2f}, "
        f"{direction} alert threshold {float(alert['threshold_value']):.2f}."
    )


def _snapshot_value(alert: dict[str, Any], snapshot: dict[str, Any]) -> float | None:
    if alert["type"].startswith("price"):
        value = snapshot.get("price") or snapshot.get("last") or snapshot.get("c")
    elif alert["type"].startswith("rsi"):
        value = snapshot.get("rsi14") or snapshot.get("rsi")
    else:
        value = None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_triggered(alert: dict[str, Any], snapshot: dict[str, Any]) -> tuple[bool, float | None]:
    value = _snapshot_value(alert, snapshot)
    if value is None:
        return False, None
    threshold = float(alert["threshold_value"])
    if alert["type"].endswith("above"):
        return value > threshold, value
    return value < threshold, value


def _fetch_live_snapshot(ticker: str) -> dict[str, Any]:
    """Fetch minimal live data lazily to keep tests independent from market libs."""
    from dataflow.service import DataService

    service = DataService()
    snapshot: dict[str, Any] = {}
    prices = service.df_get_prices(ticker, lookback_days=5)
    rows = prices.get("rows", []) if isinstance(prices, dict) else []
    if rows:
        snapshot["price"] = rows[-1].get("c")
    indicators = service.df_get_indicators(ticker, lookback_days=90)
    if isinstance(indicators, dict):
        snapshot["rsi14"] = indicators.get("rsi14")
    return snapshot


def _get_snapshot(ticker: str, snapshots: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    if snapshots:
        return snapshots.get(ticker) or snapshots.get(ticker.upper()) or {}
    return _fetch_live_snapshot(ticker)


@router.get("/watchlists")
async def list_watchlists():
    return _load_data().get("watchlists", [])


@router.post("/watchlists")
async def create_watchlist(request: WatchlistCreateRequest):
    data = _load_data()
    now = _now()
    watchlist = {
        "id": str(uuid.uuid4()),
        "name": request.name,
        "tickers": [_normalize_ticker(ticker) for ticker in request.tickers],
        "alerts": [],
        "notes": {},
        "created_at": now,
        "updated_at": now,
    }
    data.setdefault("watchlists", []).append(watchlist)
    _save_data(data)
    return watchlist


@router.get("/watchlists/{watchlist_id}")
async def get_watchlist(watchlist_id: str):
    return _find_watchlist(_load_data(), watchlist_id)


@router.post("/watchlists/{watchlist_id}/tickers")
async def add_ticker(watchlist_id: str, request: AddTickerRequest):
    data = _load_data()
    watchlist = _find_watchlist(data, watchlist_id)
    ticker = _normalize_ticker(request.ticker)
    if ticker not in watchlist["tickers"]:
        watchlist["tickers"].append(ticker)
    watchlist["updated_at"] = _now()
    _save_data(data)
    return {"ok": True}


@router.delete("/watchlists/{watchlist_id}/tickers/{ticker}")
async def remove_ticker(watchlist_id: str, ticker: str):
    data = _load_data()
    watchlist = _find_watchlist(data, watchlist_id)
    watchlist["tickers"] = [item for item in watchlist["tickers"] if item != _normalize_ticker(ticker)]
    watchlist["updated_at"] = _now()
    _save_data(data)
    return {"ok": True}


@router.post("/watchlists/{watchlist_id}/alerts")
async def create_alert(watchlist_id: str, request: CreateAlertRequest):
    if request.type not in SUPPORTED_ALERT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported alert type '{request.type}'.")

    data = _load_data()
    watchlist = _find_watchlist(data, watchlist_id)
    ticker = _normalize_ticker(request.ticker)
    if ticker not in watchlist["tickers"]:
        watchlist["tickers"].append(ticker)
    now = _now()
    alert = {
        "id": str(uuid.uuid4()),
        "watchlist_id": watchlist_id,
        "ticker": ticker,
        "type": request.type,
        "threshold_value": request.threshold_value,
        "message": "",
        "notification_channels": request.notification_channels or None,
        "is_triggered": False,
        "triggered_at": None,
        "created_at": now,
    }
    alert["message"] = (
        f"{ticker} {request.type.replace('_', ' ')} "
        f"{float(request.threshold_value):.2f}"
    )
    watchlist["alerts"].append(alert)
    watchlist["updated_at"] = now
    _save_data(data)
    return alert


@router.post("/watchlists/check-alerts")
async def check_alerts(request: AlertCheckRequest | None = None):
    """Evaluate active alerts and notify when they trigger for the first time."""
    data = _load_data()
    req = request or AlertCheckRequest()
    manager = build_manager(_load_settings())
    triggered: list[dict[str, Any]] = []

    for watchlist in data.get("watchlists", []):
        for alert in watchlist.get("alerts", []):
            if alert.get("is_triggered"):
                continue
            snapshot = _get_snapshot(alert["ticker"], req.snapshots)
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
            alert["is_triggered"] = True
            alert["triggered_at"] = _now()
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
        _save_data(data)

    return {"triggered_count": len(triggered), "triggered": triggered}
