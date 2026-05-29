from __future__ import annotations

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderType
from dataflow.portfolio_manager import PortfolioManager


def test_portfolio_manager_syncs_broker_positions_and_clears_flat_tickers() -> None:
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

    portfolio_manager = PortfolioManager()
    portfolio_manager.sync_from_broker(broker)

    synced_position = portfolio_manager.get_position("AAPL")

    assert synced_position["side"] == "long"
    assert synced_position["qty_pct"] == pytest.approx(1_000.0 / 99_998.4995)
    assert synced_position["avg_cost"] == pytest.approx(100.05)

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
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    portfolio_manager.sync_from_broker(broker)

    flat_position = portfolio_manager.get_position("AAPL")

    assert flat_position["side"] == "flat"
    assert flat_position["qty_pct"] == pytest.approx(0.0)


def test_portfolio_manager_syncs_short_positions_with_negative_position_pct() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            allow_short=True,
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
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    portfolio_manager = PortfolioManager()
    portfolio_manager.sync_from_broker(broker)

    synced_position = portfolio_manager.get_position("AAPL")

    assert synced_position["side"] == "short"
    assert synced_position["qty_pct"] == pytest.approx(-1_000.0 / 99_998.5005)
    assert synced_position["avg_cost"] == pytest.approx(99.95)
