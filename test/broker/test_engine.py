from __future__ import annotations

from datetime import UTC, datetime

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.events import InMemoryBrokerEventSink, ORDER_EVENT_PAYLOAD_KEYS
from broker.ledger import TradeLedger
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


def test_market_order_with_next_open_timing_fills_on_next_bar_open() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )

    placed_order = broker.place_order(
        Order(ticker="AAPL", side=OrderSide.BUY, type=OrderType.MARKET, qty=10)
    )

    assert placed_order.status is OrderStatus.NEW
    assert broker.get_fills(placed_order.id) == []
    assert [event.event_type for event in broker.get_event_log()] == ["order_placed"]

    broker.on_bar(
        {
            "AAPL": {"open": 105.0, "high": 106.0, "low": 104.0, "close": 105.5},
        }
    )

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.FILLED
    fills = broker.get_fills(placed_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(105.0)
    position = broker.get_position("AAPL")
    assert position is not None
    assert position.avg_cost == pytest.approx(105.0)
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "order_filled",
    ]


def test_next_open_market_order_revalidates_risk_at_open_price() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=1_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
        }
    )
    placed_order = broker.place_order(
        Order(ticker="AAPL", side=OrderSide.BUY, type=OrderType.MARKET, qty=100)
    )

    broker.on_bar(
        {
            "AAPL": {"open": 20.0, "high": 20.0, "low": 20.0, "close": 20.0},
        }
    )

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.REJECTED
    assert broker.get_fills(placed_order.id) == []
    assert broker.get_account().cash == pytest.approx(1_000.0)
    assert [event.event_type for event in broker.get_event_log()] == [
        "order_placed",
        "risk_check_failed",
        "order_rejected",
    ]


def test_next_open_risk_rejection_events_use_historical_execution_clock() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=1_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    signal_time = datetime(2024, 1, 2, tzinfo=UTC)
    execution_time = datetime(2024, 1, 3, tzinfo=UTC)
    broker.on_bar(
        {
            "AAPL": {"open": 10.0, "high": 10.0, "low": 10.0, "close": 10.0},
        },
        timestamp=signal_time,
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=100,
            created_at=signal_time,
            updated_at=signal_time,
        )
    )

    broker.on_bar(
        {
            "AAPL": {"open": 20.0, "high": 20.0, "low": 20.0, "close": 20.0},
        },
        timestamp=execution_time,
    )

    assert [event.timestamp for event in broker.get_event_log()] == [
        signal_time,
        execution_time,
        execution_time,
    ]


def test_next_open_fill_callback_uses_open_valuation_not_same_bar_close() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    ledger = TradeLedger()
    broker.register_on_fill(ledger.record_fill)
    fill_accounts = []
    broker.register_on_fill(
        lambda _fill, _position, account: fill_accounts.append(account)
    )
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        },
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
    )
    broker.place_order(
        Order(ticker="AAPL", side=OrderSide.BUY, type=OrderType.MARKET, qty=10)
    )

    broker.on_bar(
        {
            "AAPL": {"open": 109.0, "high": 151.0, "low": 108.0, "close": 150.0},
        },
        timestamp=datetime(2024, 1, 3, tzinfo=UTC),
    )

    recorded_trade = ledger.to_trades_dataframe().iloc[0]
    assert recorded_trade["equity_after"] == pytest.approx(100_000.0)
    assert fill_accounts[0].timestamp == datetime(2024, 1, 3, tzinfo=UTC)
    assert broker.get_account().equity == pytest.approx(100_410.0)


def test_backtest_order_events_use_the_historical_signal_and_execution_clock() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
            execution_timing="next_open",
        )
    )
    signal_time = datetime(2024, 1, 2, tzinfo=UTC)
    execution_time = datetime(2024, 1, 3, tzinfo=UTC)
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        },
        timestamp=signal_time,
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            created_at=signal_time,
            updated_at=signal_time,
        )
    )

    broker.on_bar(
        {
            "AAPL": {"open": 109.0, "high": 110.0, "low": 108.0, "close": 109.0},
        },
        timestamp=execution_time,
    )

    events = broker.get_event_log()
    assert [event.event_type for event in events] == ["order_placed", "order_filled"]
    assert [event.timestamp for event in events] == [signal_time, execution_time]


