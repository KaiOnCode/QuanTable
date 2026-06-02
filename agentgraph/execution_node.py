from __future__ import annotations

from collections.abc import Callable, Mapping
from math import floor
from typing import TYPE_CHECKING

from broker.events import BrokerEvent
from broker.gateway import BrokerGateway
from broker.models import ExecutionReport, Order, OrderSide, OrderStatus, OrderType
from broker.views import (
    ApprovalSnapshotView,
    ExecutionReportView,
    ExecutionStatusView,
    to_execution_report_view,
    to_execution_status_report_view,
)

if TYPE_CHECKING:
    from dataflow.portfolio_manager import PortfolioManager


def _coerce_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def create_execution_node(
    broker: BrokerGateway,
    portfolio_manager: PortfolioManager | None = None,
    on_execution_complete: (
        Callable[[ExecutionReportView, Mapping[str, object]], None] | None
    ) = None,
):
    """Create the execution node that runs after PM decisions."""

    def execution_node(state: Mapping[str, object]) -> dict[str, object]:
        identity = _identity_from_state(state)
        ticker = str(state.get("ticker", "") or "")
        action = str(state.get("Action", "HOLD") or "HOLD").upper()
        approval_status = str(state.get("approval_status", "auto_approved") or "")
        if not approval_status:
            approval_status = "auto_approved"
        original_target_pct = _coerce_float(state.get("Target_position_pct", 0.0))
        approval = _approval_snapshot(
            state,
            approval_status=approval_status,
            original_target_pct=original_target_pct,
        )

        if not state.get("execution_enabled", False):
            return _report_result(
                to_execution_status_report_view(
                    status="skipped",
                    reason="execution disabled",
                    ticker=ticker,
                    pm_action=action,
                    pm_report_summary=str(state.get("PM_report", "") or ""),
                    strategy_id=identity["strategy_id"],
                    account_id=identity["account_id"],
                    session_id=identity["session_id"],
                    decision_id=identity["decision_id"],
                )
            )

        if approval_status == "pending":
            report = to_execution_status_report_view(
                status="pending",
                reason="waiting for approval",
                ticker=ticker,
                pm_action=action,
                pm_report_summary=str(state.get("PM_report", "") or ""),
                approval=approval,
                strategy_id=identity["strategy_id"],
                account_id=identity["account_id"],
                session_id=identity["session_id"],
                decision_id=identity["decision_id"],
            )
            _publish_execution_event(
                broker,
                event_type="execution_pending",
                report=report,
                ticker=ticker,
            )
            return _report_result(report)

        if approval_status in {"rejected", "timed_out"}:
            report = to_execution_status_report_view(
                status="rejected",
                reason="approval rejected",
                ticker=ticker,
                pm_action=action,
                pm_report_summary=str(state.get("PM_report", "") or ""),
                approval=approval,
                strategy_id=identity["strategy_id"],
                account_id=identity["account_id"],
                session_id=identity["session_id"],
                decision_id=identity["decision_id"],
            )
            _publish_execution_event(
                broker,
                event_type="execution_rejected",
                report=report,
                ticker=ticker,
            )
            return _report_result(report)

        if action == "HOLD":
            return _report_result(
                to_execution_status_report_view(
                    status="held",
                    reason="PM held",
                    ticker=ticker,
                    pm_action=action,
                    pm_report_summary=str(state.get("PM_report", "") or ""),
                    approval=approval,
                    strategy_id=identity["strategy_id"],
                    account_id=identity["account_id"],
                    session_id=identity["session_id"],
                    decision_id=identity["decision_id"],
                )
            )

        reference_price = broker.get_latest_price(ticker)
        if not ticker or reference_price is None:
            report = to_execution_status_report_view(
                status="failed",
                reason="missing market price",
                ticker=ticker,
                pm_action=action,
                pm_report_summary=str(state.get("PM_report", "") or ""),
                approval=approval,
                strategy_id=identity["strategy_id"],
                account_id=identity["account_id"],
                session_id=identity["session_id"],
                decision_id=identity["decision_id"],
            )
            _publish_execution_event(
                broker,
                event_type="execution_failed",
                report=report,
                ticker=ticker,
            )
            return _report_result(report)

        if approval_status == "modified" and state.get("modified_target_pct") is None:
            report = to_execution_status_report_view(
                status="failed",
                reason="missing modified target percentage",
                ticker=ticker,
                pm_action=action,
                pm_report_summary=str(state.get("PM_report", "") or ""),
                approval=approval,
                strategy_id=identity["strategy_id"],
                account_id=identity["account_id"],
                session_id=identity["session_id"],
                decision_id=identity["decision_id"],
            )
            _publish_execution_event(
                broker,
                event_type="execution_failed",
                report=report,
                ticker=ticker,
            )
            return _report_result(report)

        account_before = broker.get_account(account_id=identity["account_id"])
        position_before = broker.get_position(ticker, account_id=identity["account_id"])
        current_shares = position_before.shares if position_before is not None else 0.0
        target_pct_source = (
            state.get("modified_target_pct", original_target_pct)
            if approval_status == "modified"
            else original_target_pct
        )
        target_pct = _coerce_float(target_pct_source)
        target_fraction = max(min(target_pct / 100.0, 1.0), -1.0)
        target_position_value = account_before.equity * target_fraction
        target_shares = float(floor(target_position_value / reference_price))
        delta_shares = target_shares - current_shares

        if delta_shares == 0:
            return _report_result(
                to_execution_status_report_view(
                    status="held",
                    reason="target already satisfied",
                    ticker=ticker,
                    pm_action=action,
                    pm_report_summary=str(state.get("PM_report", "") or ""),
                    approval=approval,
                    strategy_id=identity["strategy_id"],
                    account_id=identity["account_id"],
                    session_id=identity["session_id"],
                    decision_id=identity["decision_id"],
                )
            )

        order = Order(
            ticker=ticker,
            side=OrderSide.BUY if delta_shares > 0 else OrderSide.SELL,
            type=OrderType.MARKET,
            qty=abs(delta_shares),
            strategy_id=identity["strategy_id"],
            account_id=identity["account_id"],
            session_id=identity["session_id"],
            decision_id=identity["decision_id"],
            client_order_id=str(state.get("client_order_id", "") or ""),
        )
        placed_order = broker.place_order(order)
        fills = broker.get_fills(placed_order.id, account_id=identity["account_id"])
        position_after = broker.get_position(ticker, account_id=identity["account_id"])
        account_after = broker.get_account(account_id=identity["account_id"])

        execution_report = ExecutionReport(
            order=placed_order,
            fills=fills,
            position_before=position_before,
            position_after=position_after,
            account_after=account_after,
            pm_action=action,
            pm_report_summary=str(state.get("PM_report", "") or ""),
            strategy_id=identity["strategy_id"],
            account_id=identity["account_id"],
            session_id=identity["session_id"],
            decision_id=identity["decision_id"],
        )
        status = _execution_status_from_order_status(placed_order.status)
        report = to_execution_report_view(
            execution_report,
            status=status,
            approval=approval,
            reason="broker rejected order" if status == "rejected" else "",
        )
        event_type = _execution_event_type_for_status(status)
        if event_type is not None:
            _publish_execution_event(
                broker,
                event_type=event_type,
                report=report,
                ticker=ticker,
            )
        if portfolio_manager is not None:
            portfolio_manager.sync_from_broker(broker)
        if on_execution_complete is not None:
            on_execution_complete(report, state)
        return _report_result(report)

    return execution_node


