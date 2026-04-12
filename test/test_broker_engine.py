from __future__ import annotations

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderStatus, OrderType


def test_market_buy_order_fills_immediately_and_updates_account_state() -> None:
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

    placed_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert placed_order.status is OrderStatus.FILLED

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.FILLED

    fills = broker.get_fills(placed_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(100.05)
    assert fills[0].fill_qty == pytest.approx(10.0)
    assert fills[0].fee == pytest.approx(1.0005)
    assert fills[0].slippage == pytest.approx(0.5)

    position = broker.get_position("AAPL")
    assert position is not None
    assert position.shares == pytest.approx(10.0)
    assert position.avg_cost == pytest.approx(100.05)
    assert position.side == "LONG"
    assert position.unrealized_pnl == pytest.approx(-0.5)

    account = broker.get_account()
    assert account.cash == pytest.approx(98_998.4995)
    assert account.equity == pytest.approx(99_998.4995)
    assert len(account.positions) == 1
    assert account.positions[0].ticker == "AAPL"


def test_limit_buy_order_stays_pending_until_a_future_bar_touches_the_limit() -> None:
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
                "open": 100.0,
                "high": 101.0,
                "low": 99.5,
                "close": 100.0,
            }
        }
    )

    placed_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            qty=10,
            limit_price=99.0,
        )
    )

    assert placed_order.status is OrderStatus.NEW
    assert broker.get_fills(placed_order.id) == []
    assert broker.get_position("AAPL") is None

    broker.on_bar(
        {
            "AAPL": {
                "open": 99.8,
                "high": 100.0,
                "low": 98.5,
                "close": 99.2,
            }
        }
    )

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.FILLED

    fills = broker.get_fills(placed_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(99.0)
    assert fills[0].fee == pytest.approx(0.99)
    assert fills[0].slippage == pytest.approx(0.0)

    position = broker.get_position("AAPL")
    assert position is not None
    assert position.shares == pytest.approx(10.0)
    assert position.avg_cost == pytest.approx(99.0)
    assert position.unrealized_pnl == pytest.approx(2.0)

    account = broker.get_account()
    assert account.cash == pytest.approx(99_009.01)
    assert account.equity == pytest.approx(100_001.01)


def test_market_sell_can_close_an_existing_long_position() -> None:
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
            qty=10,
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

    sell_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert sell_order.status is OrderStatus.FILLED
    assert broker.get_position("AAPL") is None
    assert broker.get_positions() == []

    fills = broker.get_fills(sell_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(109.945)
    assert fills[0].fee == pytest.approx(1.09945)
    assert fills[0].slippage == pytest.approx(0.55)

    account = broker.get_account()
    assert account.cash == pytest.approx(100_096.85005)
    assert account.equity == pytest.approx(100_096.85005)


def test_market_buy_is_rejected_when_cash_cannot_cover_slippage_and_fees() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=1_001.0,
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

    placed_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert placed_order.status is OrderStatus.REJECTED
    assert broker.get_fills(placed_order.id) == []
    assert broker.get_position("AAPL") is None

    account = broker.get_account()
    assert account.cash == pytest.approx(1_001.0)
    assert account.equity == pytest.approx(1_001.0)


def test_market_buy_is_rejected_when_it_would_breach_max_position_pct() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            max_position_pct=0.1,
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

    placed_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=200,
        )
    )

    assert placed_order.status is OrderStatus.REJECTED
    assert broker.get_fills(placed_order.id) == []
    assert broker.get_position("AAPL") is None

    account = broker.get_account()
    assert account.cash == pytest.approx(100_000.0)
    assert account.equity == pytest.approx(100_000.0)
