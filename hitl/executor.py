"""HITL Executor.

审批通过/修改后的后续处理.
注意: 当前版本只记录结果，不调用 Broker（由 Gap C 负责）.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from hitl.models import ApprovalRequest, ApprovalStatus

logger = logging.getLogger("hitl.executor")


class ExecutionResult(BaseModel):
    """执行结果."""

    executed: bool
    action: str | None = None
    target_position_pct: float | None = None
    message: str = ""


class HITLExecutor:
    """将审批结果转为可执行的决策.

    当前仅做记录和日志，实际交易执行由外部 Broker 模块接管.
    """

    def process_approval_result(self, request: ApprovalRequest) -> ExecutionResult:
        """处理审批结果，返回最终应执行的决策参数.

        Args:
            request: 已审批（approved/modified）或已拒绝的审批请求

        Returns:
            ExecutionResult: 包含是否执行、执行参数等信息
        """
        if request.status == ApprovalStatus.REJECTED:
            logger.info(
                "[HITL] Approval %s rejected by %s. No execution.",
                request.id,
                request.reviewer,
            )
            return ExecutionResult(
                executed=False,
                message=f"Rejected by {request.reviewer}: {request.reviewer_notes}",
            )

        if request.status == ApprovalStatus.TIMED_OUT:
            logger.info(
                "[HITL] Approval %s timed out. No execution.",
                request.id,
            )
            return ExecutionResult(
                executed=False,
                message="Approval timed out, no human response.",
            )

        if request.status == ApprovalStatus.APPROVED:
            final_action = request.original_action
            final_pct = request.original_target_position_pct
            logger.info(
                "[HITL] Approval %s approved by %s. Execute %s %s%% on %s.",
                request.id,
                request.reviewer,
                final_action,
                final_pct,
                request.ticker,
            )
            return ExecutionResult(
                executed=True,
                action=final_action,
                target_position_pct=final_pct,
                message=f"Approved by {request.reviewer}",
            )

        if request.status == ApprovalStatus.MODIFIED:
            final_action = request.modified_action or request.original_action
            final_pct = (
                request.modified_target_position_pct
                or request.original_target_position_pct
            )
            logger.info(
                "[HITL] Approval %s modified by %s. Execute %s %s%% on %s (was %s %s%%).",
                request.id,
                request.reviewer,
                final_action,
                final_pct,
                request.ticker,
                request.original_action,
                request.original_target_position_pct,
            )
            return ExecutionResult(
                executed=True,
                action=final_action,
                target_position_pct=final_pct,
                message=f"Modified by {request.reviewer}: {request.reviewer_notes}",
            )

        # PENDING / AUTO_PASSED 不应进入此处
        logger.warning(
            "[HITL] Approval %s has unexpected status %s. No execution.",
            request.id,
            request.status.value,
        )
        return ExecutionResult(
            executed=False,
            message=f"Unexpected status: {request.status.value}",
        )

    def to_event_payload(self, request: ApprovalRequest) -> dict[str, Any]:
        """将审批结果转为事件日志的 payload（供 ContextStore 记录）."""
        result = self.process_approval_result(request)
        return {
            "approval_id": request.id,
            "strategy_id": request.strategy_id,
            "session_id": request.session_id,
            "ticker": request.ticker,
            "status": request.status.value,
            "reviewer": request.reviewer,
            "original_action": request.original_action,
            "original_target_position_pct": request.original_target_position_pct,
            "modified_action": request.modified_action,
            "modified_target_position_pct": request.modified_target_position_pct,
            "executed": result.executed,
            "final_action": result.action,
            "final_target_position_pct": result.target_position_pct,
            "notes": request.reviewer_notes,
        }
