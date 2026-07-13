from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import math
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from broker.events import BrokerEvent, BrokerEventType
from broker.ledger import ClosedTradeRecord, LedgerFillRecord
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


class ClosedTradeView(BaseModel):
    entry_at: datetime
    exit_at: datetime
    ticker: str
    quantity: float
    entry_vwap: float
    exit_vwap: float
    average_cost_basis: float
    net_realized_pnl: float
    fees: float
    slippage: float
    holding_period_trading_days: int
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
    model_config = ConfigDict(allow_inf_nan=False)

    cumulative_return_pct: float | None = 0.0
    total_return_pct: float | None = 0.0
    annualized_return_pct: float | None = None
    annualized_volatility_pct: float | None = None
    benchmark_return_pct: float | None = None
    excess_return_pct: float | None = None
    max_drawdown_pct: float | None = 0.0
    max_drawdown_duration: int = 0
    sharpe_ratio: float | None = None
    win_rate_pct: float | None = 0.0
    profit_factor: float | None = None
    avg_win: float | None = 0.0
    avg_loss: float | None = 0.0
    payoff_ratio: float | None = None
    number_of_trades: int = 0
    number_of_fills: int = 0
    number_of_orders: int = 0
    number_of_rejections: int = 0
    number_of_closed_trades: int = 0
    avg_holding_period_days: float = 0.0
    realized_pnl_usd: float = 0.0
    unrealized_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0
    total_fees_usd: float = 0.0
    total_slippage_usd: float = 0.0
    turnover_pct: float = 0.0
    average_daily_gross_exposure_pct: float = 0.0


class BacktestConfigView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = ""
    start_date: str = ""
    end_date: str = ""
    frequency: Literal["daily", "weekly", "monthly"] = "daily"
    benchmark_symbol: str = "SPY"
    strategy_id: str = ""
    account_id: str = "default"
    mode: Literal["deterministic", "agent_experiment"] = "deterministic"
    agent_model: str | None = None
    strategy_snapshot_hash: str = ""
    policy_hash: str = ""
    data_snapshot_hash: str = ""
    engine_version: str = "backtest-engine/v1"
    strategy_execution_frequency: Literal["daily", "weekly", "monthly"] = "daily"
    run_frequency: Literal["daily", "weekly", "monthly"] = "daily"
    initial_capital: float = 100_000.0
    commission_rate: float = 0.001
    commission_bps: float = 10.0
    slippage_rate: float = 0.0005
    slippage_bps: float = 5.0
    execution_timing: Literal["next_open", "close_bar"] = "next_open"
    max_position_pct: float = 1.0
    allow_short: bool = False
    provider_adjustment_mode: str = "auto_adjusted_prices_v1"
    corporate_actions_mode: str = "provider_adjusted_prices"
    data_provider: str = "yfinance"
    data_provider_version: str = ""
    data_interval: Literal["1d"] = "1d"
    data_auto_adjust: bool = True
    data_actions: bool = False
    data_end_exclusive: str = ""
    data_lookback_days: int = 0
    data_provider_buffer_days: int = 100
    data_provider_end_semantics: Literal["exclusive"] = "exclusive"
    data_provider_timezone: str = "unknown"
    data_timezone_normalization: Literal["exchange_session_date_to_UTC_midnight"] = (
        "exchange_session_date_to_UTC_midnight"
    )
    warmup_bars: int = 0
    risk_free_rate: float = 0.0
    periods_per_year: int = Field(default=252, ge=1)
    max_drawdown_limit_pct: float = 0.0
    max_drawdown_limit_enforced: bool = False
    evaluation_bar_count: int = 0
    sample_first_date: str = ""
    sample_last_date: str = ""


class BacktestProgressView(BaseModel):
    bars_total: int = 0
    bars_processed: int = 0
    decisions_total: int = 0
    decisions_eligible: int = 0
    decisions_not_ready: int = 0
    decisions_completed: int = 0
    current_decision_date: str | None = None