def _identity_from_state(state: Mapping[str, object]) -> dict[str, str]:
    strategy_id = str(state.get("strategy_id", "") or "")
    account_id = str(state.get("account_id", "") or "") or strategy_id or "default"
    return {
        "strategy_id": strategy_id,
        "account_id": account_id,
        "session_id": str(state.get("session_id", "") or ""),
        "decision_id": str(state.get("decision_id", "") or ""),
    }


def _approval_snapshot(
    state: Mapping[str, object],
    *,
    approval_status: str,
    original_target_pct: float,
) -> ApprovalSnapshotView | None:
    if approval_status in {"", "auto_approved", "approved"}:
        return None
    modified_target_pct = (
        _coerce_float(state.get("modified_target_pct"))
        if approval_status == "modified"
        else None
    )
    return ApprovalSnapshotView(
        approval_id=str(state.get("approval_id", "") or ""),
        approval_status=approval_status,
        approval_reason=str(state.get("approval_reason", "") or ""),
        reviewer=str(state.get("reviewer", "") or ""),
        reviewer_notes=str(state.get("reviewer_notes", "") or ""),
        original_target_pct=original_target_pct,
        modified_target_pct=modified_target_pct,
    )


def _publish_execution_event(
    broker: BrokerGateway,
    *,
    event_type: str,
    report: ExecutionReportView,
    ticker: str,
) -> None:
    broker.publish_event(
        BrokerEvent(
            event_type=event_type,
            entity_type="execution",
            entity_id=report.decision_id or report.session_id or ticker,
            strategy_id=report.strategy_id,
            account_id=report.account_id,
            session_id=report.session_id,
            decision_id=report.decision_id,
            ticker=ticker,
            payload={
                "status": report.status,
                "reason": report.reason,
                "pm_action": report.pm_action,
            },
        )
    )


def _execution_status_from_order_status(status: OrderStatus) -> ExecutionStatusView:
    if status is OrderStatus.REJECTED:
        return "rejected"
    if status is OrderStatus.NEW:
        return "pending"
    if status is OrderStatus.FILLED:
        return "executed"
    if status is OrderStatus.CANCELED:
        return "failed"
    if status is OrderStatus.PARTIALLY_FILLED:
        return "failed"
    return "failed"


def _execution_event_type_for_status(status: ExecutionStatusView) -> str | None:
    if status == "pending":
        return "execution_pending"
    if status == "rejected":
        return "execution_rejected"
    if status == "failed":
        return "execution_failed"
    return None


def _report_result(report: ExecutionReportView) -> dict[str, object]:
    return {"execution_report": report.model_dump_json()}
