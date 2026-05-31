"""Health check and system status endpoints."""

import os
import time

from fastapi import APIRouter, Request

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
        "version": "1.0.0",
    }


@router.get("/data-sources/status")
async def data_source_status(request: Request):
    online = os.getenv("ONLINE_DATA", "true").lower() == "true"

    # Include collector status if running
    collector_info = None
    if hasattr(request.app.state, "collector"):
        collector_info = request.app.state.collector.status

    return {
        "online_mode": online,
        "collector": collector_info,
        "providers": {
            "yahoo_finance": {"status": "connected" if online else "disabled"},
            "google_news": {"status": "connected" if online else "disabled"},
            "akshare": {"status": "connected" if online else "disabled"},
            "finnhub": {
                "status": "connected"
                if online and os.getenv("FINNHUB_API_KEY")
                else "disabled"
            },
        },
    }
