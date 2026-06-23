"""Daily Insights REST endpoints.

GET  /api/insights          — list recent briefs
GET  /api/insights/latest   — latest brief only
GET  /api/insights/{id}     — full brief detail
POST /api/insights/generate — SSE streaming brief generation
"""

from __future__ import annotations

import asyncio
import json
import logging
from queue import Empty, Queue
from threading import Thread

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from storage import get_store

router = APIRouter(tags=["insights"])
logger = logging.getLogger(__name__)


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/insights")
async def list_insights(limit: int = Query(20, ge=1, le=100)):
    briefs = get_store().list_daily_briefs(limit=limit)
    return {"insights": briefs, "total": len(briefs)}


@router.get("/insights/latest")
async def latest_insight():
    brief = get_store().get_latest_brief()
    return {"insight": brief} if brief else {"insight": None}


@router.get("/insights/{insight_id}")
async def get_insight(insight_id: str):
    brief = get_store().get_daily_brief(insight_id)
    if brief is None:
        raise HTTPException(404, "Brief not found")
    return brief


@router.post("/insights/generate")
async def generate_insight(hours: int = Query(0)):
    """SSE streaming brief generation with real-time progress."""

    async def event_stream():
        queue: Queue = Queue()

        def _worker():
            try:
                from server.morning_brief import run
                result = run(hours=hours, progress_queue=queue)
                queue.put(("done", result))
            except Exception as exc:
                queue.put(("error", str(exc)))

        thread = Thread(target=_worker, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()

        while True:
            try:
                msg_type, payload = await loop.run_in_executor(None, lambda: queue.get(timeout=300))
            except Empty:
                yield _sse_event("error", {"message": "Timeout after 5 minutes"})
                break

            if msg_type == "done":
                yield _sse_event("done", {"ok": True, **payload})
                break

            if msg_type == "error":
                yield _sse_event("error", {"message": str(payload)[:500]})
                break

            if msg_type == "progress":
                yield _sse_event("progress", payload)
                continue

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