class BacktestDecisionView(BaseModel):
    sequence: int
    signal_date: str
    execution_date: str | None = None
    status: Literal["not_ready", "completed", "failed", "unfilled_end_of_window"]
    attempts: int = 1
    target_position_pct: float | None = None
    confidence: float | None = None
    feature_hash: str | None = None
    policy_hash: str = ""
    error_code: str | None = None
    error_stage: str | None = None


class BacktestOrderEvidenceView(BaseModel):
    order_id: str
    status: Literal["pending", "executed", "cancelled", "rejected", "unfilled"]
    signal_date: str
    execution_date: str | None = None
    reason: str = ""


class BacktestEndPositionView(BaseModel):
    ticker: str = ""
    shares: float = 0.0
    market_value: float = 0.0
    average_cost_basis: float = 0.0
    unrealized_pnl: float = 0.0
    liquidated_at_end: bool = False


class BacktestProvenanceView(BaseModel):
    strategy_snapshot_hash: str = ""
    policy_hash: str = ""
    data_snapshot_hash: str = ""
    canonical_result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class BacktestSeriesPointView(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    date: str
    strategy_equity: float
    benchmark_equity: float | None = None
    strategy_drawdown_pct: float = 0.0
    benchmark_drawdown_pct: float | None = None


class BacktestNoTradeReasonView(BaseModel):
    code: Literal["no_signals", "not_ready", "all_hold", "all_rejected"]
    count: int = Field(ge=1)


class BacktestResultView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = "completed"
    outcome: Literal["completed", "completed_no_trades"] = "completed_no_trades"
    config: BacktestConfigView
    summary: PerformanceMetricsView
    series: list[BacktestSeriesPointView] = Field(default_factory=list)
    trades: list[TradeView] = Field(default_factory=list)
    executions: list[TradeView] = Field(default_factory=list)
    closed_trades: list[ClosedTradeView] = Field(default_factory=list)
    no_trade_reasons: list[BacktestNoTradeReasonView] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    progress: BacktestProgressView = Field(default_factory=BacktestProgressView)
    decisions: list[BacktestDecisionView] = Field(default_factory=list)
    decision_count: int = 0
    orders: list[BacktestOrderEvidenceView] = Field(default_factory=list)
    order_count: int = 0
    end_position: BacktestEndPositionView = Field(
        default_factory=BacktestEndPositionView
    )
    provenance: BacktestProvenanceView = Field(
        default_factory=lambda: BacktestProvenanceView(canonical_result_hash="0" * 64)
    )

    @model_validator(mode="after")
    def derive_counts_and_outcome(self) -> BacktestResultView:
        self.decision_count = len(self.decisions)
        self.order_count = len(self.orders)
        self.outcome = "completed" if self.closed_trades else "completed_no_trades"
        return self


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


def to_closed_trade_view(record: ClosedTradeRecord) -> ClosedTradeView:
    return ClosedTradeView(
        entry_at=record.entry_at,
        exit_at=record.exit_at,
        ticker=record.ticker,
        quantity=record.quantity,
        entry_vwap=record.entry_vwap,
        exit_vwap=record.exit_vwap,
        average_cost_basis=record.average_cost_basis,
        net_realized_pnl=record.net_realized_pnl,
        fees=record.fees,
        slippage=record.slippage,
        holding_period_trading_days=record.holding_period_trading_days,
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
    metrics: Mapping[str, float | int | None],
    *,
    benchmark_return: float | None = None,
) -> PerformanceMetricsView:
    total_return = _finite_or_none(metrics.get("total_return", 0.0))
    benchmark = _finite_or_none(benchmark_return)
    excess_return = (
        total_return - benchmark
        if total_return is not None and benchmark is not None
        else None
    )
    return PerformanceMetricsView(
        cumulative_return_pct=_percent_or_none(total_return),
        total_return_pct=_percent_or_none(total_return),
        annualized_return_pct=_percent_or_none(
            _finite_or_none(metrics.get("annualized_return"))
        ),
        annualized_volatility_pct=_percent_or_none(
            _finite_or_none(metrics.get("annualized_volatility"))
        ),
        benchmark_return_pct=_percent_or_none(benchmark),
        excess_return_pct=_percent_or_none(excess_return),
        max_drawdown_pct=_percent_or_none(
            _finite_or_none(metrics.get("max_drawdown", 0.0))
        ),
        max_drawdown_duration=_int_or_zero(metrics.get("max_drawdown_duration", 0)),
        sharpe_ratio=_finite_or_none(metrics.get("sharpe_ratio")),
        win_rate_pct=_percent_or_none(_finite_or_none(metrics.get("win_rate", 0.0))),
        profit_factor=_finite_or_none(metrics.get("profit_factor")),
        avg_win=_finite_or_none(metrics.get("avg_win", 0.0)),
        avg_loss=_finite_or_none(metrics.get("avg_loss", 0.0)),
        payoff_ratio=_finite_or_none(metrics.get("payoff_ratio")),
        number_of_trades=_int_or_zero(metrics.get("number_of_trades", 0)),
        number_of_fills=_int_or_zero(metrics.get("number_of_fills", 0)),
        number_of_orders=_int_or_zero(metrics.get("number_of_orders", 0)),
        number_of_rejections=_int_or_zero(metrics.get("number_of_rejections", 0)),
        number_of_closed_trades=_int_or_zero(metrics.get("number_of_closed_trades", 0)),
        avg_holding_period_days=_finite_or_zero(
            metrics.get("avg_holding_period_days", 0.0)
        ),
        realized_pnl_usd=_finite_or_zero(metrics.get("realized_pnl", 0.0)),
        unrealized_pnl_usd=_finite_or_zero(metrics.get("unrealized_pnl", 0.0)),
        net_pnl_usd=_finite_or_zero(metrics.get("net_pnl", 0.0)),
        total_fees_usd=_finite_or_zero(
            metrics.get("total_fees", metrics.get("fees", 0.0))
        ),
        total_slippage_usd=_finite_or_zero(
            metrics.get("total_slippage", metrics.get("slippage", 0.0))
        ),
        turnover_pct=_finite_or_zero(metrics.get("turnover", 0.0)) * 100.0,
        average_daily_gross_exposure_pct=(
            _finite_or_zero(metrics.get("average_daily_gross_exposure", 0.0)) * 100.0
        ),
    )


def to_backtest_result_view(
    *,
    config: BacktestConfigView,
    metrics: Mapping[str, float | int | None],
    portfolio: pd.DataFrame,
    trades: Sequence[LedgerFillRecord] | None = None,
    executions: Sequence[LedgerFillRecord] | None = None,
    closed_trades: Sequence[ClosedTradeRecord] | None = None,
    benchmark_return: float | None = None,
    warnings: Sequence[str] | None = None,
    progress: BacktestProgressView | None = None,
    decisions: Sequence[BacktestDecisionView] | None = None,
    no_trade_reasons: Sequence[BacktestNoTradeReasonView] | None = None,
) -> BacktestResultView:
    legacy_records = trades if trades is not None else executions
    execution_records = executions if executions is not None else legacy_records
    return BacktestResultView(
        config=config,
        summary=to_performance_metrics_view(
            metrics,
            benchmark_return=benchmark_return,
        ),
        series=_portfolio_to_series(portfolio),
        trades=[to_trade_view(record) for record in legacy_records or []],
        executions=[to_trade_view(record) for record in execution_records or []],
        closed_trades=[to_closed_trade_view(record) for record in closed_trades or []],
        warnings=list(warnings or []),
        progress=progress or BacktestProgressView(),
        decisions=list(decisions or []),
        no_trade_reasons=list(no_trade_reasons or []),
    )


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    return candidate if math.isfinite(candidate) else None


def _finite_or_zero(value: Any) -> float:
    return _finite_or_none(value) or 0.0


def _percent_or_none(value: float | None) -> float | None:
    return value * 100.0 if value is not None else None


def _int_or_zero(value: int | float | None) -> int:
    return int(value) if value is not None else 0


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
            benchmark_equity=_finite_or_none(row.get("benchmark_equity")),
            strategy_drawdown_pct=float(row.get("strategy_drawdown", 0.0)) * 100.0,
            benchmark_drawdown_pct=_percent_or_none(
                _finite_or_none(row.get("benchmark_drawdown"))
            ),
        )
        for row in portfolio.to_dict(orient="records")
    ]
