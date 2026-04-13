from __future__ import annotations

from collections.abc import Callable, Mapping
from math import floor
from typing import TYPE_CHECKING

from broker.gateway import BrokerGateway
from broker.models import ExecutionReport, Order, OrderSide, OrderType

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
        Callable[[ExecutionReport, Mapping[str, object]], None] | None
    ) = None,
):
    """Create the execution node that runs after PM decisions."""

    def execution_node(state: Mapping[str, object]) -> dict[str, object]:
        if not state.get("execution_enabled", False):
            return {}
        approval_status = str(state.get("approval_status", "auto_approved"))
        if approval_status == "rejected":
            return {"execution_report": "REJECTED — 审批未通过，不执行"}
        action = str(state.get("Action", "HOLD")).upper()
        if action == "HOLD":
            return {"execution_report": "HOLD — 无需执行"}

        ticker = str(state.get("ticker", ""))
        reference_price = broker.get_latest_price(ticker)
        if not ticker or reference_price is None:
            return {"execution_report": "REJECTED — 缺少市场价格，无法执行"}

        account_before = broker.get_account()
        position_before = broker.get_position(ticker)
        current_shares = position_before.shares if position_before is not None else 0.0
        target_pct_source = (
            state.get("modified_target_pct", state.get("Target_position_pct", 0.0))
            if approval_status == "modified"
            else state.get("Target_position_pct", 0.0)
        )
        target_pct = _coerce_float(target_pct_source)
        target_fraction = max(min(target_pct / 100.0, 1.0), -1.0)
        target_position_value = account_before.equity * target_fraction
        target_shares = float(floor(target_position_value / reference_price))
        delta_shares = target_shares - current_shares

        if delta_shares == 0:
            return {"execution_report": "HOLD — 目标仓位已满足"}

        order = Order(
            ticker=ticker,
            side=OrderSide.BUY if delta_shares > 0 else OrderSide.SELL,
            type=OrderType.MARKET,
            qty=abs(delta_shares),
            session_id=str(state.get("session_id", "") or ""),
        )
        placed_order = broker.place_order(order)
        fills = broker.get_fills(placed_order.id)
        position_after = broker.get_position(ticker)
        account_after = broker.get_account()

        report = ExecutionReport(
            order=placed_order,
            fills=fills,
            position_before=position_before,
            position_after=position_after,
            account_after=account_after,
            pm_action=action,
            pm_report_summary=str(state.get("PM_report", "") or ""),
            session_id=str(state.get("session_id", "") or ""),
        )
        if portfolio_manager is not None:
            portfolio_manager.sync_from_broker(broker)
        if on_execution_complete is not None:
            on_execution_complete(report, state)
        return {"execution_report": report.model_dump_json()}

    return execution_node
