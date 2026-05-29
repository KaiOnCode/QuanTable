from __future__ import annotations

from datetime import datetime, timezone

import pytest

from broker.events import BrokerEvent
from broker.ledger import LedgerFillRecord
from broker.models import (
    AccountSnapshot,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from broker.views import (
    ApprovalSnapshotView,
    to_broker_event_view,
    to_execution_status_report_view,
    to_order_view,
    to_performance_metrics_view,
    to_position_view,
    to_trade_view,
)


def test_order_view_maps_internal_enums_to_frontend_values() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
    )

    pending_view = to_order_view(order, fills=[])
    filled_view = to_order_view(
        order.model_copy(update={"status": OrderStatus.FILLED}),
        fills=[],
    )
    canceled_view = to_order_view(
        order.model_copy(update={"status": OrderStatus.CANCELED}),
        fills=[],
    )
    rejected_view = to_order_view(
        order.model_copy(update={"status": OrderStatus.REJECTED}),
        fills=[],
    )

    assert pending_view.side == "buy"
    assert pending_view.order_type == "market"
    assert pending_view.status == "pending"
    assert filled_view.status == "executed"
    assert canceled_view.status == "cancelled"
    assert rejected_view.status == "rejected"


def test_order_view_rejects_partially_filled_status_until_contract_defines_it() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        status=OrderStatus.PARTIALLY_FILLED,
    )

    with pytest.raises(ValueError, match="unsupported order status"):
        to_order_view(order, fills=[])


def test_position_and_performance_views_expose_percentage_points() -> None:
    position = Position(ticker="AAPL", shares=10, avg_cost=100.0)

    position_view = to_position_view(
        position,
        account_equity=2_000.0,
        current_price=110.0,
    )
    metrics_view = to_performance_metrics_view(
        {
            "total_return": 0.1234,
            "annualized_return": 0.2,
            "max_drawdown": 0.05,
            "win_rate": 0.625,
            "sharpe_ratio": 1.5,
            "number_of_trades": 4,
        }
    )

    assert position_view.side == "long"
    assert position_view.weight_pct == pytest.approx(55.0)
    assert metrics_view.cumulative_return_pct == pytest.approx(12.34)
    assert metrics_view.total_return_pct == pytest.approx(12.34)
    assert metrics_view.annualized_return_pct == pytest.approx(20.0)
    assert metrics_view.max_drawdown_pct == pytest.approx(5.0)
    assert metrics_view.win_rate_pct == pytest.approx(62.5)


def test_order_view_aggregates_fills() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        status=OrderStatus.FILLED,
    )
    fills = [
        Fill(
            order_id=order.id,
            fill_price=100.0,
            fill_qty=4,
            fee=0.4,
            slippage=0.1,
        ),
        Fill(
            order_id=order.id,
            fill_price=110.0,
            fill_qty=6,
            fee=0.66,
            slippage=0.2,
        ),
    ]

    view = to_order_view(order, fills=fills)
    empty_view = to_order_view(order, fills=[])

    assert view.filled_quantity == pytest.approx(10.0)
    assert view.filled_avg_price == pytest.approx(106.0)
    assert view.commission == pytest.approx(1.06)
    assert empty_view.filled_quantity == pytest.approx(0.0)
    assert empty_view.filled_avg_price is None
    assert empty_view.commission == pytest.approx(0.0)


def test_position_view_reports_price_source() -> None:
    position = Position(ticker="AAPL", shares=10, avg_cost=100.0)

    market_view = to_position_view(
        position,
        account_equity=1_000.0,
        current_price=120.0,
        last_close=115.0,
    )
    last_close_view = to_position_view(
        position,
        account_equity=1_000.0,
        last_close=115.0,
    )
    fallback_view = to_position_view(position, account_equity=1_000.0)

    assert market_view.current_price == pytest.approx(120.0)
    assert market_view.price_source == "market"
    assert last_close_view.current_price == pytest.approx(115.0)
    assert last_close_view.price_source == "last_close"
    assert fallback_view.current_price == pytest.approx(100.0)
    assert fallback_view.price_source == "avg_cost_fallback"


def test_trade_view_is_derived_from_ledger_record() -> None:
    traded_at = datetime(2026, 4, 13, tzinfo=timezone.utc)
    position = Position(ticker="AAPL", shares=10, avg_cost=100.05)
    account = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[position],
    )
    record = LedgerFillRecord(
        fill=Fill(
            order_id="order-1",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
            timestamp=traded_at,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        ),
        ticker="AAPL",
        side="BUY",
        realized_pnl=-1.5005,
        position_after=position,
        account_after=account,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    view = to_trade_view(record)

    assert view.order_id == "order-1"
    assert view.ticker == "AAPL"
    assert view.side == "buy"
    assert view.quantity == pytest.approx(10.0)
    assert view.price == pytest.approx(100.05)
    assert view.realized_pnl == pytest.approx(-1.5005)
    assert view.account_id == "account-1"


def test_trade_view_rejects_unknown_ledger_side() -> None:
    position = Position(ticker="AAPL", shares=10, avg_cost=100.05)
    account = AccountSnapshot(cash=98_998.4995, equity=99_998.4995)
    record = LedgerFillRecord(
        fill=Fill(
            order_id="order-1",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
        ),
        ticker="AAPL",
        side="OPEN",
        realized_pnl=-1.5005,
        position_after=position,
        account_after=account,
    )

    with pytest.raises(ValueError, match="unknown ledger trade side"):
        to_trade_view(record)


def test_status_report_serializer_supports_no_order_execution_branches() -> None:
    view = to_execution_status_report_view(
        status="pending",
        reason="waiting for approval",
        ticker="AAPL",
        pm_action="BUY",
        pm_report_summary="Increase exposure.",
        approval=ApprovalSnapshotView(
            approval_id="approval-1",
            approval_status="pending",
            original_target_pct=50.0,
        ),
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    assert view.status == "pending"
    assert view.order is None
    assert view.fills == []
    assert view.approval is not None
    assert view.approval.approval_status == "pending"
    assert view.reason == "waiting for approval"
    assert view.account_id == "account-1"
    assert view.decision_id == "decision-1"


def test_broker_event_view_uses_payload_contract() -> None:
    event = BrokerEvent(
        event_id="event-1",
        sequence=7,
        event_type="order_filled",
        entity_type="order",
        entity_id="order-1",
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
        payload={"ticker": "AAPL"},
    )

    view = to_broker_event_view(event)

    assert view.event_id == "event-1"
    assert view.sequence == 7
    assert view.event_type == "order_filled"
    assert view.payload == {"ticker": "AAPL"}
