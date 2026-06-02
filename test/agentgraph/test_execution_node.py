from __future__ import annotations

import pytest

from agentgraph.execution_node import create_execution_node
from broker.config import BrokerConfig
from broker.events import BrokerEvent
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderType
from broker.views import ExecutionReportView
from dataflow.portfolio_manager import PortfolioManager


def _report_view(result: dict[str, object]) -> ExecutionReportView:
    execution_report = result["execution_report"]
    assert isinstance(execution_report, str)
    return ExecutionReportView.model_validate_json(execution_report)


class PendingBroker(MockBrokerEngine):
    def place_order(self, order: Order) -> Order:
        self.publish_event(
            BrokerEvent(
                event_type="order_placed",
                entity_type="order",
                entity_id=order.id,
                strategy_id=order.strategy_id,
                account_id=order.account_id,
                session_id=order.session_id,
                decision_id=order.decision_id,
                ticker=order.ticker,
                payload={"order_id": order.id, "order_status": order.status.value},
            )
        )
        return order.model_copy(deep=True)


def test_execution_node_skips_when_execution_is_disabled() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )

    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": False,
        }
    )

    report = _report_view(result)

    assert report.status == "skipped"
    assert report.order is None
    assert report.reason == "execution disabled"
    assert broker.get_orders() == []
    assert broker.get_event_log() == []


def test_execution_node_returns_hold_report_without_placing_orders() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )

    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "HOLD",
            "Target_position_pct": 0.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "held"
    assert report.order is None
    assert broker.get_orders() == []
    assert broker.get_event_log() == []


def test_execution_node_returns_held_when_target_is_already_satisfied() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 0.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "held"
    assert report.order is None
    assert broker.get_orders() == []
    assert broker.get_event_log() == []


def test_execution_node_returns_rejected_report_when_approval_rejects_trade() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )

    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "rejected",
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "rejected"
    assert report.order is None
    assert report.approval is not None
    assert report.approval.approval_status == "rejected"
    assert broker.get_orders() == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "execution_rejected"
    ]


def test_execution_node_returns_rejected_report_when_approval_times_out() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "timed_out",
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "rejected"
    assert report.order is None
    assert report.approval is not None
    assert report.approval.approval_status == "timed_out"
    assert broker.get_orders() == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "execution_rejected"
    ]


def test_execution_node_rejects_modified_approval_without_modified_target() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "modified",
            "modified_target_pct": None,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "failed"
    assert report.order is None
    assert report.reason == "missing modified target percentage"
    assert broker.get_orders() == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "execution_failed"
    ]


def test_execution_node_returns_pending_report_when_approval_is_pending() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "pending",
            "approval_id": "approval-1",
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "pending"
    assert report.order is None
    assert report.approval is not None
    assert report.approval.approval_id == "approval-1"
    assert report.approval.approval_status == "pending"
    assert broker.get_orders() == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "execution_pending"
    ]


def test_execution_node_returns_failed_report_when_market_price_is_missing() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "failed"
    assert report.order is None
    assert report.reason == "missing market price"
    assert broker.get_orders() == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "execution_failed"
    ]


def test_execution_node_places_market_order_and_serializes_execution_report() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )

    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "PM_report": "Increase exposure on breakout.",
            "execution_enabled": True,
            "session_id": "session-1",
        }
    )

    orders = broker.get_orders()

    assert len(orders) == 1
    assert orders[0].side is OrderSide.BUY
    assert orders[0].qty == pytest.approx(500.0)

    report = _report_view(result)

    assert report.status == "executed"
    assert report.order is not None
    assert report.order.id == orders[0].id
    assert report.order.status == "executed"
    assert report.order.session_id == "session-1"
    assert len(report.fills) == 1
    assert report.position_before is None
    assert report.position_after is not None
    assert report.position_after.shares == pytest.approx(500.0)
    assert report.account_after is not None
    assert report.account_after.cash == pytest.approx(49_924.975)
    assert report.account_after.equity == pytest.approx(99_924.975)
    assert report.pm_action == "BUY"
    assert report.pm_report_summary == "Increase exposure on breakout."
    assert report.session_id == "session-1"


