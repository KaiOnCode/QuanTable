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


# Phase 1 keeps `session_id` on broker-facing models so later phases can join
# one run across storage, notifications, and audit logs.
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
        # Market orders are priced by the engine later. A limit order needs its
        # trigger price at model-validation time.
        if self.type is OrderType.LIMIT and self.limit_price is None:
            msg = "limit_price is required for limit orders"
            raise ValueError(msg)
        return self


class Fill(BaseModel):
    order_id: str
    fill_price: float
    fill_qty: float
    fee: float
    # `slippage` stores realized cash cost, not the configured rate.
    slippage: float
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""


class Position(BaseModel):
    ticker: str
    # Positive shares = long, negative shares = short. This matches the sign
    # convention in `test/trade.py` and keeps PnL math symmetric.
    shares: float
    # Average entry cost per share. Direction lives in `shares`, not here.
    avg_cost: float
    # `side` is derived for logs and UI. `shares` remains the source of truth.
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
    # `equity` means cash plus marked-to-market position value.
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
    # Keep PM context next to execution results so downstream code can consume
    # one object for notifications, state sync, or audit output.
    pm_action: str
    pm_report_summary: str
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""
