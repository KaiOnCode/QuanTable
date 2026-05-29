from datetime import timezone

import pytest
from pydantic import ValidationError

from broker.config import BrokerConfig
from broker.events import BrokerEvent, InMemoryBrokerEventSink
from broker.models import (
    AccountSnapshot,
    ExecutionReport,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)


def test_market_order_defaults_to_new_status_with_generated_metadata() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
    )

    assert order.status is OrderStatus.NEW
    assert order.limit_price is None
    assert order.strategy_id == ""
    assert order.account_id == "default"
    assert order.session_id == ""
    assert order.decision_id == ""
    assert order.id
    assert order.created_at.tzinfo == timezone.utc
    assert order.updated_at.tzinfo == timezone.utc


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(ValidationError):
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            qty=10,
        )


def test_order_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=0,
        )


def test_fill_defaults_timestamp_and_session_id() -> None:
    fill = Fill(
        order_id="order-1",
        fill_price=123.45,
        fill_qty=10,
        fee=1.23,
        slippage=0.5,
    )

    assert fill.order_id == "order-1"
    assert fill.timestamp.tzinfo == timezone.utc
    assert fill.strategy_id == ""
    assert fill.account_id == "default"
    assert fill.session_id == ""
    assert fill.decision_id == ""


def test_position_derives_side_from_share_direction() -> None:
    long_position = Position(ticker="AAPL", shares=10, avg_cost=100.0)
    short_position = Position(ticker="AAPL", shares=-5, avg_cost=100.0)
    flat_position = Position(ticker="AAPL", shares=0, avg_cost=0.0)

    assert long_position.side == "LONG"
    assert long_position.strategy_id == ""
    assert long_position.account_id == "default"
    assert long_position.session_id == ""
    assert long_position.decision_id == ""
    assert short_position.side == "SHORT"
    assert flat_position.side == "FLAT"


def test_account_snapshot_exposes_identity_defaults() -> None:
    account = AccountSnapshot(cash=100_000.0, equity=100_000.0)

    assert account.strategy_id == ""
    assert account.account_id == "default"
    assert account.session_id == ""
    assert account.decision_id == ""


def test_execution_report_preserves_nested_models_and_pm_context() -> None:
    order = Order(
        ticker="AAPL",
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        qty=10,
    )
    fill = Fill(
        order_id=order.id,
        fill_price=123.45,
        fill_qty=10,
        fee=1.23,
        slippage=0.5,
    )
    position_before = Position(ticker="AAPL", shares=0, avg_cost=0.0)
    position_after = Position(ticker="AAPL", shares=10, avg_cost=123.45)
    account_after = AccountSnapshot(
        cash=98_763.77, equity=100_000.0, positions=[position_after]
    )

    report = ExecutionReport(
        order=order,
        fills=[fill],
        position_before=position_before,
        position_after=position_after,
        account_after=account_after,
        pm_action="BUY",
        pm_report_summary="Increase exposure on breakout.",
    )

    assert report.order.id == order.id
    assert report.account_after.positions[0].ticker == "AAPL"
    assert report.position_after is not None
    assert report.position_after.side == "LONG"
    assert report.pm_action == "BUY"
    assert report.pm_report_summary == "Increase exposure on breakout."
    assert report.strategy_id == ""
    assert report.account_id == "default"
    assert report.session_id == ""
    assert report.decision_id == ""
    assert report.timestamp.tzinfo == timezone.utc


def test_broker_event_uses_independent_default_details() -> None:
    first_event = BrokerEvent(event_type="order_placed")
    second_event = BrokerEvent(event_type="order_filled")

    first_event.details["order_id"] = "order-1"

    assert first_event.event_id == ""
    assert first_event.sequence == 0
    assert first_event.timestamp.tzinfo == timezone.utc
    assert first_event.entity_type == ""
    assert first_event.entity_id == ""
    assert first_event.strategy_id == ""
    assert first_event.account_id == "default"
    assert first_event.session_id == ""
    assert first_event.decision_id == ""
    assert first_event.ticker == ""
    assert first_event.payload == {}
    assert first_event.details == {"order_id": "order-1"}
    assert second_event.details == {}


def test_in_memory_broker_event_sink_assigns_sequence_per_strategy_account() -> None:
    sink = InMemoryBrokerEventSink()

    first_a = sink.publish(
        BrokerEvent(
            event_type="order_placed",
            entity_type="order",
            entity_id="order-a-1",
            strategy_id="strategy-a",
            account_id="account-a",
            payload={"ticker": "AAPL"},
        )
    )
    second_a = sink.publish(
        BrokerEvent(
            event_type="order_filled",
            entity_type="order",
            entity_id="order-a-1",
            strategy_id="strategy-a",
            account_id="account-a",
            payload={"ticker": "AAPL"},
        )
    )
    first_b = sink.publish(
        BrokerEvent(
            event_type="order_placed",
            entity_type="order",
            entity_id="order-b-1",
            strategy_id="strategy-b",
            account_id="account-b",
            payload={"ticker": "MSFT"},
        )
    )

    assert first_a.event_id
    assert first_a.sequence == 1
    assert second_a.sequence == 2
    assert first_b.sequence == 1
    assert [
        event.sequence
        for event in sink.load_events(strategy_id="strategy-a", account_id="account-a")
    ] == [1, 2]
    assert [
        event.event_type for event in sink.load_events(event_type="order_placed")
    ] == [
        "order_placed",
        "order_placed",
    ]
    assert sink.load_events(session_id="missing") == []


def test_broker_config_exposes_phase_one_defaults_and_overrides() -> None:
    default_config = BrokerConfig()
    overridden_config = BrokerConfig(execution_timing="next_open", allow_short=False)

    assert default_config.initial_cash == 100_000.0
    assert default_config.commission_rate == 0.001
    assert default_config.slippage_rate == 0.0005
    assert default_config.execution_timing == "close_bar"
    assert default_config.max_position_pct == 1.0
    assert default_config.max_total_position_pct == 1.0
    assert default_config.allow_short is True
    assert overridden_config.execution_timing == "next_open"
    assert overridden_config.allow_short is False