def test_limit_order_fill_uses_the_historical_bar_timestamp() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 100.0, "high": 101.0, "low": 99.5, "close": 100.0},
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
    execution_time = datetime(2024, 1, 3, tzinfo=UTC)

    broker.on_bar(
        {
            "AAPL": {"open": 100.0, "high": 101.0, "low": 98.0, "close": 99.0},
        },
        timestamp=execution_time,
    )

    stored_order = broker.get_order(placed_order.id)
    fills = broker.get_fills(placed_order.id)
    assert stored_order is not None
    assert stored_order.updated_at == execution_time
    assert len(fills) == 1
    assert fills[0].timestamp == execution_time


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


def test_canceling_a_pending_limit_order_prevents_future_fills() -> None:
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
    canceled_order = broker.cancel_order(placed_order.id)

    assert canceled_order.status is OrderStatus.CANCELED
    assert [order.id for order in broker.get_orders(OrderStatus.CANCELED)] == [
        placed_order.id
    ]
    assert broker.get_orders(OrderStatus.NEW) == []

    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 100.0,
                "low": 98.0,
                "close": 98.5,
            }
        }
    )

    stored_order = broker.get_order(placed_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.CANCELED
    assert broker.get_fills(placed_order.id) == []
    assert broker.get_position("AAPL") is None


def test_limit_sell_order_stays_pending_until_a_future_bar_touches_the_limit() -> None:
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

    limit_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            type=OrderType.LIMIT,
            qty=10,
            limit_price=105.0,
        )
    )

    assert limit_order.status is OrderStatus.NEW
    assert broker.get_position("AAPL") is not None

    broker.on_bar(
        {
            "AAPL": {
                "open": 103.0,
                "high": 106.0,
                "low": 102.0,
                "close": 104.0,
            }
        }
    )

    stored_order = broker.get_order(limit_order.id)
    assert stored_order is not None
    assert stored_order.status is OrderStatus.FILLED

    fills = broker.get_fills(limit_order.id)
    assert len(fills) == 1
    assert fills[0].fill_price == pytest.approx(105.0)
    assert fills[0].fee == pytest.approx(1.05)
    assert fills[0].slippage == pytest.approx(0.0)

    assert broker.get_position("AAPL") is None
    account = broker.get_account()
    assert account.cash == pytest.approx(100_047.4495)
    assert account.equity == pytest.approx(100_047.4495)


def test_market_sell_can_open_a_short_and_market_buy_can_cover_it() -> None:
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

    short_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert short_order.status is OrderStatus.FILLED
    short_position = broker.get_position("AAPL")
    assert short_position is not None
    assert short_position.shares == pytest.approx(-10.0)
    assert short_position.avg_cost == pytest.approx(99.95)
    assert short_position.side == "SHORT"
    assert short_position.unrealized_pnl == pytest.approx(-0.5)

    account_after_short = broker.get_account()
    assert account_after_short.cash == pytest.approx(100_998.5005)
    assert account_after_short.equity == pytest.approx(99_998.5005)

    broker.on_bar(
        {
            "AAPL": {
                "open": 91.0,
                "high": 92.0,
                "low": 89.0,
                "close": 90.0,
            }
        }
    )

    cover_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert cover_order.status is OrderStatus.FILLED
    assert broker.get_position("AAPL") is None

    fills = broker.get_fills()
    assert len(fills) == 2
    assert fills[-1].fill_price == pytest.approx(90.045)
    assert fills[-1].fee == pytest.approx(0.90045)
    assert fills[-1].slippage == pytest.approx(0.45)

    account_after_cover = broker.get_account()
    assert account_after_cover.cash == pytest.approx(100_097.15005)
    assert account_after_cover.equity == pytest.approx(100_097.15005)


def test_market_short_sell_is_rejected_when_shorting_is_disabled() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            allow_short=False,
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
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    assert placed_order.status is OrderStatus.REJECTED
    assert broker.get_fills() == []
    assert broker.get_position("AAPL") is None

    account = broker.get_account()
    assert account.cash == pytest.approx(100_000.0)
    assert account.equity == pytest.approx(100_000.0)


