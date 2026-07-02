from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from hitl import (
    ApprovalDecision,
    ApprovalStateMachine,
    ApprovalStatus,
    HITLRuleConfig,
    HITLRuleEngine,
    PMDecision,
)
from hitl.state_machine import InvalidTransitionError
from server.routes import approvals
from storage.store import ContextStore


def test_hitl_rules_trigger_and_skip_noop() -> None:
    engine = HITLRuleEngine(
        HITLRuleConfig(
            position_change_threshold_pct=20.0,
            min_confidence_threshold=0.5,
            max_single_ticker_pct=30.0,
        )
    )

    noop = PMDecision(action="HOLD", target_position_pct=0.0, confidence=0.3)
    assert engine.evaluate(noop, current_position_pct=0.0) == (False, [])

    decision = PMDecision(action="BUY", target_position_pct=60.0, confidence=0.4)
    needs_approval, rules = engine.evaluate(decision, current_position_pct=10.0)

    assert needs_approval is True
    assert rules == ["position_change", "low_confidence", "high_concentration"]


def test_approval_state_machine_validates_transitions() -> None:
    from hitl.models import ApprovalRequest

    request = ApprovalRequest(
        id="approval-1",
        strategy_id="strategy-1",
        account_id="account-1",
        decision_id="decision-1",
        session_id="session-1",
        ticker="AAPL",
        original_action="BUY",
        original_target_position_pct=50.0,
        original_confidence=0.8,
        triggered_rules=["position_change"],
    )

    ApprovalStateMachine.apply_decision(
        request,
        ApprovalDecision(
            approval_id="approval-1",
            reviewer="reviewer",
            decision="approve",
            notes="ok",
        ),
    )

    assert request.status == ApprovalStatus.APPROVED
    assert request.reviewer == "reviewer"

    with pytest.raises(InvalidTransitionError):
        ApprovalStateMachine.apply_decision(
            request,
            ApprovalDecision(
                approval_id="approval-1",
                reviewer="reviewer",
                decision="reject",
            ),
        )


def test_approval_api_uses_pydantic_schema_and_updates_store(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ContextStore(tmp_path)
    approval_id = store.create_approval(
        "strategy-1",
        {
            "account_id": "account-1",
            "decision_id": "decision-1",
            "session_id": "session-1",
            "ticker": "AAPL",
            "original_action": "BUY",
            "original_target_position_pct": 50.0,
            "original_confidence": 0.7,
            "triggered_rules": ["position_change"],
            "approval_reason": "position_change",
        },
    )
    monkeypatch.setattr(approvals, "get_store", lambda: store)

    app = FastAPI()
    app.include_router(approvals.router, prefix="/api")
    client = TestClient(app)

    invalid = client.post(
        f"/api/approvals/{approval_id}/modify?strategy_id=strategy-1",
        json={"reviewer": "human", "modified_action": "BUY"},
    )
    assert invalid.status_code == 422

    response = client.post(
        f"/api/approvals/{approval_id}/modify?strategy_id=strategy-1",
        json={
            "reviewer": "human",
            "notes": "cap exposure",
            "modified_action": "BUY",
            "modified_target_position_pct": 25.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "modified"

    updated = store.get_approval("strategy-1", approval_id)
    assert updated is not None
    assert updated["status"] == "modified"
    assert updated["reviewer"] == "human"
    assert updated["modified_target_position_pct"] == pytest.approx(25.0)

    store.close()
