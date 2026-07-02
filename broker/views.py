from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from broker.events import BrokerEvent, BrokerEventType
from broker.ledger import LedgerFillRecord
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

OrderStatusView = Literal["pending", "executed", "cancelled", "rejected"]
ExecutionStatusView = Literal[
    "pending",
    "skipped",
    "held",
    "executed",
    "rejected",
    "failed",
]
PriceSourceView = Literal["market", "last_close", "avg_cost_fallback"]


class FillView(BaseModel):
    order_id: str
    fill_price: float
    fill_qty: float
    fee: float
    slippage: float
    timestamp: datetime
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class OrderView(BaseModel):
    id: str
    ticker: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: float
    limit_price: float | None = None
    status: OrderStatusView
    filled_quantity: float
    filled_avg_price: float | None
    commission: float
    created_at: datetime
    updated_at: datetime
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""
    client_order_id: str = ""


class PositionView(BaseModel):
    ticker: str
    shares: float
    avg_cost: float
    side: Literal["long", "short", "flat"]
    current_price: float
    price_source: PriceSourceView
    market_value: float
    unrealized_pnl: float
    weight_pct: float
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class AccountView(BaseModel):
    cash: float
    equity: float
    positions: list[PositionView] = Field(default_factory=list)
    timestamp: datetime
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class TradeView(BaseModel):
    order_id: str
    timestamp: datetime
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    fee: float
    slippage: float
    trade_value: float
    realized_pnl: float
    cash_after: float
    equity_after: float
    shares_after: float
    avg_cost_after: float
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class ApprovalSnapshotView(BaseModel):
    approval_id: str = ""
    approval_status: str = ""
    approval_reason: str = ""
    reviewer: str = ""
    reviewer_notes: str = ""
    original_target_pct: float | None = None
    modified_target_pct: float | None = None


class ExecutionReportView(BaseModel):
    status: ExecutionStatusView
    order: OrderView | None = None
    fills: list[FillView] = Field(default_factory=list)
    position_before: PositionView | None = None
    position_after: PositionView | None = None
    account_after: AccountView | None = None
    approval: ApprovalSnapshotView | None = None
    reason: str = ""
    pm_action: str = ""
    pm_report_summary: str = ""
    timestamp: datetime | None = None
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class ExecutionOutcomeView(BaseModel):
    status: ExecutionStatusView
    order: OrderView | None = None
    trades: list[TradeView] = Field(default_factory=list)
    account_after: AccountView | None = None
    realized_pnl: float = 0.0
    reason: str = ""
    pm_action: str = ""
    approval_status: str = ""
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class BrokerEventView(BaseModel):
    event_id: str
    sequence: int
    event_type: BrokerEventType
    entity_type: str
    entity_id: str
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class PerformanceMetricsView(BaseModel):
    cumulative_return_pct: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    benchmark_return_pct: float = 0.0
    excess_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    payoff_ratio: float = 0.0
    number_of_trades: int = 0
    avg_holding_period_days: float = 0.0


class BacktestConfigView(BaseModel):
    tickers: list[str] = Field(default_factory=list)
    start_date: str = ""
    end_date: str = ""
    benchmark_symbol: str = "SPY"
    strategy_id: str = ""
    account_id: str = "default"


class BacktestSeriesPointView(BaseModel):
    date: str
    strategy_equity: float
    benchmark_equity: float
    strategy_drawdown_pct: float = 0.0
    benchmark_drawdown_pct: float = 0.0


class BacktestResultView(BaseModel):
    status: Literal["completed"] = "completed"
    config: BacktestConfigView
    summary: PerformanceMetricsView
    series: list[BacktestSeriesPointView] = Field(default_factory=list)
    trades: list[TradeView] = Field(default_factory=list)


def to_account_view(
    account: AccountSnapshot,
    *,
    market_prices: Mapping[str, float] | None = None,
    last_closes: Mapping[str, float] | None = None,
) -> AccountView:
    market_prices = market_prices or {}
    last_closes = last_closes or {}
    return AccountView(
        cash=account.cash,
        equity=account.equity,
        positions=[
            to_position_view(
                position,
                account_equity=account.equity,
                current_price=market_prices.get(position.ticker),
                last_close=last_closes.get(position.ticker),
            )
            for position in account.positions
        ],
        timestamp=account.timestamp,
        strategy_id=account.strategy_id,
        account_id=account.account_id,
        session_id=account.session_id,
        decision_id=account.decision_id,
    )


def to_position_view(
    position: Position,
    *,
    account_equity: float,
    current_price: float | None = None,
    last_close: float | None = None,
) -> PositionView:
    mark_price, price_source = _select_mark_price(
        position,
        current_price=current_price,
        last_close=last_close,
    )
    market_value = position.shares * mark_price
    weight_pct = market_value / account_equity * 100.0 if account_equity else 0.0
    return PositionView(
        ticker=position.ticker,
        shares=position.shares,
        avg_cost=position.avg_cost,
        side=_position_side_to_view(position.side),
        current_price=mark_price,
        price_source=price_source,
        market_value=market_value,
        unrealized_pnl=(mark_price - position.avg_cost) * position.shares,
        weight_pct=weight_pct,
        strategy_id=position.strategy_id,
        account_id=position.account_id,
        session_id=position.session_id,
        decision_id=position.decision_id,
    )


