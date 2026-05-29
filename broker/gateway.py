from __future__ import annotations

from typing import Protocol

from broker.events import BrokerEvent
from broker.models import AccountSnapshot, Fill, Order, OrderStatus, Position


class BrokerGateway(Protocol):
    """Stable broker interface that later phases can swap for real execution."""

    def get_latest_price(self, ticker: str) -> float | None: ...

    def get_account(self, account_id: str = "default") -> AccountSnapshot: ...

    def get_positions(self, account_id: str = "default") -> list[Position]: ...

    def get_position(
        self,
        ticker: str,
        account_id: str = "default",
    ) -> Position | None: ...

    def place_order(self, order: Order) -> Order: ...

    def cancel_order(
        self,
        order_id: str,
        account_id: str | None = "default",
    ) -> Order: ...

    def get_order(
        self,
        order_id: str,
        account_id: str | None = "default",
    ) -> Order | None: ...

    def get_orders(
        self,
        status: OrderStatus | None = None,
        account_id: str = "default",
    ) -> list[Order]: ...

    def get_fills(
        self,
        order_id: str | None = None,
        account_id: str | None = "default",
    ) -> list[Fill]: ...

    def publish_event(self, event: BrokerEvent) -> BrokerEvent: ...