def test_market_fill_emits_order_and_fill_callbacks_and_records_events() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    order_statuses: list[OrderStatus] = []
    fill_callback_payloads: list[tuple[float, float, float]] = []

    def on_order(order: Order) -> None:
        order_statuses.append(order.status)

    def on_fill(fill_price: float, shares: float, equity: float) -> None:
        fill_callback_payloads.append((fill_price, shares, equity))

    broker.register_on_order(on_order)
    broker.register_on_fill(
        lambda fill, position, account: on_fill(
            fill.fill_price,
            position.shares,
            account.equity,
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

    assert order_statuses == [OrderStatus.NEW, OrderStatus.FILLED]
    assert fill_callback_payloads == [
        (pytest.approx(100.05), 10.0, pytest.approx(99_998.4995))
    ]

    event_types = [event.event_type for event in broker.get_event_log()]
    assert event_types == ["order_placed", "order_filled"]
    assert broker.get_event_log()[0].ticker == "AAPL"
    assert broker.get_event_log()[1].details["order_status"] == "FILLED"


def test_engine_publishes_events_with_per_strategy_account_sequences() -> None:
    event_sink = InMemoryBrokerEventSink()
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        ),
        event_sink=event_sink,
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            },
            "MSFT": {
                "open": 199.0,
                "high": 201.0,
                "low": 198.0,
                "close": 200.0,
            },
        }
    )

    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            strategy_id="strategy-a",
            account_id="account-a",
            session_id="session-a",
            decision_id="decision-a",
        )
    )
    broker.place_order(
        Order(
            ticker="MSFT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=5,
            strategy_id="strategy-b",
            account_id="account-b",
            session_id="session-b",
            decision_id="decision-b",
        )
    )

    account_a_events = event_sink.load_events(account_id="account-a")
    account_b_events = event_sink.load_events(account_id="account-b")

    assert [event.sequence for event in account_a_events] == [1, 2]
    assert [event.sequence for event in account_b_events] == [1, 2]
    assert [event.event_type for event in account_a_events] == [
        "order_placed",
        "order_filled",
    ]
    assert account_a_events[0].entity_type == "order"
    assert account_a_events[0].entity_id
    assert account_a_events[0].strategy_id == "strategy-a"
    assert account_a_events[0].session_id == "session-a"
    assert account_a_events[0].decision_id == "decision-a"
    assert account_a_events[0].payload["order_status"] == "NEW"
    assert broker.get_event_log(account_id="account-a") == account_a_events
    assert [
        event.event_type
        for event in broker.get_event_log(
            account_id="account-b",
            decision_id="decision-b",
        )
    ] == ["order_placed", "order_filled"]


def test_client_order_id_is_idempotent_within_strategy_account_scope() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        )
    )
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    first_order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
        strategy_id="strategy-1",
        account_id="account-1",
        client_order_id="client-order-1",
    )
    duplicate_order = first_order.model_copy(update={"id": "different-order-id"})

    first_result = broker.place_order(first_order)
    duplicate_result = broker.place_order(duplicate_order)

    assert duplicate_result.id == first_result.id
    assert duplicate_result.status is OrderStatus.FILLED
    assert len(broker.get_orders(account_id="account-1")) == 1
    assert len(broker.get_fills(account_id="account-1")) == 1
    assert [
        event.event_type for event in broker.get_event_log(account_id="account-1")
    ] == [
        "order_placed",
        "order_filled",
    ]
    assert (
        broker.get_event_log(account_id="account-1")[0].payload["client_order_id"]
        == "client-order-1"
    )


def test_order_event_payload_contains_minimal_contract_fields() -> None:
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0},
        }
    )
    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            client_order_id="client-order-1",
        )
    )

    placed_event = broker.get_event_log()[0]

    assert set(ORDER_EVENT_PAYLOAD_KEYS).issubset(placed_event.payload)
    assert placed_event.payload["order_id"]
    assert placed_event.payload["client_order_id"] == "client-order-1"
    assert placed_event.payload["order_status"] == "NEW"


def test_engine_preserves_injected_falsy_event_sink() -> None:
    class FalsyEventSink(InMemoryBrokerEventSink):
        def __bool__(self) -> bool:
            return False

    event_sink = FalsyEventSink()
    broker = MockBrokerEngine(BrokerConfig(), event_sink=event_sink)
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

    assert [event.event_type for event in event_sink.load_events()] == [
        "order_placed",
        "order_filled",
    ]


