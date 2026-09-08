from __future__ import annotations

from broker.config import BrokerConfig
from broker.models import AccountSnapshot, Order, OrderSide, OrderType


class PreTradeRiskChecker:
    def __init__(self, config: BrokerConfig):
        self._config = config

    def check(
        self,
        order: Order,
        account: AccountSnapshot,
        reference_price: float | None = None,
    ) -> tuple[bool, str]:
        if order.qty <= 0:
            return False, "order quantity must be positive"

        if order.type is OrderType.LIMIT and (
            order.limit_price is None or order.limit_price <= 0
        ):
            return False, "limit order requires a positive limit price"

        if order.side is OrderSide.SELL and not self._config.allow_short:
            existing_position = next(
                (
                    position
                    for position in account.positions
                    if position.ticker == order.ticker
                ),
                None,
            )
            available_shares = (
                existing_position.shares if existing_position is not None else 0.0
            )
            if order.qty > available_shares:
                return False, "short selling is disabled"

        if order.side is OrderSide.BUY and reference_price is not None:
            estimated_fill_price = reference_price
            if order.type is OrderType.MARKET:
                estimated_fill_price *= 1 + self._config.slippage_rate

            estimated_trade_value = estimated_fill_price * order.qty
            estimated_fee = estimated_trade_value * self._config.commission_rate
            if estimated_trade_value + estimated_fee > account.cash:
                return False, "insufficient cash"

        if reference_price is not None:
            signed_qty = order.qty if order.side is OrderSide.BUY else -order.qty
            current_position = next(
                (
                    position
                    for position in account.positions
                    if position.ticker == order.ticker
                ),
                None,
            )
            current_shares = (
                current_position.shares if current_position is not None else 0.0
            )
            projected_shares = current_shares + signed_qty

            estimated_fill_price = reference_price
            if order.type is OrderType.MARKET:
                if order.side is OrderSide.BUY:
                    estimated_fill_price *= 1 + self._config.slippage_rate
                else:
                    estimated_fill_price *= 1 - self._config.slippage_rate

            estimated_trade_value = abs(estimated_fill_price * order.qty)
            estimated_fee = estimated_trade_value * self._config.commission_rate
            estimated_slippage = abs(estimated_fill_price - reference_price) * order.qty
            projected_equity = account.equity - estimated_fee - estimated_slippage
            projected_position_value = abs(projected_shares) * reference_price

            if projected_equity > 0:
                projected_position_pct = projected_position_value / projected_equity
                if projected_position_pct > self._config.max_position_pct:
                    return False, "max position pct exceeded"

        return True, ""
