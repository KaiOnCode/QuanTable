from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    ticker: str
    side: OrderSide
    type: OrderType
    qty: float = Field(gt=0)
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.NEW
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    session_id: str = ""

    @model_validator(mode="after")
    def validate_limit_price(self) -> Order:
        if self.type is OrderType.LIMIT and self.limit_price is None:
            msg = "limit_price is required for limit orders"
            raise ValueError(msg)
        return self


class Fill(BaseModel):
    order_id: str
    fill_price: float
    fill_qty: float
    fee: float
    slippage: float
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""


class Position(BaseModel):
    ticker: str
    shares: float
    avg_cost: float
    side: str = "FLAT"
    unrealized_pnl: float = 0.0
    session_id: str = ""

    @model_validator(mode="after")
    def derive_side(self) -> Position:
        if self.shares > 0:
            self.side = "LONG"
        elif self.shares < 0:
            self.side = "SHORT"
        else:
            self.side = "FLAT"
        return self


class AccountSnapshot(BaseModel):
    cash: float
    equity: float
    positions: list[Position] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""


class ExecutionReport(BaseModel):
    order: Order
    fills: list[Fill] = Field(default_factory=list)
    position_before: Position | None = None
    position_after: Position | None = None
    account_after: AccountSnapshot
    pm_action: str
    pm_report_summary: str
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""
