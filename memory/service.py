"""High-level memory integration helpers for the quick_ask pipeline."""

from __future__ import annotations

from collections.abc import Mapping
import os
import re
from typing import Any

from memory.models import MemoryRecord
from memory.store import MemoryStore


DEFAULT_STRATEGY_ID = "default"
DEFAULT_MEMORY_DB_PATH = "data/memory.db"
DEFAULT_RECALL_LIMIT = 5


class MemoryService:
    """Service boundary between agent state and OWM-scored memory storage."""

    def __init__(
        self,
        store: MemoryStore | None = None,
        strategy_id: str | None = None,
        recall_limit: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.store = store or MemoryStore(
            os.getenv("MEMORY_DB_PATH", DEFAULT_MEMORY_DB_PATH)
        )
        self.strategy_id = (
            strategy_id or os.getenv("MEMORY_STRATEGY_ID") or DEFAULT_STRATEGY_ID
        )
        self.recall_limit = recall_limit or int(
            os.getenv("MEMORY_RECALL_LIMIT", str(DEFAULT_RECALL_LIMIT))
        )
        self.enabled = memory_enabled(enabled)

    def recall_records(
        self,
        ticker: str,
        market_context: Mapping[str, Any] | None = None,
        *,
        strategy_id: str | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        """Return strategy-scoped memories for the current analysis context."""
        if not self.enabled:
            return []

        context = {"ticker": ticker.upper()}
        if market_context:
            context.update(dict(market_context))

        return self.store.recall_by_context(
            context=context,
            strategy_id=strategy_id or self.strategy_id,
            limit=limit or self.recall_limit,
        )

    def recall_context(
        self,
        ticker: str,
        market_context: Mapping[str, Any] | None = None,
        *,
        strategy_id: str | None = None,
        limit: int | None = None,
    ) -> str:
        """Return compact prompt-ready advisory text for recalled memories."""
        records = self.recall_records(
            ticker,
            market_context,
            strategy_id=strategy_id,
            limit=limit,
        )
        if not records:
            return "（无相关历史记忆；请仅依据当前证据分析。）"

        lines = [
            "以下历史记忆仅供参考；若与当前 Market/Fundamental/News/Risk 证据冲突，当前证据优先。",
        ]
        for index, record in enumerate(records, 1):
            trade = record.trade_record or {}
            action = trade.get("action", "UNKNOWN")
            target = trade.get("target_position_pct", "Unknown")
            direction = trade.get("direction", "Unknown")
            lesson = _compact(record.semantic or record.episodic, 220)
            lines.append(
                f"{index}. OWM={record.owm_score:.2f}; {record.created_at}; "
                f"{action} target={target} direction={direction}; {lesson}"
            )
        return "\n".join(lines)

    def remember_decision(self, state: Mapping[str, Any]) -> str | None:
        """Persist a completed PM decision as a five-layer MemoryRecord."""
        if not self.enabled:
            return None

        ticker = state.get("ticker")
        report = state.get("PM_report")
        action = state.get("Action")
        if not ticker or not report or not action:
            return None

        parsed = parse_pm_report(str(report))
        confidence = parsed["confidence"]
        if confidence is None:
            confidence = _safe_float(state.get("confidence"), 0.5)

        target_position_pct = _safe_float(state.get("Target_position_pct"), 0.0)
        current_position_pct = _safe_float(state.get("current_position_pct"), 0.0)
        position_delta_pct = target_position_pct - current_position_pct
        strategy_id = str(state.get("strategy_id") or self.strategy_id)

        record = MemoryRecord(
            strategy_id=strategy_id,
            session_id=str(state.get("session_id") or ""),
            ticker=str(ticker).upper(),
            outcome_quality=0.0,
            confidence=confidence,
            episodic=(
                f"On {state.get('date', 'Unknown date')}, PM decided {action} "
                f"{ticker} from current position {current_position_pct}% to "
                f"target {target_position_pct}%."
            ),
            semantic=(
                parsed["one_sentence"]
                or "No one-sentence PM conclusion parsed from the report."
            ),
            procedural=_build_procedural_summary(state),
            affective=(
                f"direction={parsed['direction'] or 'Unknown'}, "
                f"time_range={parsed['time_range'] or 'Unknown'}, "
                f"confidence={confidence:.2f}"
            ),
            trade_record={
                "date": state.get("date"),
                "action": str(action),
                "target_position_pct": target_position_pct,
                "current_position_pct": current_position_pct,
                "position_delta_pct": position_delta_pct,
                "direction": parsed["direction"],
                "time_range": parsed["time_range"],
                "confidence": confidence,
                "session_id": state.get("session_id"),
                "strategy_id": strategy_id,
                "account_id": state.get("account_id"),
                "decision_id": state.get("decision_id"),
                "pm_report_excerpt": _compact(report, 800),
            },
            tags=_build_tags(str(ticker), str(action), parsed),
        )
        return self.store.remember(record)


def parse_pm_report(report: str) -> dict[str, Any]:
    """Parse PM report header fields emitted by quick_ask/agents/PM.py."""
    confidence = _parse_confidence(
        _match(report, r"(?:置信度|confidence)[:：\s]*([0-9]*\.?[0-9]+)")
    )

    return {
        "direction": _match(report, r"方向[:：]\s*([^\n]+)"),
        "time_range": _match(report, r"时间范围[:：]\s*([^\n]+)"),
        "confidence": confidence,
        "one_sentence": _match(report, r"一句话结论[:：]\s*([^\n]+)"),
    }


def memory_enabled(config_value: bool | str | None = None) -> bool:
    """Return the shared memory enablement decision for env and server settings."""
    env_value = os.getenv("MEMORY_ENABLED")
    env_enabled = None if env_value is None else _truthy(env_value)
    if env_enabled is False:
        return False
    if config_value is not None:
        if isinstance(config_value, str):
            return _truthy(config_value)
        return bool(config_value)
    if env_enabled is not None:
        return env_enabled
    return True


def _build_procedural_summary(state: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "Decision based on current reports:",
            f"- market: {_compact(state.get('market_report'), 220)}",
            f"- fundamentals: {_compact(state.get('fundamental_report'), 220)}",
            f"- news: {_compact(state.get('news_report'), 220)}",
            f"- risk: {_compact(state.get('risk_report'), 220)}",
        ]
    )


def _build_tags(
    ticker: str,
    action: str,
    parsed: Mapping[str, Any],
) -> list[str]:
    tags = [ticker.upper(), action.upper()]
    for key in ("direction", "time_range"):
        value = parsed.get(key)
        if value:
            tags.append(str(value))
    return tags


def _match(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "", re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _parse_confidence(value: str) -> float | None:
    if not value:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if 1.0 < parsed <= 100.0:
        parsed = parsed / 100.0
    return max(0.0, min(1.0, parsed))


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _compact(text: Any, limit: int) -> str:
    compacted = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."
