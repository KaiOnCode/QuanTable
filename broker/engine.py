from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from broker.config import BrokerConfig
from broker.gateway import BrokerGateway
from broker.models import (
    AccountSnapshot,
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from broker.risk_checks import PreTradeRiskChecker


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BarData(TypedDict):
    open: float
    high: float
    low: float
    close: float


class MockBrokerEngine(BrokerGateway):
    def __init__(self, config: BrokerConfig):
        self._config = config
        self._risk_checker = PreTradeRiskChecker(config)
        self._cash = config.initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        self._fills: list[Fill] = []
        self._latest_bars: dict[str, BarData] = {}

    def on_bar(self, bars: dict[str, BarData]) -> None:
        self._latest_bars.update(bars)
        for order in list(self._orders.values()):
            if (
                order.status is OrderStatus.NEW
                and order.type is OrderType.LIMIT
                and order.ticker in bars
            ):
                self._try_fill_limit(order, bars[order.ticker])

    def get_account(self) -> AccountSnapshot:
        positions = self.get_positions()
        equity = self._cash + sum(
            position.shares * self._get_mark_price(position.ticker, position.avg_cost)
            for position in positions
        )
        return AccountSnapshot(
            cash=self._cash,
            equity=equity,
            positions=positions,
        )

    def get_positions(self) -> list[Position]:
        return [
            self._build_position_view(position)
            for position in self._positions.values()
            if position.shares != 0
        ]

    def get_position(self, ticker: str) -> Position | None:
        position = self._positions.get(ticker)
        if position is None or position.shares == 0:
            return None
        return self._build_position_view(position)

    def place_order(self, order: Order) -> Order:
        stored_order = order.model_copy(deep=True)
        stored_order.updated_at = _utc_now()
        self._orders[stored_order.id] = stored_order

        reference_price = self._get_reference_price(stored_order.ticker)
        account_before = self.get_account()
        passed, _reason = self._risk_checker.check(
            stored_order,
            account_before,
            reference_price=reference_price,
        )

        if not passed or reference_price is None:
            stored_order.status = OrderStatus.REJECTED
            stored_order.updated_at = _utc_now()
            self._orders[stored_order.id] = stored_order
            return stored_order.model_copy(deep=True)

        if stored_order.type is OrderType.MARKET:
            self._try_fill_market(stored_order, reference_price)

        return stored_order.model_copy(deep=True)

    def cancel_order(self, order_id: str) -> Order:
        order = self._orders[order_id]
        order.status = OrderStatus.CANCELED
        order.updated_at = _utc_now()
        return order.model_copy(deep=True)

    def get_order(self, order_id: str) -> Order | None:
        order = self._orders.get(order_id)
        if order is None:
            return None
        return order.model_copy(deep=True)

    def get_orders(self, status: OrderStatus | None = None) -> list[Order]:
        orders = [order.model_copy(deep=True) for order in self._orders.values()]
        if status is None:
            return orders
        return [order for order in orders if order.status is status]

    def get_fills(self, order_id: str | None = None) -> list[Fill]:
        fills = [fill.model_copy(deep=True) for fill in self._fills]
        if order_id is None:
            return fills
        return [fill for fill in fills if fill.order_id == order_id]

    def _try_fill_market(self, order: Order, reference_price: float) -> None:
        if order.side is OrderSide.BUY:
            fill_price = reference_price * (1 + self._config.slippage_rate)
        else:
            fill_price = reference_price * (1 - self._config.slippage_rate)

        self._execute_fill(
            order, fill_price=fill_price, reference_price=reference_price
        )

    def _try_fill_limit(self, order: Order, bar: BarData) -> None:
        limit_price = order.limit_price
        if limit_price is None:
            return

        is_triggered = (
            bar["low"] <= limit_price
            if order.side is OrderSide.BUY
            else bar["high"] >= limit_price
        )
        if not is_triggered:
            return

        account_before = self.get_account()
        passed, _reason = self._risk_checker.check(
            order,
            account_before,
            reference_price=limit_price,
        )
        if not passed:
            order.status = OrderStatus.REJECTED
            order.updated_at = _utc_now()
            return

        self._execute_fill(order, fill_price=limit_price, reference_price=limit_price)

    def _execute_fill(
        self,
        order: Order,
        *,
        fill_price: float,
        reference_price: float,
    ) -> None:
        signed_qty = order.qty if order.side is OrderSide.BUY else -order.qty
        signed_trade_value = fill_price * signed_qty
        fee = abs(signed_trade_value) * self._config.commission_rate
        ideal_trade_value = reference_price * signed_qty
        slippage = abs(ideal_trade_value - signed_trade_value)

        updated_position = self._calculate_next_position(
            ticker=order.ticker,
            signed_qty=signed_qty,
            fill_price=fill_price,
            session_id=order.session_id,
        )

        if updated_position is None:
            self._positions.pop(order.ticker, None)
        else:
            self._positions[order.ticker] = updated_position
        self._cash -= signed_trade_value
        self._cash -= fee
        self._fills.append(
            Fill(
                order_id=order.id,
                fill_price=fill_price,
                fill_qty=order.qty,
                fee=fee,
                slippage=slippage,
                session_id=order.session_id,
            )
        )
        order.status = OrderStatus.FILLED
        order.updated_at = _utc_now()
        self._orders[order.id] = order

    def _build_position_view(self, position: Position) -> Position:
        mark_price = self._get_mark_price(position.ticker, position.avg_cost)
        return Position(
            ticker=position.ticker,
            shares=position.shares,
            avg_cost=position.avg_cost,
            unrealized_pnl=(mark_price - position.avg_cost) * position.shares,
            session_id=position.session_id,
        )

    def _get_reference_price(self, ticker: str) -> float | None:
        bar = self._latest_bars.get(ticker)
        if bar is None:
            return None
        return float(bar["close"])

    def _get_mark_price(self, ticker: str, fallback: float) -> float:
        reference_price = self._get_reference_price(ticker)
        if reference_price is None:
            return fallback
        return reference_price

    def _calculate_next_position(
        self,
        *,
        ticker: str,
        signed_qty: float,
        fill_price: float,
        session_id: str,
    ) -> Position | None:
        existing_position = self._positions.get(ticker)
        if existing_position is None or existing_position.shares == 0:
            return Position(
                ticker=ticker,
                shares=signed_qty,
                avg_cost=fill_price,
                session_id=session_id,
            )

        shares_before = existing_position.shares
        shares_after = shares_before + signed_qty
        if shares_after == 0:
            return None

        if shares_before * signed_qty > 0:
            # Add to the same direction: average entry cost across absolute size.
            total_cost = existing_position.avg_cost * abs(
                shares_before
            ) + fill_price * abs(signed_qty)
            return Position(
                ticker=ticker,
                shares=shares_after,
                avg_cost=total_cost / abs(shares_after),
                session_id=session_id,
            )

        if shares_before * shares_after > 0:
            return Position(
                ticker=ticker,
                shares=shares_after,
                avg_cost=existing_position.avg_cost,
                session_id=session_id,
            )

        return Position(
            ticker=ticker,
            shares=shares_after,
            avg_cost=fill_price,
            session_id=session_id,
        )
