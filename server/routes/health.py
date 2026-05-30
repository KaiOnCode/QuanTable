"""Health check and system status endpoints."""

import os
import time

from fastapi import APIRouter

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
async def data_source_status():
    online = os.getenv("ONLINE_DATA", "true").lower() == "true"
    return {
        "online_mode": online,
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
