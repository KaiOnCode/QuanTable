"""POST /api/approvals — Human-in-the-Loop approval endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from hitl import ApprovalDecision, ApprovalStateMachine
from storage.store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["approvals"])


@router.get("/approvals")
def list_approvals(
    strategy_id: str = Query(default="default"),
    status: str | None = None,
    limit: int = 50,
):
    """GET /api/approvals?strategy_id=default&status=pending

    List approvals for a strategy. Defaults to the "default" strategy
    used by Quick Ask.
    """
    store = get_store()
    approvals = store.list_approvals(strategy_id, status=status, limit=limit)
    return {"items": approvals, "total": len(approvals)}


@router.get("/approvals/{approval_id}")
def get_approval(approval_id: str, strategy_id: str = Query(default="default")):
    """GET /api/approvals/{id}?strategy_id=default"""
    store = get_store()
    approval = store.get_approval(strategy_id, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    return approval


class ApprovalActionRequest(BaseModel):
    reviewer: str = Field(default="anonymous")
    notes: str | None = None


class ApprovalModifyRequest(ApprovalActionRequest):
    modified_action: Literal["BUY", "SELL", "HOLD"]
    modified_target_position_pct: float = Field(ge=0.0, le=100.0)


@router.post("/approvals/{approval_id}/approve")
def approve_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    strategy_id: str = Query(default="default"),
):
    """POST /api/approvals/{id}/approve"""
    store = get_store()
    row = store.get_approval(strategy_id, approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    decision = ApprovalDecision(
        approval_id=approval_id,
        reviewer=body.reviewer,
        decision="approve",
        notes=body.notes,
        decided_at=datetime.now(timezone.utc),
    )

    req = _approval_request_from_row(row, strategy_id)
    ApprovalStateMachine.apply_decision(req, decision)

    store.update_approval_status(
        strategy_id,
        approval_id,
        status=req.status.value,
        reviewer=req.reviewer,
        reviewer_notes=req.reviewer_notes or "",
    )

    logger.info("Approval %s approved by %s", approval_id, req.reviewer)
    return {"status": "approved", "approval_id": approval_id}


@router.post("/approvals/{approval_id}/reject")
def reject_approval(
    approval_id: str,
    body: ApprovalActionRequest,
    strategy_id: str = Query(default="default"),
):
    """POST /api/approvals/{id}/reject"""
    store = get_store()
    row = store.get_approval(strategy_id, approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    decision = ApprovalDecision(
        approval_id=approval_id,
        reviewer=body.reviewer,
        decision="reject",
        notes=body.notes,
        decided_at=datetime.now(timezone.utc),
    )

    req = _approval_request_from_row(row, strategy_id)
    ApprovalStateMachine.apply_decision(req, decision)

    store.update_approval_status(
        strategy_id,
        approval_id,
        status=req.status.value,
        reviewer=req.reviewer,
        reviewer_notes=req.reviewer_notes or "",
    )

    logger.info("Approval %s rejected by %s", approval_id, req.reviewer)
    return {"status": "rejected", "approval_id": approval_id}


@router.post("/approvals/{approval_id}/modify")
def modify_approval(
    approval_id: str,
    body: ApprovalModifyRequest,
    strategy_id: str = Query(default="default"),
):
    """POST /api/approvals/{id}/modify"""
    store = get_store()
    row = store.get_approval(strategy_id, approval_id)
    if not row:
        raise HTTPException(status_code=404, detail="Approval not found")

    decision = ApprovalDecision(
        approval_id=approval_id,
        reviewer=body.reviewer,
        decision="modify",
        notes=body.notes,
        modified_action=body.modified_action,
        modified_target_position_pct=body.modified_target_position_pct,
        decided_at=datetime.now(timezone.utc),
    )

    req = _approval_request_from_row(row, strategy_id)
    ApprovalStateMachine.apply_decision(req, decision)

    store.update_approval_status(
        strategy_id,
        approval_id,
        status=req.status.value,
        reviewer=req.reviewer,
        reviewer_notes=req.reviewer_notes or "",
        modified_action=req.modified_action,
        modified_target_position_pct=req.modified_target_position_pct,
    )

    logger.info(
        "Approval %s modified by %s: %s %s%%",
        approval_id,
        req.reviewer,
        req.modified_action,
        req.modified_target_position_pct,
    )
    return {
        "status": "modified",
        "approval_id": approval_id,
        "modified_action": req.modified_action,
        "modified_target_position_pct": req.modified_target_position_pct,
    }


# ── Helpers ──────────────────────────────────────────────


def _approval_request_from_row(row: dict, strategy_id: str):
    from hitl.models import ApprovalRequest, ApprovalStatus

    return ApprovalRequest(
        id=row["id"],
        strategy_id=row.get("strategy_id") or strategy_id,
        account_id=row.get("account_id") or "",
        decision_id=row.get("decision_id") or "",
        session_id=row["session_id"],
        ticker=row["ticker"],
        original_action=row["original_action"],
        original_target_position_pct=row["original_target_position_pct"],
        original_confidence=row["original_confidence"],
        pm_report=row.get("pm_report", ""),
        triggered_rules=_parse_json_list(row.get("triggered_rules_json", "[]")),
        approval_reason=row.get("approval_reason", ""),
        status=ApprovalStatus(row["status"]),
        created_at=_parse_dt(row["created_at"]) or datetime.now(timezone.utc),
        timeout_at=_parse_dt(row.get("timeout_at")),
        reviewer=row.get("reviewer", ""),
        reviewer_notes=row.get("reviewer_notes", ""),
    )


def _parse_json_list(value: str | None) -> list[str]:
    import json

    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _parse_dt(value: str | None):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
