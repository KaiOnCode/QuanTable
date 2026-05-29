from __future__ import annotations

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import Order, OrderSide, OrderType
from dataflow.service import DataService


def test_data_service_reads_position_from_injected_broker() -> None:
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

    data_service = DataService(broker=broker)
    position = data_service.df_get_position("AAPL")

    assert position["side"] == "long"
    assert position["qty_pct"] == pytest.approx(1_000.0 / 99_998.4995)
    assert position["avg_cost"] == pytest.approx(100.05)
