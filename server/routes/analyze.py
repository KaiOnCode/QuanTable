"""POST /api/analyze — SSE streaming analysis endpoint.

Calls the LangGraph orchestrator via stream() and emits per-agent
progress events in real-time as each agent completes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from memory.service import memory_enabled as is_memory_enabled
from server import analysis_runs
from server.routes.settings import _load_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])

# Map node name → report key in state
_AGENT_REPORT_KEYS: dict[str, str] = {
    "market_analyst": "market_report",
    "sentiment_analyst": "sentiment_report",
    "news_analyst": "news_report",
    "fundamentals_analyst": "fundamental_report",
    "bull_researcher": "investment_debate_state",
    "bear_researcher": "investment_debate_state",
    "research_manager": "investment_plan",
    "trader": "trader_proposal",
    "aggressive_analyst": "risk_debate_state",
    "conservative_analyst": "risk_debate_state",
    "neutral_analyst": "risk_debate_state",
    "risk_analyst": "risk_report",
    "PM_agent": "PM_report",
}

_AGENT_LABELS: dict[str, str] = {
    "market_analyst": "Market Analyst",
    "sentiment_analyst": "Sentiment Analyst",
    "news_analyst": "News Analyst",
    "fundamentals_analyst": "Fundamentals Analyst",
    "bull_researcher": "Bull Researcher",
    "bear_researcher": "Bear Researcher",
    "research_manager": "Research Manager",
    "trader": "Trader",
    "aggressive_analyst": "Aggressive Risk",
    "conservative_analyst": "Conservative Risk",
    "neutral_analyst": "Neutral Risk",
    "risk_analyst": "Risk Analyst",
    "PM_agent": "PM Decision",
}


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol, e.g. AAPL")
    date: str | None = Field(None, description="ISO 8601 date for historical analysis")
    current_position_pct: float = Field(0.0, ge=-100.0, le=100.0)
    strategy_id: str = Field(
        "default", description="Strategy identity for HITL context"
    )
    account_id: str = Field("default", description="Account identity for HITL context")
    decision_id: str | None = Field(
        None, description="Optional caller-provided decision identity"
    )
    mode: str = Field("standard", pattern="^(fast|standard|deep)$")
    active_agents: list[str] | None = None
    beliefs: list[str] = []
    debate_rounds: int = Field(2, ge=0, le=5)
    enable_debate: bool = False
    enable_cross_review: bool = False


def _sse_event(event: str, data: dict) -> str:
    """Format an SSE event."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """Start a new analysis. Returns SSE stream with real-time progress events."""
    session_id = str(uuid.uuid4())
    decision_id = request.decision_id or str(uuid.uuid4())
    started_at = time.time()
    try:
        analysis_memory_enabled = is_memory_enabled(
            _load_settings().get("memory_enabled", True)
        )
    except Exception:
        logger.warning("Failed to load memory setting; using env/default")
        analysis_memory_enabled = is_memory_enabled()

    analysis_runs.create_running_snapshot(
        session_id=session_id,
        ticker=request.ticker,
        mode=request.mode,
        request_payload=_request_payload(request),
    )
    analysis_runs.create_run(session_id)
    subscriber = analysis_runs.subscribe_run(session_id)
    asyncio.create_task(
        _execute_analysis_run(
            request=request,
            session_id=session_id,
            decision_id=decision_id,
            started_at=started_at,
            analysis_memory_enabled=analysis_memory_enabled,
        )
    )

    return StreamingResponse(
        _event_stream_from_queue(subscriber),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analyze/runs/{session_id}/events")
async def subscribe_analysis_run(session_id: str):
    if not analysis_runs.has_run(session_id):
        raise HTTPException(404, "Session not found")
    return StreamingResponse(
        _event_stream_from_queue(analysis_runs.subscribe_run(session_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _request_payload(request: AnalyzeRequest) -> dict[str, object]:
    if hasattr(request, "model_dump"):
        return request.model_dump()
    return request.dict()


async def _event_stream_from_queue(
    queue: analysis_runs.SubscriberQueue,
):
    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, queue.get)
        if item is None:
            break
        event_name, payload = item
        yield _sse_event(event_name, payload)


def _publish_progress(session_id: str, payload: dict[str, Any]) -> None:
    analysis_runs.record_progress(session_id, payload)
    analysis_runs.publish_run_event(session_id, ("progress", payload))


async def _execute_analysis_run(
    *,
    request: AnalyzeRequest,
    session_id: str,
    decision_id: str,
    started_at: float,
    analysis_memory_enabled: bool,
) -> None:
    try:
        _publish_progress(
            session_id,
            {
                "agent": "system",
                "status": "started",
                "session_id": session_id,
                "ticker": request.ticker,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )

        queue: Queue = Queue()

        def _stream_worker() -> None:
            try:
                analysis_date = request.date or time.strftime("%Y-%m-%dT00:00:00Z")
                for event in analysis_runs.run_orchestrator_stream(
                    ticker=request.ticker,
                    date=analysis_date,
                    current_position_pct=request.current_position_pct,
                    strategy_id=request.strategy_id,
                    session_id=session_id,
                    memory_enabled=analysis_memory_enabled,
                    account_id=request.account_id,
                    decision_id=decision_id,
                    mode=request.mode,
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
                msg_type, payload = await loop.run_in_executor(
                    None, lambda: queue.get(timeout=120)
                )
            except Empty:
                message = f"Analysis timed out for {session_id}"
                logger.warning(message)
                await _fail_analysis_run(request, session_id, message)
                return

            if msg_type == "done":
                break

            if msg_type == "error":
                logger.error("Analysis failed for %s: %s", request.ticker, payload)
                await _fail_analysis_run(request, session_id, str(payload))
                return

            if msg_type != "event" or not isinstance(payload, dict):
                continue

            for node_name, update in payload.items():
                if not isinstance(update, dict):
                    continue

                # Handle _started marker (from on_node_start callback)
                if update.get("_started"):
                    if node_name in _AGENT_REPORT_KEYS:
                        _publish_progress(session_id, {
                            "agent": node_name,
                            "status": "started",
                            "report": "",
                            "duration_ms": 0,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        })
                    continue

                # Only process agent nodes (not tool/clear nodes)
                if node_name not in _AGENT_REPORT_KEYS:
                    continue

                # Publish "completed" when agent produces its report
                report_key = _AGENT_REPORT_KEYS[node_name]
                if update.get(report_key) and node_name not in seen_reports:
                    seen_reports.add(node_name)
                    report_text = update[report_key]
                    _publish_progress(session_id, {
                        "agent": node_name,
                        "status": "completed",
                        "report": report_text,
                        "duration_ms": 0,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    logger.debug(
                        "Agent %s completed (%d chars)", node_name, len(report_text)
                    )

                for key, value in update.items():
                    if key in _AGENT_REPORT_KEYS.values() or key in (
                        "Action",
                        "Target_position_pct",
                        "memory_record_id",
                    ):
                        final_result[key] = value

                # Publish "completed" when agent produces its report
                report_key = _AGENT_REPORT_KEYS[node_name]
                if update.get(report_key) and node_name not in seen_reports:
                    seen_reports.add(node_name)
                    report_text = update[report_key]
                    _publish_progress(session_id, {
                        "agent": node_name,
                        "status": "completed",
                        "report": report_text,
                        "duration_ms": 0,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    })
                    logger.debug(
                        "Agent %s completed (%d chars)", node_name, len(report_text)
                    )

        result_payload = await _build_result_payload(
            request=request,
            session_id=session_id,
            decision_id=decision_id,
            started_at=started_at,
            analysis_memory_enabled=analysis_memory_enabled,
            final_result=final_result,
        )
        analysis_runs.complete_snapshot(session_id, result_payload)
        analysis_runs.publish_run_event(session_id, ("result", result_payload))
        await _notify_analysis_completed(request, result_payload)
    except Exception as exc:
        logger.exception("Analysis run crashed for %s", session_id)
        await _fail_analysis_run(request, session_id, str(exc))
    finally:
        analysis_runs.close_run(session_id)


async def _fail_analysis_run(
    request: AnalyzeRequest,
    session_id: str,
    error: str,
) -> None:
    message = error[:500]
    analysis_runs.fail_snapshot(session_id, message)
    analysis_runs.publish_run_event(
        session_id,
        (
            "error",
            {
                "agent": "orchestrator",
                "error": message,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ),
    )
    await _notify_analysis_failed(request, session_id, message)


async def _build_result_payload(
    *,
    request: AnalyzeRequest,
    session_id: str,
    decision_id: str,
    started_at: float,
    analysis_memory_enabled: bool,
    final_result: dict[str, Any],
) -> dict[str, Any]:
    pm_report = final_result.get("PM_report", "")
    action = final_result.get("Action", "HOLD")
    direction, confidence, timeframe = _parse_pm_report(pm_report, action)

    agent_reports = {}
    for agent_name, report_key in _AGENT_REPORT_KEYS.items():
        report = final_result.get(report_key, "")
        if not report:
            continue
        # Convert dict values (debate/risk state) to their history strings
        if isinstance(report, dict):
            history = report.get("history", "")
            if history:
                agent_reports[agent_name] = history
        elif isinstance(report, str) and report.strip():
            agent_reports[agent_name] = report

    news_articles = []
    try:
        from quick_ask.agents.utils.agent_tools import _fetch_news_multi_source

        news_articles, _ = _fetch_news_multi_source(request.ticker, window_days=7)
    except Exception:
        pass

    elapsed = round(time.time() - started_at, 2)
    target_position_pct = float(final_result.get("Target_position_pct", 0))
    approval_status: str | None = None
    approval_id: str | None = None
    triggered_rules: list[str] = []

    try:
        from hitl import HITLRuleConfig, HITLRuleEngine
        from hitl.models import PMDecision
        from storage.store import get_store

        normalized_action = action.upper()
        if normalized_action not in {"BUY", "SELL", "HOLD"}:
            normalized_action = "HOLD"

        hitl_confidence = confidence
        if hitl_confidence > 1.0 and hitl_confidence <= 100.0:
            hitl_confidence = hitl_confidence / 100.0
        hitl_confidence = max(0.0, min(1.0, hitl_confidence))
        hitl_target_pct = max(0.0, min(100.0, target_position_pct))

        engine = HITLRuleEngine(
            HITLRuleConfig(
                position_change_threshold_pct=20.0,
                min_confidence_threshold=0.5,
                max_single_ticker_pct=30.0,
            )
        )
        pm_decision = PMDecision(
            action=normalized_action,
            target_position_pct=hitl_target_pct,
            confidence=hitl_confidence,
            report=pm_report,
        )
        needs_approval, triggered_rules = engine.evaluate(
            pm_decision,
            current_position_pct=request.current_position_pct,
        )
        if needs_approval:
            approval_status = "pending"
            approval_id = get_store().create_approval(
                request.strategy_id,
                {
                    "strategy_id": request.strategy_id,
                    "account_id": request.account_id,
                    "decision_id": decision_id,
                    "session_id": session_id,
                    "ticker": request.ticker,
                    "original_action": normalized_action,
                    "original_target_position_pct": hitl_target_pct,
                    "original_confidence": hitl_confidence,
                    "pm_report": pm_report,
                    "triggered_rules": triggered_rules,
                    "approval_reason": ", ".join(triggered_rules),
                    "agent_reports": agent_reports,
                    "status": "pending",
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
    except Exception as exc:
        logger.warning("HITL check failed for %s: %s", request.ticker, exc)

    return {
        "session_id": session_id,
        "strategy_id": request.strategy_id,
        "account_id": request.account_id,
        "decision_id": decision_id,
        "memory_enabled": analysis_memory_enabled,
        "memory_record_id": final_result.get("memory_record_id"),
        "action": action,
        "direction": direction,
        "confidence": confidence,
        "timeframe": timeframe,
        "report": pm_report,
        "agent_reports": agent_reports,
        "target_position_pct": target_position_pct,
        "debate_records": final_result.get("debate_history", []),
        "investment_debate_history": final_result.get("investment_debate_state", {}).get("history", ""),
        "risk_debate_history": final_result.get("risk_debate_state", {}).get("history", ""),
        "news_articles": [
            {
                "title": a["title"],
                "source": a.get("source_name", ""),
                "url": a.get("url", ""),
                "published_at": a.get("published_at", ""),
            }
            for a in news_articles
        ],
        "elapsed_s": elapsed,
        "approval_required": approval_status == "pending",
        "approval_status": approval_status,
        "approval_id": approval_id,
        "triggered_rules": triggered_rules,
    }


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
    conf_match = re.search(
        r"(?:置信度|confidence)[:\s]*([0-9]*\.?[0-9]+)", report, re.IGNORECASE
    )
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


def _analysis_priority(action: str, confidence: float) -> str:
    if action.upper() in {"BUY", "SELL"} or confidence >= 0.7:
        return "high"
    return "normal"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def _notify_analysis_completed(
    request: AnalyzeRequest,
    result: dict[str, Any],
) -> None:
    """Publish an analysis-complete notification without mutating domain state."""
    action = str(result.get("action", "HOLD")).upper()
    confidence = _safe_float(result.get("confidence"))
    priority = _analysis_priority(action, confidence)
    report = str(result.get("report", ""))
    summary = _extract_oneliner(report) or report.replace("\n", " ")[:160]
    message = (
        f"Ticker: {request.ticker.upper()}\n"
        f"Strategy: {request.strategy_id}\n"
        f"Account: {request.account_id}\n"
        f"Session: {result.get('session_id', '')}\n"
        f"Decision: {result.get('decision_id', '')}\n"
        f"Action: {action}\n"
        f"Direction: {result.get('direction', 'Neutral')}\n"
        f"Confidence: {confidence:.2f}\n"
        f"Target Position: {_safe_float(result.get('target_position_pct')):.2f}%\n"
        f"Approval: {result.get('approval_status') or 'not_required'}\n"
        f"Summary: {summary}"
    )
    try:
        from notification import build_manager
        from server.routes.settings import _load_settings

        results = await build_manager(_load_settings()).send(
            message=message,
            title=f"Analysis Complete: {request.ticker.upper()} {action}",
            priority=priority,
        )
        logger.info(
            "analysis_notification_done ticker=%s session_id=%s results=%s",
            request.ticker,
            result.get("session_id"),
            {
                name: {"ok": channel_result.ok, "message": channel_result.message}
                for name, channel_result in results.items()
            },
        )
    except Exception:
        logger.exception(
            "analysis_notification_failed ticker=%s session_id=%s",
            request.ticker,
            result.get("session_id"),
        )


async def _notify_analysis_failed(
    request: AnalyzeRequest,
    session_id: str,
    error: str,
) -> None:
    """Publish an analysis-failed notification without mutating domain state."""
    message = (
        f"Ticker: {request.ticker.upper()}\n"
        f"Strategy: {request.strategy_id}\n"
        f"Account: {request.account_id}\n"
        f"Session: {session_id}\n"
        f"Error: {error[:500]}"
    )
    try:
        from notification import build_manager
        from server.routes.settings import _load_settings

        await build_manager(_load_settings()).send(
            message=message,
            title=f"Analysis Failed: {request.ticker.upper()}",
            priority="high",
        )
    except Exception:
        logger.exception(
            "analysis_failure_notification_failed ticker=%s session_id=%s",
            request.ticker,
            session_id,
        )


# ── History endpoints ──────────────────────────────────────


@router.get("/analyze/history")
async def list_history(limit: int = 20):
    """List past analysis sessions."""
    items = [_history_item(data) for data in analysis_runs.list_snapshots(limit)]
    return {"items": items, "total": len(items)}


@router.get("/analyze/history/{session_id}")
async def get_history(session_id: str):
    """Get full session data."""
    try:
        return analysis_runs.load_snapshot(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Session not found")


@router.delete("/analyze/history/{session_id}")
async def delete_history(session_id: str):
    """Delete a past analysis session."""
    if not analysis_runs.delete_snapshot(session_id):
        raise HTTPException(404, "Session not found")
    return {"ok": True}


def _history_item(data: dict[str, Any]) -> dict[str, Any]:
    result = data.get("result")
    result_data = result if isinstance(result, dict) else None
    report = str(result_data.get("report", "")) if result_data else ""
    return {
        "session_id": data.get("session_id"),
        "ticker": data.get("ticker"),
        "mode": data.get("mode"),
        "status": data.get("status", "completed"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "action": result_data.get("action") if result_data else None,
        "direction": result_data.get("direction") if result_data else None,
        "confidence": result_data.get("confidence") if result_data else None,
        "oneliner": _extract_oneliner(report) if result_data else "",
    }


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
