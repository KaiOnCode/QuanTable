"""POST /api/analyze — SSE streaming analysis endpoint.

Calls the LangGraph orchestrator in a background thread and streams
progress, debate, and result events back to the frontend via SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


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


@router.post("/analyze")
async def analyze(request: AnalyzeRequest):
    """Start a new analysis. Returns SSE stream with progress events."""

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

        try:
            # Import orchestrator (lazy to avoid blocking startup)
            from agentgraph.orchestrator import IntelliFin_Assistant

            # Run in thread pool (orchestrator is synchronous)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                _run_analysis,
                request.ticker,
                request.date,
                request.current_position_pct,
                session_id,
            )

            # Parse PM report for structured result
            pm_report = result.get("PM_report", "")
            action = result.get("Action", "HOLD")
            direction, confidence, timeframe = _parse_pm_report(pm_report, action)

            # ── HITL check ──────────────────────────────────────
            approval_status = "auto_passed"
            approval_id = None
            triggered_rules = []
            try:
                from hitl import HITLRuleEngine, HITLRuleConfig, PMDecision as HITLDecision
                from storage.store import get_store as _get_store

                # 使用默认 HITL 配置（后续可从策略配置读取）
                hitl_config = HITLRuleConfig(
                    position_change_threshold_pct=20.0,
                    min_confidence_threshold=0.9,
                    max_single_ticker_pct=30.0,
                )
                engine = HITLRuleEngine(hitl_config)
                pm_decision = HITLDecision(
                    action=action,
                    target_position_pct=float(result.get("Target_position_pct", 0)),
                    confidence=confidence,
                    report=pm_report,
                )
                needs_approval, rules = engine.evaluate(
                    pm_decision, current_position_pct=request.current_position_pct
                )
                if needs_approval:
                    approval_status = "pending"
                    triggered_rules = rules
                    # 创建审批记录
                    store = _get_store()
                    approval_data = {
                        "session_id": session_id,
                        "ticker": request.ticker,
                        "original_action": action,
                        "original_target_position_pct": float(result.get("Target_position_pct", 0)),
                        "original_confidence": confidence,
                        "pm_report": pm_report[:2000],
                        "triggered_rules": rules,
                        "status": "pending",
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "timeout_at": None,
                    }
                    approval_id = store.create_approval("default", approval_data)
                    logger.info(
                        "HITL triggered for %s: %s (approval_id=%s)",
                        request.ticker, rules, approval_id,
                    )
            except Exception as hitl_exc:
                logger.warning("HITL check failed for %s: %s", request.ticker, hitl_exc)
                # HITL 检查失败不阻塞主流程，继续执行

            # Emit per-agent progress (post-hoc: mark agents with reports as completed)
            agent_reports = {
                "market_analyst": result.get("market_report", ""),
                "news_analyst": result.get("news_report", ""),
                "fundamentals_analyst": result.get("fundamental_report", ""),
                "PM_agent": pm_report,
            }
            for agent_name, report in agent_reports.items():
                status = "completed" if report else "error"
                yield _sse_event("progress", {
                    "agent": agent_name,
                    "status": status,
                    "duration_ms": 0,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            # Emit debate records if present
            debate_history = result.get("debate_history", [])
            for d in debate_history:
                yield _sse_event("debate", {
                    "type": "investment",
                    "round": d.get("round", 1),
                    "bull_claim": d.get("bull_claim", ""),
                    "bear_claim": d.get("bear_claim", ""),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            risk_debate = result.get("risk_debate_history", [])
            for d in risk_debate:
                yield _sse_event("debate", {
                    "type": "risk",
                    "round": d.get("round", 1),
                    "aggressive": d.get("aggressive", ""),
                    "safe": d.get("safe", ""),
                    "neutral": d.get("neutral", ""),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

            # Emit final result

            elapsed = round(time.time() - started_at, 2)
            yield _sse_event("result", {
                "session_id": session_id,
                "action": result.get("Action", "HOLD"),
                "direction": direction,
                "confidence": confidence,
                "timeframe": timeframe,
                "report": pm_report,
                "target_position_pct": float(result.get("Target_position_pct", 0)),
                "debate_records": debate_history,
                "elapsed_s": elapsed,
                "approval_status": approval_status,
                "approval_id": approval_id,
                "triggered_rules": triggered_rules,
            })

        except Exception as exc:
            err_msg = str(exc)
            # PM often returns valid text but JSON parsing fails.
            # Extract the report from the error message.
            if "Invalid json output:" in err_msg and "方向:" in err_msg:
                report_text = err_msg.split("Invalid json output:", 1)[1].strip()
                direction, confidence, timeframe = _parse_pm_report(report_text, "HOLD")
                yield _sse_event("result", {
                    "session_id": session_id,
                    "action": "HOLD",
                    "direction": direction,
                    "confidence": confidence,
                    "timeframe": timeframe,
                    "report": report_text[:2000],
                    "target_position_pct": 0,
                    "debate_records": [],
                    "elapsed_s": round(time.time() - started_at, 2),
                })
            else:
                logger.exception("Analysis failed for %s", request.ticker)
                yield _sse_event("error", {
                    "agent": "orchestrator",
                    "error": err_msg[:500],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

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


def _run_analysis(
    ticker: str,
    date: str | None,
    position_pct: float,
    session_id: str,
) -> dict[str, Any]:
    """Run the LangGraph pipeline and record to ContextStore."""

    import logging
    from datetime import datetime, timezone
    _log = logging.getLogger("analyze")

    from agentgraph.orchestrator import IntelliFin_Assistant

    # Default date to today if not provided
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")

    _log.info("Creating orchestrator for %s (date=%s)...", ticker, date)
    assistant = IntelliFin_Assistant()

    # Record session start
    try:
        from storage import get_store
        store = get_store()
        store.record_session("default", session_id, ticker)
    except Exception:
        pass

    # Run the pipeline
    result = assistant.run(ticker, date=date, current_position_pct=position_pct)
    _log.info("Pipeline complete. PM_report: %d chars, Action: %s",
              len(result.get("PM_report", "")), result.get("Action", "N/A"))

    # Record decision
    try:
        from storage import get_store
        store = get_store()

        # Record agent reports
        for agent in ["market", "news", "fundamentals", "risk"]:
            report_key = f"{agent}_report"
            if result.get(report_key):
                store.record_report(
                    "default", session_id, agent,
                    report_key, str(result[report_key]),
                )

        # Record final decision
        store.record_decision("default", {
            "session_id": session_id,
            "ticker": ticker,
            "action": result.get("Action", "HOLD"),
            "direction": result.get("direction", "Neutral"),
            "confidence": result.get("confidence", 0.0),
            "target_position_pct": result.get("Target_position_pct", 0.0),
            "report": result.get("PM_report", ""),
        })

        # Record memory
        try:
            from memory.store import MemoryStore
            from memory.models import MemoryRecord
            import uuid as _uuid

            mem_store = MemoryStore("data/memory.db")
            record = MemoryRecord(
                id=str(_uuid.uuid4()),
                strategy_id="default",
                session_id=session_id,
                ticker=ticker,
                outcome_quality=0.0,
                confidence=result.get("confidence", 0.5),
                episodic=f"Analysis: {result.get('Action', 'HOLD')} {ticker}",
                semantic="",
                procedural="",
                trade_record={"action": result.get("Action", "HOLD")},
                tags=[ticker, result.get("Action", "HOLD").lower()],
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            mem_store.remember(record)
        except Exception:
            pass

        store.complete_session("default", session_id)

    except Exception:
        pass

    return result
