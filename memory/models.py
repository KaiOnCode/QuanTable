"""Pydantic models for the Memory layer.

Inspired by TradeMemory Protocol (MIT License).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid

from pydantic import BaseModel, Field


class MemoryLayer(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    AFFECTIVE = "affective"
    TRADE_RECORD = "trade_record"


class MemoryRecord(BaseModel):
    """A single memory entry stored across 5 layers."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    session_id: str = ""
    ticker: str

    # OWM 5-factor inputs
    outcome_quality: float = 0.0  # -1.0 to 1.0
    confidence: float = 0.5  # 0.0 to 1.0

    # Content layers
    episodic: str = ""  # Story of what happened
    semantic: str = ""  # Rule or lesson learned
    procedural: str = ""  # Pattern or trigger conditions
    affective: str = ""  # Emotional/market state context
    trade_record: dict = Field(
        default_factory=dict
    )  # {action, price, qty, pnl_pct, ...}

    # Computed on store
    owm_score: float = 0.0
    tags: list[str] = Field(default_factory=list)

    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class Reflection(BaseModel):
    """Periodic reflection on strategy performance."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    period_start: str
    period_end: str

    total_trades: int = 0
    win_rate_pct: float = 0.0
    avg_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float | None = None

    disposition_effect: str | None = None
    overtrading: str | None = None
    momentum_chasing: str | None = None
    anchoring: str | None = None

    strategy_decay_detected: bool = False
    decay_indicators: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    new_rules: list[str] = Field(default_factory=list)
    new_findings: list[str] = Field(default_factory=list)
    new_failures: list[str] = Field(default_factory=list)

    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PreTradeCheck(BaseModel):
    """Safety gate result before executing a trade."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str
    decision_id: str

    passed: bool = True
    checks: dict[str, bool] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    checked_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
