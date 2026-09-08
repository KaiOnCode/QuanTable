"""HITL (Human-in-the-Loop) module.

Approval loop -- submits high-risk AI decisions for human review.

Usage:
    from hitl import HITLRuleEngine, ApprovalStateMachine, HITLExecutor
    from hitl.models import HITLRuleConfig, PMDecision, ApprovalRequest, ApprovalDecision

    # 1. Configure rules
    config = HITLRuleConfig(position_change_threshold_pct=20)
    engine = HITLRuleEngine(config)

    # 2. Evaluate PM decision
    decision = PMDecision(action="BUY", target_position_pct=60, confidence=0.8)
    needs_approval, rules = engine.evaluate(decision, current_position_pct=0)

    # 3. Apply state transition after human approval
    request = ApprovalRequest(id="a1", strategy_id="s1", ...)
    human_decision = ApprovalDecision(approval_id="a1", reviewer="admin", decision="approve")
    ApprovalStateMachine.apply_decision(request, human_decision)

    # 4. Process execution
    executor = HITLExecutor()
    result = executor.process_approval_result(request)
"""

from hitl.models import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    HITLRuleConfig,
    PMDecision,
)
from hitl.rules import HITLRuleEngine
from hitl.state_machine import ApprovalStateMachine, InvalidTransitionError
from hitl.executor import ExecutionResult, HITLExecutor

__all__ = [
    # Models
    "HITLRuleConfig",
    "PMDecision",
    "ApprovalRequest",
    "ApprovalDecision",
    "ApprovalStatus",
    # Core
    "HITLRuleEngine",
    "ApprovalStateMachine",
    "InvalidTransitionError",
    "HITLExecutor",
    "ExecutionResult",
]