def to_order_view(order: Order, *, fills: Sequence[Fill]) -> OrderView:
    order_fills = [fill for fill in fills if fill.order_id == order.id]
    filled_quantity = sum(fill.fill_qty for fill in order_fills)
    filled_value = sum(fill.fill_qty * fill.fill_price for fill in order_fills)
    filled_avg_price = filled_value / filled_quantity if filled_quantity > 0 else None
    return OrderView(
        id=order.id,
        ticker=order.ticker,
        side=_order_side_to_view(order.side),
        order_type=_order_type_to_view(order.type),
        quantity=order.qty,
        limit_price=order.limit_price,
        status=_order_status_to_view(order.status),
        filled_quantity=filled_quantity,
        filled_avg_price=filled_avg_price,
        commission=sum(fill.fee for fill in order_fills),
        created_at=order.created_at,
        updated_at=order.updated_at,
        strategy_id=order.strategy_id,
        account_id=order.account_id,
        session_id=order.session_id,
        decision_id=order.decision_id,
        client_order_id=order.client_order_id,
    )


def to_fill_view(fill: Fill) -> FillView:
    return FillView(
        order_id=fill.order_id,
        fill_price=fill.fill_price,
        fill_qty=fill.fill_qty,
        fee=fill.fee,
        slippage=fill.slippage,
        timestamp=fill.timestamp,
        strategy_id=fill.strategy_id,
        account_id=fill.account_id,
        session_id=fill.session_id,
        decision_id=fill.decision_id,
    )


def to_trade_view(record: LedgerFillRecord) -> TradeView:
    return TradeView(
        order_id=record.fill.order_id,
        timestamp=record.fill.timestamp,
        ticker=record.ticker,
        side=_ledger_side_to_view(record.side),
        quantity=record.fill.fill_qty,
        price=record.fill.fill_price,
        fee=record.fill.fee,
        slippage=record.fill.slippage,
        trade_value=record.fill.fill_price * record.fill.fill_qty,
        realized_pnl=record.realized_pnl,
        cash_after=record.account_after.cash,
        equity_after=record.account_after.equity,
        shares_after=record.position_after.shares,
        avg_cost_after=record.position_after.avg_cost,
        strategy_id=record.strategy_id,
        account_id=record.account_id,
        session_id=record.session_id,
        decision_id=record.decision_id,
    )


def to_execution_report_view(
    report: ExecutionReport,
    *,
    status: ExecutionStatusView = "executed",
    approval: ApprovalSnapshotView | None = None,
    reason: str = "",
) -> ExecutionReportView:
    fills = [to_fill_view(fill) for fill in report.fills]
    account_after = to_account_view(report.account_after)
    return ExecutionReportView(
        status=status,
        order=to_order_view(report.order, fills=report.fills),
        fills=fills,
        position_before=(
            to_position_view(
                report.position_before,
                account_equity=report.account_after.equity,
            )
            if report.position_before is not None
            else None
        ),
        position_after=(
            to_position_view(
                report.position_after,
                account_equity=report.account_after.equity,
            )
            if report.position_after is not None
            else None
        ),
        account_after=account_after,
        approval=approval,
        reason=reason,
        pm_action=report.pm_action,
        pm_report_summary=report.pm_report_summary,
        timestamp=report.timestamp,
        strategy_id=report.strategy_id,
        account_id=report.account_id,
        session_id=report.session_id,
        decision_id=report.decision_id,
    )


def to_execution_status_report_view(
    *,
    status: ExecutionStatusView,
    reason: str = "",
    ticker: str = "",
    pm_action: str = "",
    pm_report_summary: str = "",
    approval: ApprovalSnapshotView | None = None,
    timestamp: datetime | None = None,
    strategy_id: str = "",
    account_id: str = "default",
    session_id: str = "",
    decision_id: str = "",
) -> ExecutionReportView:
    del ticker
    return ExecutionReportView(
        status=status,
        approval=approval,
        reason=reason,
        pm_action=pm_action,
        pm_report_summary=pm_report_summary,
        timestamp=timestamp,
        strategy_id=strategy_id,
        account_id=account_id,
        session_id=session_id,
        decision_id=decision_id,
    )


