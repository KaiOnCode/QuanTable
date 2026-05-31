"""Approval State Machine.

管理审批状态的生命周期转换.
"""

from __future__ import annotations

from hitl.models import ApprovalDecision, ApprovalRequest, ApprovalStatus


class InvalidTransitionError(ValueError):
    """非法状态转换."""

    pass


class ApprovalStateMachine:
    """审批状态机.

    合法转换:
        PENDING → APPROVED | REJECTED | MODIFIED | TIMED_OUT
        AUTO_PASSED → (终态, 不可转换)
        APPROVED → (终态)
        REJECTED → (终态)
        MODIFIED → (终态)
        TIMED_OUT → (终态)
    """

    VALID_TRANSITIONS: dict[ApprovalStatus, set[ApprovalStatus]] = {
        ApprovalStatus.PENDING: {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.MODIFIED,
            ApprovalStatus.TIMED_OUT,
        },
        ApprovalStatus.AUTO_PASSED: set(),
        ApprovalStatus.APPROVED: set(),
        ApprovalStatus.REJECTED: set(),
        ApprovalStatus.MODIFIED: set(),
        ApprovalStatus.TIMED_OUT: set(),
    }

    @classmethod
    def can_transition(
        cls, from_status: ApprovalStatus, to_status: ApprovalStatus
    ) -> bool:
        """检查状态转换是否合法."""
        return to_status in cls.VALID_TRANSITIONS.get(from_status, set())

    @classmethod
    def apply_decision(
        cls, request: ApprovalRequest, decision: ApprovalDecision
    ) -> ApprovalRequest:
        """将人工决策应用到审批请求上.

        Args:
            request: 待更新的审批请求
            decision: 人工审批决策

        Returns:
            更新后的审批请求

        Raises:
            InvalidTransitionError: 如果状态转换不合法
        """
        status_map = {
            "approve": ApprovalStatus.APPROVED,
            "reject": ApprovalStatus.REJECTED,
            "modify": ApprovalStatus.MODIFIED,
        }
        new_status = status_map[decision.decision]

        if not cls.can_transition(request.status, new_status):
            raise InvalidTransitionError(
                f"Cannot transition from {request.status.value} to {new_status.value}"
            )

        request.status = new_status
        request.reviewer = decision.reviewer
        request.reviewer_notes = decision.notes or ""
        request.decided_at = decision.decided_at

        if decision.decision == "modify":
            request.modified_action = decision.modified_action
            request.modified_target_position_pct = decision.modified_target_position_pct

        return request

    @classmethod
    def mark_expired(cls, request: ApprovalRequest) -> ApprovalRequest:
        """将审批标记为超时."""
        if not cls.can_transition(request.status, ApprovalStatus.TIMED_OUT):
            raise InvalidTransitionError(
                f"Cannot mark {request.status.value} as timed_out"
            )
        request.status = ApprovalStatus.TIMED_OUT
        return request
