from __future__ import annotations

import pytest

from agentgraph.execution_node import create_execution_node
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import ExecutionReport, Order, OrderSide, OrderStatus, OrderType
from dataflow.portfolio_manager import PortfolioManager


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

    assert result == {}
    assert broker.get_orders() == []


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

    assert result == {"execution_report": "HOLD — 无需执行"}
    assert broker.get_orders() == []


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

    execution_report = result["execution_report"]
    assert isinstance(execution_report, str)
    report = ExecutionReport.model_validate_json(execution_report)

    assert report.order.id == orders[0].id
    assert report.order.status is OrderStatus.FILLED
    assert report.order.session_id == "session-1"
    assert len(report.fills) == 1
    assert report.position_before is None
    assert report.position_after is not None
    assert report.position_after.shares == pytest.approx(500.0)
    assert report.account_after.cash == pytest.approx(49_924.975)
    assert report.account_after.equity == pytest.approx(99_924.975)
    assert report.pm_action == "BUY"
    assert report.pm_report_summary == "Increase exposure on breakout."
    assert report.session_id == "session-1"


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

    execution_report = result["execution_report"]
    assert isinstance(execution_report, str)
    report = ExecutionReport.model_validate_json(execution_report)
    synced_position = portfolio_manager.get_position("AAPL")

    assert synced_position["side"] == "long"
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
    execution_report = result["execution_report"]
    assert isinstance(execution_report, str)
    report = ExecutionReport.model_validate_json(execution_report)

    assert len(orders) == 2
    assert orders[-1].side is OrderSide.SELL
    assert orders[-1].qty == pytest.approx(500.0)
    assert report.position_before is not None
    assert report.position_before.shares == pytest.approx(500.0)
    assert report.position_after is None
    assert report.order.status is OrderStatus.FILLED
    assert report.pm_action == "SELL"
