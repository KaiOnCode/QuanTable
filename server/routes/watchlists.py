"""Watchlist and alert endpoints.

Alerts are stored locally and notify configured social channels on first trigger.
The check endpoint accepts optional snapshots for tests or fetches live data when
snapshots are omitted.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from notification import build_manager
from server.routes.settings import _load_settings

router = APIRouter(tags=["watchlists"])
logger = logging.getLogger("server.watchlists")

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
        logger.info(
            "watchlist_data_missing_using_defaults path=%s",
            WATCHLISTS_PATH,
        )
        return _default_data()
    with WATCHLISTS_PATH.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    logger.info(
        "watchlist_data_loaded path=%s watchlist_count=%s",
        WATCHLISTS_PATH,
        len(data.get("watchlists", [])),
    )
    return data


def _save_data(data: dict[str, Any]) -> None:
    WATCHLISTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with WATCHLISTS_PATH.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    logger.info(
        "watchlist_data_saved path=%s watchlist_count=%s alert_count=%s",
        WATCHLISTS_PATH,
        len(data.get("watchlists", [])),
        sum(len(watchlist.get("alerts", [])) for watchlist in data.get("watchlists", [])),
    )


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

    logger.info("watchlist_alert_live_snapshot_fetch_start ticker=%s", ticker)
    service = DataService()
    snapshot: dict[str, Any] = {}
    prices = service.df_get_prices(ticker, lookback_days=5)
    rows = prices.get("rows", []) if isinstance(prices, dict) else []
    if rows:
        snapshot["price"] = rows[-1].get("c")
    indicators = service.df_get_indicators(ticker, lookback_days=90)
    if isinstance(indicators, dict):
        snapshot["rsi14"] = indicators.get("rsi14")
    logger.info(
        "watchlist_alert_live_snapshot_fetch_done ticker=%s has_price=%s has_rsi14=%s snapshot=%s",
        ticker,
        snapshot.get("price") is not None,
        snapshot.get("rsi14") is not None,
        snapshot,
    )
    return snapshot


def _get_snapshot(ticker: str, snapshots: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    if snapshots:
        snapshot = snapshots.get(ticker) or snapshots.get(ticker.upper()) or {}
        logger.info(
            "watchlist_alert_snapshot_from_request ticker=%s found=%s snapshot=%s",
            ticker,
            bool(snapshot),
            snapshot,
        )
        return snapshot
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
        logger.warning(
            "watchlist_alert_create_rejected watchlist_id=%s ticker=%s alert_type=%s reason=unsupported_type",
            watchlist_id,
            request.ticker,
            request.type,
        )
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
    logger.info(
        "watchlist_alert_created watchlist_id=%s alert_id=%s ticker=%s alert_type=%s threshold=%s channels=%s",
        watchlist_id,
        alert["id"],
        ticker,
        request.type,
        request.threshold_value,
        request.notification_channels,
    )
    return alert


@router.post("/watchlists/check-alerts")
async def check_alerts(request: AlertCheckRequest | None = None):
    """Evaluate active alerts and notify when they trigger for the first time."""
    data = _load_data()
    req = request or AlertCheckRequest()
    manager = build_manager(_load_settings())
    triggered: list[dict[str, Any]] = []
    watchlists = data.get("watchlists", [])
    total_alerts = sum(len(watchlist.get("alerts", [])) for watchlist in watchlists)
    logger.info(
        "watchlist_alert_check_start watchlist_count=%s alert_count=%s request_snapshot_count=%s request_channels=%s",
        len(watchlists),
        total_alerts,
        len(req.snapshots or {}),
        req.channels,
    )

    for watchlist in watchlists:
        logger.info(
            "watchlist_alert_check_watchlist watchlist_id=%s name=%s ticker_count=%s alert_count=%s",
            watchlist.get("id"),
            watchlist.get("name"),
            len(watchlist.get("tickers", [])),
            len(watchlist.get("alerts", [])),
        )
        for alert in watchlist.get("alerts", []):
            logger.info(
                "watchlist_alert_evaluate_start watchlist_id=%s alert_id=%s ticker=%s alert_type=%s threshold=%s already_triggered=%s channels=%s",
                watchlist.get("id"),
                alert.get("id"),
                alert.get("ticker"),
                alert.get("type"),
                alert.get("threshold_value"),
                alert.get("is_triggered"),
                alert.get("notification_channels") or req.channels,
            )
            if alert.get("is_triggered"):
                logger.info(
                    "watchlist_alert_evaluate_skip alert_id=%s ticker=%s reason=already_triggered triggered_at=%s",
                    alert.get("id"),
                    alert.get("ticker"),
                    alert.get("triggered_at"),
                )
                continue
            snapshot = _get_snapshot(alert["ticker"], req.snapshots)
            matched, current_value = _is_triggered(alert, snapshot)
            logger.info(
                "watchlist_alert_evaluate_result alert_id=%s ticker=%s alert_type=%s threshold=%s current_value=%s matched=%s snapshot_keys=%s",
                alert.get("id"),
                alert.get("ticker"),
                alert.get("type"),
                alert.get("threshold_value"),
                current_value,
                matched,
                sorted(snapshot.keys()),
            )
            if not matched or current_value is None:
                logger.info(
                    "watchlist_alert_evaluate_skip alert_id=%s ticker=%s reason=%s",
                    alert.get("id"),
                    alert.get("ticker"),
                    "missing_metric" if current_value is None else "condition_not_met",
                )
                continue

            message = _alert_message(alert, current_value)
            channels = alert.get("notification_channels") or req.channels
            logger.info(
                "watchlist_alert_notify_start alert_id=%s ticker=%s title=%s priority=high channels=%s message=%s",
                alert.get("id"),
                alert.get("ticker"),
                f"Watchlist Alert: {alert['ticker']}",
                channels or "all_configured",
                message,
            )
            results = await manager.send(
                message=message,
                title=f"Watchlist Alert: {alert['ticker']}",
                priority="high",
                channels=channels,
            )
            logger.info(
                "watchlist_alert_notify_done alert_id=%s ticker=%s result_count=%s results=%s",
                alert.get("id"),
                alert.get("ticker"),
                len(results),
                {
                    name: {
                        "ok": result.ok,
                        "message": result.message,
                    }
                    for name, result in results.items()
                },
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
        logger.info(
            "watchlist_alert_check_persisted triggered_count=%s triggered_alert_ids=%s",
            len(triggered),
            [item["alert"].get("id") for item in triggered],
        )
    else:
        logger.info("watchlist_alert_check_no_triggers")

    logger.info(
        "watchlist_alert_check_done triggered_count=%s",
        len(triggered),
    )
    return {"triggered_count": len(triggered), "triggered": triggered}