def test_orders_with_different_account_ids_keep_isolated_state() -> None:
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
            },
            "MSFT": {
                "open": 199.0,
                "high": 201.0,
                "low": 198.0,
                "close": 200.0,
            },
        }
    )

    account_a_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            strategy_id="strategy-a",
            account_id="account-a",
        )
    )
    account_b_order = broker.place_order(
        Order(
            ticker="MSFT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=3,
            strategy_id="strategy-b",
            account_id="account-b",
        )
    )

    account_a = broker.get_account(account_id="account-a")
    account_b = broker.get_account(account_id="account-b")

    assert account_a.account_id == "account-a"
    assert account_a.strategy_id == "strategy-a"
    assert account_a.cash == pytest.approx(98_998.4995)
    assert {position.ticker for position in account_a.positions} == {"AAPL"}
    assert broker.get_position("AAPL", account_id="account-a") is not None
    assert broker.get_position("MSFT", account_id="account-a") is None
    assert [order.id for order in broker.get_orders(account_id="account-a")] == [
        account_a_order.id
    ]
    assert [fill.order_id for fill in broker.get_fills(account_id="account-a")] == [
        account_a_order.id
    ]
    assert [
        event.event_type for event in broker.get_event_log(account_id="account-a")
    ] == ["order_placed", "order_filled"]

    assert account_b.account_id == "account-b"
    assert account_b.strategy_id == "strategy-b"
    assert account_b.cash == pytest.approx(99_399.0997)
    assert {position.ticker for position in account_b.positions} == {"MSFT"}
    assert broker.get_position("AAPL", account_id="account-b") is None
    assert broker.get_position("MSFT", account_id="account-b") is not None
    assert [order.id for order in broker.get_orders(account_id="account-b")] == [
        account_b_order.id
    ]
    assert [fill.order_id for fill in broker.get_fills(account_id="account-b")] == [
        account_b_order.id
    ]
    assert [
        event.event_type for event in broker.get_event_log(account_id="account-b")
    ] == ["order_placed", "order_filled"]

    assert broker.get_account().cash == pytest.approx(100_000.0)
    assert broker.get_positions() == []
    assert broker.get_orders() == []
    assert broker.get_fills() == []


def test_default_queries_do_not_cross_non_default_accounts() -> None:
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
    filled_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            account_id="account-a",
        )
    )
    pending_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            qty=5,
            limit_price=95.0,
            account_id="account-a",
        )
    )

    assert broker.get_order(filled_order.id) is None
    assert broker.get_fills(filled_order.id) == []
    assert broker.get_event_log() == []
    with pytest.raises(KeyError):
        broker.cancel_order(pending_order.id)

    canceled_order = broker.cancel_order(pending_order.id, account_id="account-a")

    assert canceled_order.status is OrderStatus.CANCELED
    assert broker.get_order(filled_order.id, account_id="account-a") is not None
    assert len(broker.get_fills(filled_order.id, account_id="account-a")) == 1
    assert len(broker.get_fills(filled_order.id, account_id=None)) == 1
    assert [event.event_type for event in broker.get_event_log(account_id=None)] == [
        "order_placed",
        "order_filled",
        "order_placed",
        "order_canceled",
    ]


def test_rejected_and_canceled_orders_are_recorded_in_event_log() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
            allow_short=False,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
            }
        }
    )

    rejected_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            qty=5,
        )
    )
    pending_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            qty=5,
            limit_price=95.0,
        )
    )
    canceled_order = broker.cancel_order(pending_order.id)

    assert rejected_order.status is OrderStatus.REJECTED
    assert canceled_order.status is OrderStatus.CANCELED

    event_types = [event.event_type for event in broker.get_event_log()]
    assert event_types == [
        "order_placed",
        "risk_check_failed",
        "order_rejected",
        "order_placed",
        "order_canceled",
    ]
    assert broker.get_event_log()[1].details["reason"] == "short selling is disabled"
    assert broker.get_event_log()[-1].details["order_id"] == pending_order.id


def test_account_snapshot_tracks_multiple_tickers_through_public_queries() -> None:
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
            },
            "MSFT": {
                "open": 199.0,
                "high": 201.0,
                "low": 198.0,
                "close": 200.0,
            },
        }
    )

    aapl_order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )
    msft_order = broker.place_order(
        Order(
            ticker="MSFT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=5,
        )
    )

    assert aapl_order.status is OrderStatus.FILLED
    assert msft_order.status is OrderStatus.FILLED

    positions = broker.get_positions()
    assert {position.ticker for position in positions} == {"AAPL", "MSFT"}

    account = broker.get_account()
    assert account.cash == pytest.approx(97_996.999)
    assert account.equity == pytest.approx(99_996.999)
    assert {position.ticker for position in account.positions} == {"AAPL", "MSFT"}


def test_legacy_account_snapshot_keeps_default_identity_for_global_account() -> None:
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
            },
            "MSFT": {
                "open": 199.0,
                "high": 201.0,
                "low": 198.0,
                "close": 200.0,
            },
        }
    )

    broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
            strategy_id="strategy-a",
            account_id="account-a",
        )
    )
    broker.place_order(
        Order(
            ticker="MSFT",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=5,
            strategy_id="strategy-b",
            account_id="account-b",
        )
    )

    account = broker.get_account()

    assert account.strategy_id == ""
    assert account.account_id == "default"
    assert account.session_id == ""
    assert account.decision_id == ""