def to_execution_outcome_view(
    report: ExecutionReportView,
    *,
    trades: Sequence[LedgerFillRecord] | None = None,
) -> ExecutionOutcomeView:
    trade_views = [to_trade_view(record) for record in trades or []]
    return ExecutionOutcomeView(
        status=report.status,
        order=report.order,
        trades=trade_views,
        account_after=report.account_after,
        realized_pnl=sum(trade.realized_pnl for trade in trade_views),
        reason=report.reason,
        pm_action=report.pm_action,
        approval_status=(
            report.approval.approval_status if report.approval is not None else ""
        ),
        strategy_id=report.strategy_id,
        account_id=report.account_id,
        session_id=report.session_id,
        decision_id=report.decision_id,
    )


def to_broker_event_view(event: BrokerEvent) -> BrokerEventView:
    return BrokerEventView(
        event_id=event.event_id,
        sequence=event.sequence,
        event_type=event.event_type,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        strategy_id=event.strategy_id,
        account_id=event.account_id,
        session_id=event.session_id,
        decision_id=event.decision_id,
        payload=dict(event.payload),
        timestamp=event.timestamp,
    )


def to_performance_metrics_view(
    metrics: Mapping[str, float | int],
    *,
    benchmark_return: float = 0.0,
) -> PerformanceMetricsView:
    total_return = float(metrics.get("total_return", 0.0))
    return PerformanceMetricsView(
        cumulative_return_pct=total_return * 100.0,
        total_return_pct=total_return * 100.0,
        annualized_return_pct=float(metrics.get("annualized_return", 0.0)) * 100.0,
        benchmark_return_pct=benchmark_return * 100.0,
        excess_return_pct=(total_return - benchmark_return) * 100.0,
        max_drawdown_pct=float(metrics.get("max_drawdown", 0.0)) * 100.0,
        max_drawdown_duration=float(metrics.get("max_drawdown_duration", 0.0)),
        sharpe_ratio=float(metrics.get("sharpe_ratio", 0.0)),
        win_rate_pct=float(metrics.get("win_rate", 0.0)) * 100.0,
        profit_factor=float(metrics.get("profit_factor", 0.0)),
        avg_win=float(metrics.get("avg_win", 0.0)),
        avg_loss=float(metrics.get("avg_loss", 0.0)),
        payoff_ratio=float(metrics.get("payoff_ratio", 0.0)),
        number_of_trades=int(metrics.get("number_of_trades", 0)),
        avg_holding_period_days=float(metrics.get("avg_holding_period_days", 0.0)),
    )


def to_backtest_result_view(
    *,
    config: BacktestConfigView,
    metrics: Mapping[str, float | int],
    portfolio: pd.DataFrame,
    trades: Sequence[LedgerFillRecord] | None = None,
    benchmark_return: float = 0.0,
) -> BacktestResultView:
    return BacktestResultView(
        config=config,
        summary=to_performance_metrics_view(
            metrics,
            benchmark_return=benchmark_return,
        ),
        series=_portfolio_to_series(portfolio),
        trades=[to_trade_view(record) for record in trades or []],
    )


def _select_mark_price(
    position: Position,
    *,
    current_price: float | None,
    last_close: float | None,
) -> tuple[float, PriceSourceView]:
    if current_price is not None:
        return current_price, "market"
    if last_close is not None:
        return last_close, "last_close"
    return position.avg_cost, "avg_cost_fallback"


def _order_side_to_view(side: OrderSide) -> Literal["buy", "sell"]:
    return "buy" if side is OrderSide.BUY else "sell"


def _order_type_to_view(order_type: OrderType) -> Literal["market", "limit"]:
    return "market" if order_type is OrderType.MARKET else "limit"


def _order_status_to_view(status: OrderStatus) -> OrderStatusView:
    if status is OrderStatus.NEW:
        return "pending"
    if status is OrderStatus.FILLED:
        return "executed"
    if status is OrderStatus.CANCELED:
        return "cancelled"
    if status is OrderStatus.REJECTED:
        return "rejected"
    msg = f"unsupported order status for public view: {status.value}"
    raise ValueError(msg)


def _position_side_to_view(side: str) -> Literal["long", "short", "flat"]:
    normalized = side.upper()
    if normalized == "LONG":
        return "long"
    if normalized == "SHORT":
        return "short"
    return "flat"


def _ledger_side_to_view(side: str) -> Literal["buy", "sell"]:
    normalized = side.upper()
    if normalized == "BUY":
        return "buy"
    if normalized == "SELL":
        return "sell"
    msg = f"unknown ledger trade side: {side}"
    raise ValueError(msg)


def _portfolio_to_series(portfolio: pd.DataFrame) -> list[BacktestSeriesPointView]:
    if portfolio.empty:
        return []
    return [
        BacktestSeriesPointView(
            date=str(row["date"]),
            strategy_equity=float(row["strategy_equity"]),
            benchmark_equity=float(row["benchmark_equity"]),
            strategy_drawdown_pct=float(row.get("strategy_drawdown", 0.0)) * 100.0,
            benchmark_drawdown_pct=float(row.get("benchmark_drawdown", 0.0)) * 100.0,
        )
        for row in portfolio.to_dict(orient="records")
    ]