def test_execution_node_uses_modified_target_pct_from_hitl_state() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )

    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "approval_status": "modified",
            "modified_target_pct": 20.0,
            "execution_enabled": True,
        }
    )

    orders = broker.get_orders()
    report = _report_view(result)

    assert len(orders) == 1
    assert orders[0].qty == pytest.approx(200.0)
    assert report.approval is not None
    assert report.approval.approval_status == "modified"
    assert report.approval.original_target_pct == pytest.approx(50.0)
    assert report.approval.modified_target_pct == pytest.approx(20.0)
    assert report.order is not None
    assert report.order.quantity == pytest.approx(200.0)
    assert report.position_after is not None
    assert report.position_after.shares == pytest.approx(200.0)


def test_execution_node_syncs_portfolio_manager_after_execution() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    portfolio_manager = PortfolioManager()
    execution_node = create_execution_node(broker, portfolio_manager=portfolio_manager)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)
    synced_position = portfolio_manager.get_position("AAPL")

    assert synced_position["side"] == "long"
    assert report.account_after is not None
    assert synced_position["qty_pct"] == pytest.approx(
        50_000.0 / report.account_after.equity
    )
    assert synced_position["avg_cost"] == pytest.approx(100.05)


def test_execution_node_sells_down_to_target_position() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=500,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 109.0,
                "high": 111.0,
                "low": 108.0,
                "close": 110.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "SELL",
            "Target_position_pct": 0.0,
            "PM_report": "Exit the position after the move.",
            "execution_enabled": True,
        }
    )

    orders = broker.get_orders()
    report = _report_view(result)

    assert len(orders) == 2
    assert orders[-1].side is OrderSide.SELL
    assert orders[-1].qty == pytest.approx(500.0)
    assert report.position_before is not None
    assert report.position_before.shares == pytest.approx(500.0)
    assert report.position_after is None
    assert report.order is not None
    assert report.order.status == "executed"
    assert report.pm_action == "SELL"


def test_execution_node_propagates_identity_to_report_order_fills_and_events() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
            "strategy_id": "strategy-1",
            "account_id": "account-1",
            "session_id": "session-1",
            "decision_id": "decision-1",
        }
    )

    report = _report_view(result)
    orders = broker.get_orders(account_id="account-1")
    fills = broker.get_fills(account_id="account-1")
    events = broker.get_event_log(account_id="account-1")

    assert report.strategy_id == "strategy-1"
    assert report.account_id == "account-1"
    assert report.session_id == "session-1"
    assert report.decision_id == "decision-1"
    assert report.order is not None
    assert report.order.strategy_id == "strategy-1"
    assert report.order.account_id == "account-1"
    assert len(report.fills) == 1
    assert report.fills[0].decision_id == "decision-1"
    assert len(orders) == 1
    assert orders[0].decision_id == "decision-1"
    assert len(fills) == 1
    assert fills[0].account_id == "account-1"
    assert [event.event_type for event in events] == ["order_placed", "order_filled"]
    assert all(event.decision_id == "decision-1" for event in events)


def test_execution_node_passes_client_order_id_to_broker_order() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
            "client_order_id": "client-order-1",
        }
    )

    report = _report_view(result)
    assert report.order is not None
    assert report.order.client_order_id == "client-order-1"
    assert broker.get_orders()[0].client_order_id == "client-order-1"


def test_execution_node_writes_execution_rejected_for_broker_risk_rejection() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=1_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 100.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "rejected"
    assert report.order is not None
    assert report.order.status == "rejected"
    assert report.fills == []
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "risk_check_failed",
        "order_rejected",
        "execution_rejected",
    ]


def test_execution_node_does_not_mark_pending_broker_order_as_executed() -> None:
    broker = PendingBroker(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    execution_node = create_execution_node(broker)

    result = execution_node(
        {
            "ticker": "AAPL",
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "execution_enabled": True,
        }
    )

    report = _report_view(result)

    assert report.status == "pending"
    assert report.order is not None
    assert report.order.status == "pending"
    assert report.account_after is not None
    assert report.account_after.cash == pytest.approx(100_000.0)
    assert report.account_after.equity == pytest.approx(100_000.0)
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "execution_pending",
    ]
