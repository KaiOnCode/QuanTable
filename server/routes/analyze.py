"""POST /api/analyze — SSE streaming analysis endpoint.

Calls the LangGraph orchestrator via stream() and emits per-agent
progress events in real-time as each agent completes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

HISTORY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "history"

# Map node name → report key in state
_AGENT_REPORT_KEYS: dict[str, str] = {
    "market_analyst": "market_report",
    "news_analyst": "news_report",
    "fundamentals_analyst": "fundamental_report",
    "risk_analyst": "risk_report",
    "PM_agent": "PM_report",
}

_AGENT_LABELS: dict[str, str] = {
    "market_analyst": "Market Analyst",
    "news_analyst": "News Analyst",
    "fundamentals_analyst": "Fundamentals Analyst",
    "risk_analyst": "Risk Analyst",
    "PM_agent": "PM Decision",
}


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL")
    date: str | None = Field(None, description="ISO 8601 date for historical analysis")
    current_position_pct: float = Field(0.0, ge=-100.0, le=100.0)
    mode: str = Field(
        "standard", pattern="^(fast|standard|deep)$"
    )
    active_agents: list[str] | None = None
    beliefs: list[str] = []
    debate_rounds: int = Field(2, ge=0, le=5)
    enable_debate: bool = False
    enable_cross_review: bool = False


def _sse_event(event: str, data: dict) -> str:
    """Format an SSE event."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _save_session_json(session_id: str, ticker: str, mode: str, result: dict) -> None:
    """Persist session to data/history/{session_id}.json."""
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "session_id": session_id,
            "ticker": ticker,
            "mode": mode,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "request": {"ticker": ticker, "mode": mode},
            "result": result,
        }
        path = HISTORY_DIR / f"{session_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, default=str, indent=2))
        logger.debug("Session saved: %s", path)
    except Exception:
        logger.warning("Failed to save session %s", session_id, exc_info=True)


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """Start a new analysis. Returns SSE stream with real-time progress events."""

    async def event_stream():
        session_id = str(uuid.uuid4())
        started_at = time.time()

        # Emit initial progress
        yield _sse_event("progress", {
            "agent": "system",
            "status": "started",
            "session_id": session_id,
            "ticker": request.ticker,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

        # ── Run stream in thread, consume via queue ──
        queue: Queue = Queue()

        def _stream_worker():
            try:
                from agentgraph.orchestrator import IntelliFin_Assistant

                analysis_date = request.date or time.strftime("%Y-%m-%dT00:00:00Z")

                assistant = IntelliFin_Assistant()
                for event in assistant.stream(
                    request.ticker,
                    date=analysis_date,
                    current_position_pct=request.current_position_pct,
                    session_id=session_id,
                ):
                    queue.put(("event", event))
                queue.put(("done", None))
            except Exception as exc:
                queue.put(("error", str(exc)))

        thread = Thread(target=_stream_worker, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()
        final_result: dict[str, Any] = {}
        seen_reports: set[str] = set()

        while True:
            try:
                msg_type, payload = await loop.run_in_executor(None, lambda: queue.get(timeout=120))
            except Empty:
                logger.warning("Stream timeout for %s", session_id)
                break

            if msg_type == "done":
                break

            if msg_type == "error":
                logger.exception("Analysis failed for %s: %s", request.ticker, payload)
                yield _sse_event("error", {
                    "agent": "orchestrator",
                    "error": str(payload)[:500],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
                return

            # msg_type == "event": {node_name: {key: value, ...}}
            if msg_type != "event":
                continue

            if isinstance(payload, dict):
                for node_name, update in payload.items():
                    if not isinstance(update, dict):
                        continue
                    # Merge all recognized keys into final result
                    for k, v in update.items():
                        if k in _AGENT_REPORT_KEYS.values() or k in ("Action", "Target_position_pct"):
                            final_result[k] = v
                    # Emit progress when an agent produces its report
                    report_key = _AGENT_REPORT_KEYS.get(node_name)
                    if report_key and update.get(report_key) and node_name not in seen_reports:
                        seen_reports.add(node_name)
                        report_text = update[report_key]
                        yield _sse_event("progress", {
                            "agent": node_name,
                            "status": "completed",
                            "report": report_text,
                            "duration_ms": 0,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        })
                        logger.debug("Agent %s completed (%d chars)", node_name, len(report_text))

        # ── After stream completes: build and emit result ──
        pm_report = final_result.get("PM_report", "")
        action = final_result.get("Action", "HOLD")
        direction, confidence, timeframe = _parse_pm_report(pm_report, action)

        # Build agent reports map
        agent_reports = {}
        for agent_name, report_key in _AGENT_REPORT_KEYS.items():
            report = final_result.get(report_key, "")
            if report:
                agent_reports[agent_name] = report

        # Fetch news articles
        news_articles = []
        try:
            from dataflow.service import DataService
            svc = DataService()
            news_articles = svc.get_news(request.ticker, window_days=7)
        except Exception:
            pass

        elapsed = round(time.time() - started_at, 2)

        result_payload = {
            "session_id": session_id,
            "action": action,
            "direction": direction,
            "confidence": confidence,
            "timeframe": timeframe,
            "report": pm_report,
            "agent_reports": agent_reports,
            "target_position_pct": float(final_result.get("Target_position_pct", 0)),
            "debate_records": final_result.get("debate_history", []),
            "news_articles": [
                {"title": a["title"], "source": a.get("source_name", ""),
                 "url": a.get("url", ""), "published_at": a.get("published_at", "")}
                for a in news_articles[:8]
            ],
            "elapsed_s": elapsed,
        }

        yield _sse_event("result", result_payload)

        # ── Persist to history ──
        _save_session_json(session_id, request.ticker, request.mode, result_payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _parse_pm_report(report: str, action: str) -> tuple[str, float, str]:
    """Extract direction, confidence, and timeframe from PM output.

    PM reports use free-form text. We map Action → direction and
    extract confidence from the content.
    """
    import re

    # Map canonical action to direction
    action_map = {"BUY": "Bullish", "SELL": "Bearish", "HOLD": "Neutral"}
    direction = action_map.get(action.upper(), "Neutral")

    # Try to extract confidence from report text
    confidence = 0.5  # default
    # Look for patterns like "置信度: 0.70" or "confidence: 0.65"
    conf_match = re.search(r"(?:置信度|confidence)[:\s]*([0-9]*\.?[0-9]+)", report, re.IGNORECASE)
    if conf_match:
        try:
            confidence = float(conf_match.group(1))
        except ValueError:
            pass

    # Extract timeframe from report
    timeframe = ""
    tf_match = re.search(r"时间范围[:\s]*(intraday|1-3d|1-4w|long-term)", report)
    if tf_match:
        timeframe = tf_match.group(1)

    return direction, confidence, timeframe


# ── History endpoints ──────────────────────────────────────


@router.get("/analyze/history")
async def list_history(limit: int = 20):
    """List past analysis sessions."""
    items = []
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(HISTORY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text())
                items.append({
                    "session_id": data.get("session_id"),
                    "ticker": data.get("ticker"),
                    "mode": data.get("mode"),
                    "created_at": data.get("created_at"),
                    "action": data.get("result", {}).get("action"),
                    "direction": data.get("result", {}).get("direction"),
                    "confidence": data.get("result", {}).get("confidence"),
                    "oneliner": _extract_oneliner(data.get("result", {}).get("report", "")),
                })
            except Exception:
                continue
    except Exception:
        pass
    return {"items": items, "total": len(items)}


@router.get("/analyze/history/{session_id}")
async def get_history(session_id: str):
    """Get full session data."""
    from fastapi import HTTPException
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "Session not found")
    return json.loads(path.read_text())


@router.delete("/analyze/history/{session_id}")
async def delete_history(session_id: str):
    """Delete a past analysis session."""
    from fastapi import HTTPException
    path = HISTORY_DIR / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, "Session not found")
    path.unlink()
    return {"ok": True}


def _extract_oneliner(report: str) -> str:
    """Extract one-line summary from PM report."""
    import re
    match = re.search(r"(?:一句话结论)[：:]\s*(.+)", report)
    if match:
        return match.group(1).strip()
    # Fallback: first non-empty line
    for line in report.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and len(line) > 10:
            return line[:120]
    return ""
