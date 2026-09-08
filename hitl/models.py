"""HITL data models.

Pydantic models for approvals, rule configuration, and decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# -- Enums ----------------------------------------------------------------


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMED_OUT = "timed_out"
    AUTO_PASSED = "auto_passed"


# -- Rule Configuration ----------------------------------------------------


class HITLRuleConfig(BaseModel):
    """Strategy-level HITL rule configuration.

    All thresholds are percentages (0-100 or 0.0-1.0).
    """

    enabled: bool = True

    # Trigger rule thresholds
    position_change_threshold_pct: float = Field(
        default=20.0,
        ge=0,
        le=100,
        description="Trigger approval when position change exceeds this percentage",
    )
    min_confidence_threshold: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Trigger approval when confidence falls below this threshold",
    )
    max_single_ticker_pct: float = Field(
        default=30.0,
        ge=0,
        le=100,
        description="Trigger approval when single-ticker target position exceeds this percentage",
    )

    # Timeout configuration
    approval_timeout_minutes: int = Field(
        default=120,
        ge=1,
        description="Approval timeout in minutes",
    )


# -- PM Decision -----------------------------------------------------------


class PMDecision(BaseModel):
    """Portfolio Manager output decision."""

    action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    target_position_pct: float = Field(default=0.0, ge=0, le=100)
    confidence: float = Field(default=0.0, ge=0, le=1)
    report: str = ""

    @property
    def is_noop(self) -> bool:
        """True if HOLD with zero target position (no-op)."""
        return self.action == "HOLD" and self.target_position_pct == 0


# -- Approval Request ------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Approval request -- generated after PM decision, awaiting human review."""

    id: str
    strategy_id: str
    account_id: str = ""
    decision_id: str = ""
    session_id: str
    ticker: str

    # Original PM decision
    original_action: Literal["BUY", "SELL", "HOLD"]
    original_target_position_pct: float
    original_confidence: float
    pm_report: str = ""

    # Trigger reasons
    triggered_rules: list[str] = Field(default_factory=list)
    approval_reason: str = ""

    # Status
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None

    # Approval result (filled after human review)
    reviewer: str = ""
    reviewer_notes: str = ""
    modified_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    modified_target_position_pct: Optional[float] = None

    def is_expired(self) -> bool:
        """Check if this request has timed out."""
        if self.timeout_at is None:
            return False
        return datetime.now(timezone.utc) > self.timeout_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict (for database storage)."""
        return self.model_dump(mode="json")


# -- Approval Decision (human input) ---------------------------------------


class ApprovalDecision(BaseModel):
    """Human approval input."""

    approval_id: str
    reviewer: str
    decision: Literal["approve", "reject", "modify"]
    notes: Optional[str] = None

    # Only valid when decision == "modify"
    modified_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    modified_target_position_pct: Optional[float] = None

    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
