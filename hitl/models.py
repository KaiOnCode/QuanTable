"""HITL data models.

Pydantic models for approvals, rule configuration, and decisions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMED_OUT = "timed_out"
    AUTO_PASSED = "auto_passed"


# ── Rule Configuration ───────────────────────────────────

class HITLRuleConfig(BaseModel):
    """策略级别的 HITL 规则配置.

    所有阈值均为百分比 (0-100 或 0.0-1.0).
    """

    enabled: bool = True

    # 触发规则阈值
    position_change_threshold_pct: float = Field(
        default=20.0, ge=0, le=100,
        description="仓位变化超过此百分比时触发审批",
    )
    min_confidence_threshold: float = Field(
        default=0.5, ge=0, le=1,
        description="置信度低于此值时触发审批",
    )
    max_single_ticker_pct: float = Field(
        default=30.0, ge=0, le=100,
        description="单票目标仓位超过此百分比时触发审批",
    )

    # 超时配置
    approval_timeout_minutes: int = Field(
        default=120, ge=1,
        description="审批超时时间（分钟）",
    )


# ── PM Decision ──────────────────────────────────────────

class PMDecision(BaseModel):
    """Portfolio Manager 的输出决策."""

    action: Literal["BUY", "SELL", "HOLD"] = "HOLD"
    target_position_pct: float = Field(default=0.0, ge=0, le=100)
    confidence: float = Field(default=0.0, ge=0, le=1)
    report: str = ""

    @property
    def is_noop(self) -> bool:
        """是否为无操作（HOLD 且目标仓位为 0）."""
        return self.action == "HOLD" and self.target_position_pct == 0


# ── Approval Request ─────────────────────────────────────

class ApprovalRequest(BaseModel):
    """审批请求 — PM 决策后生成，等待人工审核."""

    id: str
    strategy_id: str
    session_id: str
    ticker: str

    # 原始 PM 决策
    original_action: Literal["BUY", "SELL", "HOLD"]
    original_target_position_pct: float
    original_confidence: float
    pm_report: str = ""

    # 触发原因
    triggered_rules: list[str] = Field(default_factory=list)

    # 状态
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timeout_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None

    # 审批结果（填写后）
    reviewer: str = ""
    reviewer_notes: str = ""
    modified_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    modified_target_position_pct: Optional[float] = None

    def is_expired(self) -> bool:
        """检查是否已超时."""
        if self.timeout_at is None:
            return False
        return datetime.now(timezone.utc) > self.timeout_at

    def to_dict(self) -> dict[str, Any]:
        """转为可序列化的 dict（用于数据库存储）."""
        return self.model_dump(mode="json")


# ── Approval Decision (human input) ──────────────────────

class ApprovalDecision(BaseModel):
    """人工审批的输入."""

    approval_id: str
    reviewer: str
    decision: Literal["approve", "reject", "modify"]
    notes: Optional[str] = None

    # 仅当 decision == "modify" 时有效
    modified_action: Optional[Literal["BUY", "SELL", "HOLD"]] = None
    modified_target_position_pct: Optional[float] = None

    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
