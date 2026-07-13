from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
import math
from typing import Hashable, Literal, Protocol
from uuid import uuid4

import pandas as pd

from broker.config import BrokerConfig
from broker.engine import BarData, MockBrokerEngine
from broker.ledger import TradeLedger
from broker.models import AccountSnapshot, Order, OrderSide, OrderStatus, OrderType
from broker.views import (
    BacktestConfigView,
    BacktestDecisionView,
    BacktestEndPositionView,
    BacktestOrderEvidenceView,
    BacktestProgressView,
    BacktestResultView,
    to_backtest_result_view,
)


class BacktestRunError(RuntimeError):
    pass


class BacktestInsufficientHistoryError(BacktestRunError):
    pass


class BacktestAgent(Protocol):
    def run(
        self,
        ticker: str,
        *,
        date: str,
        as_of: str,
        current_position_pct: float,
        execution_enabled: bool,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> dict: ...


@dataclass(frozen=True, slots=True)
class BacktestTargetDecision:
    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float
    confidence: float
    rationale: str
    feature_hash: str
    attempts: int


class BacktestDecisionExecutor(Protocol):
    @property
    def minimum_close_count(self) -> int: ...

    def decide(
        self,
        ticker: str,
        *,
        as_of: str,
        closes: tuple[float, ...],
        current_position_pct: float,
    ) -> BacktestTargetDecision: ...


class BacktestRunObserver(Protocol):
    def bind_input_snapshot(
        self, target: pd.DataFrame, benchmark: pd.DataFrame
    ) -> None: ...

    def record_progress(self, progress: BacktestProgressView) -> None: ...

    def begin_decision(
        self, sequence: int, decision_date: str, policy_hash: str
    ) -> None: ...

    def record_decision(self, decision: BacktestDecisionView) -> None: ...

    def record_execution(self, sequence: int, execution_date: str) -> None: ...


BacktestScopedAgentFactory = Callable[[str, MockBrokerEngine], BacktestAgent]
type BacktestFrequency = Literal["daily", "weekly", "monthly"]


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    portfolio: pd.DataFrame
    metrics: dict[str, float | int]
    view: BacktestResultView = field(
        default_factory=lambda: BacktestResultView(
            config=BacktestConfigView(),
            summary=to_backtest_result_view(
                config=BacktestConfigView(), metrics={}, portfolio=pd.DataFrame()
            ).summary,
        )
    )


@dataclass(frozen=True, slots=True)
class _PendingTargetIntent:
    sequence: int
    signal_time: datetime
    target_position_pct: float
    strategy_id: str
    account_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class _PendingTargetPlacement:
    sequence: int
    evidence: BacktestOrderEvidenceView | None = None


class BacktestRunner:
    def __init__(
        self,
        config: BrokerConfig,
        *,
        broker: MockBrokerEngine | None = None,
        ledger: TradeLedger | None = None,
        agent: BacktestAgent | None = None,
        scoped_agent_factory: BacktestScopedAgentFactory | None = None,
        decision_executor: BacktestDecisionExecutor | None = None,
    ) -> None:
        configured = sum(
            item is not None
            for item in (agent, scoped_agent_factory, decision_executor)
        )
        if configured != 1:
            raise BacktestRunError("provide exactly one decision implementation")
        self._config = config.model_copy(update={"execution_timing": "next_open"})
        if broker is not None and broker.execution_timing != "next_open":
            raise BacktestRunError("backtest broker requires next_open execution")
        self.broker = broker if broker is not None else MockBrokerEngine(self._config)
        self.ledger = ledger if ledger is not None else TradeLedger()
        self._agent = agent
        self._scoped_agent_factory = scoped_agent_factory
        self._decision_executor = decision_executor
        self.broker.register_on_fill(self.ledger.record_fill)

    def run(
        self,
        ticker: str,
        price_df: pd.DataFrame,
        start_date: str,
        end_date: str,
        *,
        benchmark_df: pd.DataFrame | None = None,
        benchmark_symbol: str = "SPY",
        frequency: str = "daily",
        strategy_id: str = "",
        account_id: str = "default",
        policy_hash: str = "",
        observer: BacktestRunObserver | None = None,
        history_df: pd.DataFrame | None = None,
        snapshot_benchmark_df: pd.DataFrame | None = None,
    ) -> BacktestResult:
        target, benchmark = self._aligned_windows(
            price_df, benchmark_df, start_date, end_date
        )
        history = history_df.loc[:end_date].copy() if history_df is not None else target
        snapshot_benchmark = (
            snapshot_benchmark_df.loc[:end_date].copy()
            if snapshot_benchmark_df is not None
            else benchmark
        )
        if observer is not None:
            observer.bind_input_snapshot(history, snapshot_benchmark)
        session_id = f"backtest-{ticker.lower()}-{uuid4().hex[:8]}"
        decision_dates, canonical_frequency = self._decision_dates(
            target.index, frequency
        )
        progress = BacktestProgressView(
            bars_total=len(target), decisions_total=len(decision_dates)
        )
        if observer is not None:
            observer.record_progress(progress)
        decision_sequence = 0
        pending_intent: _PendingTargetIntent | None = None
        target_intent_evidence: list[BacktestOrderEvidenceView] = []
        pending_agent_order_sequences: dict[str, int] = {}
        execution_recorded_sequences: set[int] = set()
        for trading_date, row in target.iterrows():
            execution_time = self._historical_timestamp(trading_date)
            placement = self._place_pending_target_order(
                ticker=ticker,
                row=row,
                pending=pending_intent,
                execution_time=execution_time,
            )
            pending_intent = None
            if placement is not None and placement.evidence is not None:
                target_intent_evidence.append(placement.evidence)
            self.broker.on_bar(
                {ticker: self._row_to_bar(row)},
                timestamp=execution_time,
            )
            as_of = self._to_iso_date(trading_date)
            executed_sequences: set[int] = set()
            if placement is not None:
                executed_sequences.add(placement.sequence)
            for order_id, sequence in tuple(pending_agent_order_sequences.items()):
                order = self.broker.get_order(order_id, account_id=account_id)
                if order is not None and order.status is not OrderStatus.NEW:
                    executed_sequences.add(sequence)
                    del pending_agent_order_sequences[order_id]
            newly_executed_sequences = executed_sequences - execution_recorded_sequences
            execution_recorded_sequences.update(newly_executed_sequences)
            if observer is not None:
                for sequence in sorted(newly_executed_sequences):
                    observer.record_execution(sequence, as_of)
            progress = progress.model_copy(
                update={"bars_processed": progress.bars_processed + 1}
            )
            if observer is not None:
                observer.record_progress(progress)
            if trading_date in decision_dates:
                decision_sequence += 1
                progress = progress.model_copy(
                    update={
                        "decisions_eligible": progress.decisions_eligible + 1,
                        "current_decision_date": as_of,
                    }
                )
                if observer is not None:
                    observer.record_progress(progress)
                    observer.begin_decision(decision_sequence, as_of, policy_hash)
                current_position_pct = self._calculate_current_position_pct(
                    ticker, account_id
                )
                agent_executed_at_signal_sequences: set[int] = set()
                if self._decision_executor is not None:
                    closes = tuple(
                        self._row_value(item, "Close", "close")
                        for _, item in history.loc[:trading_date].iterrows()
                    )
                    if len(closes) < self._decision_executor.minimum_close_count:
                        progress = progress.model_copy(
                            update={
                                "decisions_not_ready": (
                                    progress.decisions_not_ready + 1
                                )
                            }
                        )
                        if observer is not None:
                            observer.record_decision(
                                BacktestDecisionView(
                                    sequence=decision_sequence,
                                    signal_date=as_of,
                                    status="not_ready",
                                    policy_hash=policy_hash,
                                )
                            )
                            observer.record_progress(progress)
                        self.ledger.record_daily_snapshot(
                            date=self._to_timestamp(trading_date).strftime("%Y-%m-%d"),
                            account=self._account_snapshot_for_date(
                                trading_date,
                                session_id,
                                strategy_id,
                                account_id,
                            ),
                        )
                        continue
                    typed_decision = self._decision_executor.decide(
                        ticker,
                        as_of=as_of,
                        closes=closes,
                        current_position_pct=current_position_pct,
                    )
                    pending_intent = self._target_intent(
                        sequence=decision_sequence,
                        signal_time=execution_time,
                        target_position_pct=typed_decision.target_position_pct,
                        strategy_id=strategy_id,
                        account_id=account_id,
                        session_id=session_id,
                    )
                    decision: dict[str, object] = {
                        "target_position_pct": typed_decision.target_position_pct,
                        "confidence": typed_decision.confidence,
                        "attempts": typed_decision.attempts,
                        "feature_hash": typed_decision.feature_hash,
                    }
                else:
                    agent = self._agent_for(as_of)
                    prior_order_ids = {
                        order.id
                        for order in self.broker.get_orders(account_id=account_id)
                        if order.session_id == session_id
                    }
                    with self.broker.historical_order_submission(
                        session_id=session_id,
                        timestamp=execution_time,
                        decision_id=str(decision_sequence),
                    ):
                        decision = agent.run(
                            ticker,
                            date=as_of,
                            as_of=as_of,
                            current_position_pct=current_position_pct,
                            execution_enabled=True,
                            strategy_id=strategy_id,
                            account_id=account_id,
                            session_id=session_id,
                        )
                    new_order_ids = {
                        order.id
                        for order in self.broker.get_orders(account_id=account_id)
                        if order.session_id == session_id
                    } - prior_order_ids
                    self.broker.stamp_pending_orders(
                        session_id=session_id,
                        timestamp=execution_time,
                        decision_id=str(decision_sequence),
                        order_ids=new_order_ids,
                    )
                    for order_id in new_order_ids:
                        order = self.broker.get_order(order_id, account_id=account_id)
                        if order is not None and order.status is OrderStatus.NEW:
                            pending_agent_order_sequences[order_id] = decision_sequence
                        else:
                            agent_executed_at_signal_sequences.add(decision_sequence)
                    for order_id, sequence in tuple(
                        pending_agent_order_sequences.items()
                    ):
                        order = self.broker.get_order(order_id, account_id=account_id)
                        if order is not None and order.status is not OrderStatus.NEW:
                            agent_executed_at_signal_sequences.add(sequence)
                            del pending_agent_order_sequences[order_id]
                progress = progress.model_copy(
                    update={"decisions_completed": progress.decisions_completed + 1}
                )
                newly_agent_executed_sequences = (
                    agent_executed_at_signal_sequences - execution_recorded_sequences
                )
                execution_recorded_sequences.update(newly_agent_executed_sequences)
                if observer is not None:
                    observer.record_decision(
                        BacktestDecisionView(
                            sequence=decision_sequence,
                            signal_date=as_of,
                            execution_date=None,
                            status="completed",
                            target_position_pct=self._decision_float(
                                decision, "target_position_pct"
                            ),
                            confidence=self._decision_float(decision, "confidence"),
                            attempts=self._decision_int(decision, "attempts") or 1,
                            feature_hash=self._decision_str(decision, "feature_hash"),
                            policy_hash=policy_hash,
                        )
                    )
                    observer.record_progress(progress)
                    for sequence in sorted(newly_agent_executed_sequences):
                        observer.record_execution(sequence, as_of)
            self.ledger.record_daily_snapshot(
                date=self._to_timestamp(trading_date).strftime("%Y-%m-%d"),
                account=self._account_snapshot_for_date(
                    trading_date,
                    session_id,
                    strategy_id,
                    account_id,
                ),
            )
        if (
            decision_sequence > 0
            and progress.decisions_completed == 0
            and progress.decisions_not_ready == progress.decisions_eligible
        ):
            raise BacktestInsufficientHistoryError(
                "no evaluation decision has sufficient policy history"
            )
        portfolio = self._build_portfolio_performance_view(
            target, benchmark, session_id
        )
        metrics = self.ledger.compute_metrics(session_id=session_id)
        result_view = to_backtest_result_view(
            config=BacktestConfigView(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                benchmark_symbol=benchmark_symbol,
                frequency=canonical_frequency,
                strategy_id=strategy_id,
                account_id=account_id,
            ),
            metrics=metrics,
            portfolio=portfolio,
            trades=self.ledger.load_fill_records(session_id=session_id),
            benchmark_return=self._calculate_benchmark_return(portfolio),
        )
        order_evidence = [
            *self._order_evidence(account_id, session_id),
            *target_intent_evidence,
        ]
        result_view = result_view.model_copy(
            update={
                "orders": order_evidence,
                "order_count": len(order_evidence),
                "end_position": self._end_position(ticker, account_id),
            }
        )
        return BacktestResult(
            trades=self.ledger.to_trades_dataframe(session_id=session_id),
            portfolio=portfolio,
            metrics=metrics,
            view=result_view,
        )

    @staticmethod
    def _decision_float(decision: dict, key: str) -> float | None:
        value = decision.get(key)
        if isinstance(value, int | float):
            return float(value)
        return None

    @staticmethod
    def _decision_int(decision: dict, key: str) -> int | None:
        value = decision.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @staticmethod
    def _decision_str(decision: dict, key: str) -> str | None:
        value = decision.get(key)
        return value if isinstance(value, str) else None

    def _target_intent(
        self,
        *,
        sequence: int,
        signal_time: datetime,
        target_position_pct: float,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> _PendingTargetIntent:
        target = target_position_pct
        if target < 0 or target > self._config.max_position_pct * 100:
            raise BacktestRunError("typed decision violates long-only position limit")
        return _PendingTargetIntent(
            sequence=sequence,
            signal_time=signal_time,
            target_position_pct=target,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
        )

    def _place_pending_target_order(
        self,
        *,
        ticker: str,
        row: pd.Series,
        pending: _PendingTargetIntent | None,
        execution_time: datetime,
    ) -> _PendingTargetPlacement | None:
        if pending is None:
            return None
        open_price = self._row_value(row, "Open", "open")
        position = self.broker.get_position(ticker, account_id=pending.account_id)
        current_shares = 0 if position is None else math.floor(position.shares)
        account = self.broker.get_account(account_id=pending.account_id)
        prefill_equity = account.cash + current_shares * open_price
        target_fraction = pending.target_position_pct / 100
        slipped_price = open_price * (1 + self._config.slippage_rate)
        buy_cost_per_share = (
            open_price * self._config.slippage_rate
            + slipped_price * self._config.commission_rate
        )
        sell_price = open_price * (1 - self._config.slippage_rate)
        sell_cost_per_share = (
            open_price * self._config.slippage_rate
            + sell_price * self._config.commission_rate
        )
        uncosted_target_shares = math.floor(
            prefill_equity * target_fraction / open_price
        )
        if uncosted_target_shares >= current_shares:
            desired_shares = math.floor(
                target_fraction
                * (prefill_equity + current_shares * buy_cost_per_share)
                / (open_price + target_fraction * buy_cost_per_share)
            )
        else:
            desired_shares = math.floor(
                target_fraction
                * (prefill_equity - current_shares * sell_cost_per_share)
                / (open_price - target_fraction * sell_cost_per_share)
            )
        desired_shares = max(desired_shares, 0)
        if desired_shares > current_shares:
            affordable = math.floor(
                account.cash / (slipped_price * (1 + self._config.commission_rate))
            )
            desired_shares = min(desired_shares, current_shares + affordable)
        delta = desired_shares - current_shares
        if delta == 0:
            actual_position_fraction = (
                current_shares * open_price / prefill_equity
                if prefill_equity > 0
                else 0.0
            )
            if not math.isclose(
                actual_position_fraction,
                target_fraction,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                return _PendingTargetPlacement(
                    sequence=pending.sequence,
                    evidence=BacktestOrderEvidenceView(
                        order_id=f"target-intent-{pending.sequence}",
                        status="unfilled",
                        signal_date=pending.signal_time.isoformat(),
                        execution_date=execution_time.isoformat(),
                        reason="target_not_affordable",
                    ),
                )
            return None
        self.broker.place_order(
            Order(
                ticker=ticker,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                type=OrderType.MARKET,
                qty=abs(delta),
                created_at=pending.signal_time,
                updated_at=pending.signal_time,
                strategy_id=pending.strategy_id,
                account_id=pending.account_id,
                session_id=pending.session_id,
                decision_id=str(pending.sequence),
            )
        )
        return _PendingTargetPlacement(sequence=pending.sequence)

    def _agent_for(self, as_of: str) -> BacktestAgent:
        if self._scoped_agent_factory is not None:
            return self._scoped_agent_factory(as_of, self.broker)
        if self._agent is None:
            raise BacktestRunError("backtest agent is not configured")
        return self._agent

    def _order_evidence(
        self, account_id: str, session_id: str
    ) -> list[BacktestOrderEvidenceView]:
        evidence: list[BacktestOrderEvidenceView] = []
        for order in self.broker.get_orders(account_id=account_id):
            if order.session_id != session_id:
                continue
            if order.status is OrderStatus.FILLED:
                status = "executed"
            elif order.status is OrderStatus.REJECTED:
                status = "rejected"
            elif order.status is OrderStatus.CANCELED:
                status = "cancelled"
            else:
                status = "unfilled"
            execution_date = (
                order.updated_at.isoformat()
                if order.status is not OrderStatus.NEW
                else None
            )
            evidence.append(
                BacktestOrderEvidenceView(
                    order_id=order.id,
                    status=status,
                    signal_date=order.created_at.isoformat(),
                    execution_date=execution_date,
                    reason=("risk_check_failed" if status == "rejected" else ""),
                )
            )
        return evidence

    def _end_position(self, ticker: str, account_id: str) -> BacktestEndPositionView:
        position = self.broker.get_position(ticker, account_id=account_id)
        price = self.broker.get_latest_price(ticker)
        if position is None or price is None:
            return BacktestEndPositionView(ticker=ticker)
        return BacktestEndPositionView(
            ticker=ticker,
            shares=position.shares,
            market_value=position.shares * price,
            unrealized_pnl=position.unrealized_pnl,
            liquidated_at_end=False,
        )

    def _aligned_windows(
        self,
        price_df: pd.DataFrame,
        benchmark_df: pd.DataFrame | None,
        start_date: str,
        end_date: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if benchmark_df is None:
            raise BacktestRunError("independent benchmark_df is required")
        self._validate_price_frame(price_df, "target")
        self._validate_price_frame(benchmark_df, "benchmark")
        if self._to_timestamp(start_date) > self._to_timestamp(end_date):
            raise BacktestRunError("start_date must not be after end_date")
        target = price_df.loc[start_date:end_date].copy()
        benchmark = benchmark_df.loc[start_date:end_date].copy()
        if target.empty or benchmark.empty:
            raise BacktestRunError(
                "target and benchmark require non-empty price windows"
            )
        if target.index.intersection(benchmark.index).empty:
            raise BacktestRunError("target and benchmark have no overlapping dates")
        return target, benchmark

    def _validate_price_frame(self, frame: pd.DataFrame, label: str) -> None:
        if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
            raise BacktestRunError(f"{label} dates must be unique and monotonic")
        required = ("Open", "High", "Low", "Close")
        if any(column not in frame.columns for column in required):
            raise BacktestRunError(f"{label} requires OHLC columns")
        for _, row in frame.iterrows():
            try:
                open_price = self._row_value(row, "Open", "open")
                high = self._row_value(row, "High", "high")
                low = self._row_value(row, "Low", "low")
                close = self._row_value(row, "Close", "close")
            except (TypeError, ValueError) as error:
                raise BacktestRunError(f"{label} requires finite OHLCV") from error
            values = (open_price, high, low, close)
            try:
                finite = all(math.isfinite(value) for value in values)
            except TypeError as error:
                raise BacktestRunError(f"{label} requires finite OHLCV") from error
            if not finite:
                raise BacktestRunError(f"{label} requires finite OHLCV")
            if (
                min(values) <= 0
                or high < max(open_price, close, low)
                or low > min(open_price, close, high)
            ):
                raise BacktestRunError(f"{label} requires valid OHLC")
            if "Volume" in row:
                try:
                    volume = float(row["Volume"])
                except (TypeError, ValueError) as error:
                    raise BacktestRunError(f"{label} requires finite OHLCV") from error
                if not math.isfinite(volume):
                    raise BacktestRunError(f"{label} requires finite OHLCV")
                if volume < 0:
                    raise BacktestRunError(f"{label} volume must not be negative")

    def _decision_dates(
        self, index: pd.Index, frequency: str
    ) -> tuple[frozenset[pd.Timestamp], BacktestFrequency]:
        dates = pd.DatetimeIndex(index)
        period_dates = dates.tz_localize(None) if dates.tz is not None else dates
        match frequency:
            case "daily":
                selected = dates[:-1]
                canonical_frequency: BacktestFrequency = "daily"
            case "weekly":
                executable = dates[:-1]
                periods = period_dates.to_period("W")
                selected = executable[periods[:-1] != periods[1:]]
                canonical_frequency = "weekly"
            case "monthly":
                executable = dates[:-1]
                periods = period_dates.to_period("M")
                selected = executable[periods[:-1] != periods[1:]]
                canonical_frequency = "monthly"
            case _:
                raise BacktestRunError("frequency must be daily, weekly, or monthly")
        return (
            frozenset(self._to_timestamp(value) for value in selected),
            canonical_frequency,
        )

    def _row_to_bar(self, row: pd.Series) -> BarData:
        return {
            "open": self._row_value(row, "Open", "open"),
            "high": self._row_value(row, "High", "high"),
            "low": self._row_value(row, "Low", "low"),
            "close": self._row_value(row, "Close", "close"),
        }

    @staticmethod
    def _row_value(row: pd.Series, primary: str, fallback: str) -> float:
        try:
            return float(row[primary])
        except KeyError:
            return float(row[fallback])

    def _calculate_current_position_pct(self, ticker: str, account_id: str) -> float:
        account = self.broker.get_account(account_id=account_id)
        position = self.broker.get_position(ticker, account_id=account_id)
        latest_price = self.broker.get_latest_price(ticker)
        if position is None or latest_price is None or account.equity == 0:
            return 0.0
        return position.shares * latest_price / account.equity * 100.0

    @staticmethod
    def _to_timestamp(value: Hashable) -> pd.Timestamp:
        timestamp = pd.Timestamp(str(value))
        if not isinstance(timestamp, pd.Timestamp):
            raise BacktestRunError("invalid backtest trading timestamp")
        return timestamp

    def _to_iso_date(self, trading_date: Hashable) -> str:
        timestamp = self._to_timestamp(trading_date)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(UTC)
        else:
            timestamp = timestamp.tz_convert(UTC)
        return timestamp.isoformat().replace("+00:00", "Z")

    def _historical_timestamp(self, trading_date: Hashable) -> datetime:
        timestamp = self._to_timestamp(trading_date)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(UTC)
        else:
            timestamp = timestamp.tz_convert(UTC)
        return timestamp.to_pydatetime()

    def _account_snapshot_for_date(
        self,
        trading_date: Hashable,
        session_id: str,
        strategy_id: str,
        account_id: str,
    ) -> AccountSnapshot:
        snapshot = self.broker.get_account(account_id=account_id)
        timestamp = self._to_timestamp(trading_date).to_pydatetime()
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return snapshot.model_copy(
            update={
                "timestamp": timestamp,
                "strategy_id": strategy_id,
                "account_id": account_id,
                "session_id": session_id,
            }
        )

    def _build_portfolio_performance_view(
        self,
        target: pd.DataFrame,
        benchmark: pd.DataFrame,
        session_id: str,
    ) -> pd.DataFrame:
        portfolio = self.ledger.to_portfolio_dataframe(session_id=session_id)
        if portfolio.empty:
            return portfolio
        target_close = {
            self._to_timestamp(trading_date).strftime("%Y-%m-%d"): self._row_value(
                row, "Close", "close"
            )
            for trading_date, row in target.iterrows()
        }
        benchmark_series = pd.Series(
            [self._row_value(row, "Close", "close") for _, row in benchmark.iterrows()],
            index=pd.DatetimeIndex(benchmark.index),
            dtype=float,
        )
        target_dates = pd.DatetimeIndex(target.index)
        aligned_benchmark = benchmark_series.reindex(target_dates).ffill(limit=5)
        benchmark_close = {
            self._to_timestamp(trading_date).strftime("%Y-%m-%d"): float(value)
            for trading_date, value in aligned_benchmark.items()
        }
        dated = portfolio.copy()
        dated["close"] = [target_close[str(value)] for value in dated["date"].tolist()]
        benchmark_values = [
            benchmark_close[str(value)] for value in dated["date"].tolist()
        ]
        strategy_equity = pd.Series(
            dated["equity"].to_numpy(), index=dated.index, dtype=float
        )
        dated["strategy_equity"] = strategy_equity
        first_benchmark_close = benchmark_values[0]
        benchmark_shares = self._config.initial_cash / first_benchmark_close
        dated["benchmark_equity"] = pd.Series(
            [value * benchmark_shares for value in benchmark_values],
            index=dated.index,
            dtype=float,
        )
        benchmark_equity = pd.Series(
            dated["benchmark_equity"].to_numpy(), index=dated.index, dtype=float
        )
        dated["strategy_drawdown"] = self._drawdown(strategy_equity)
        dated["benchmark_drawdown"] = self._drawdown(benchmark_equity)
        return dated

    @staticmethod
    def _drawdown(equity: pd.Series) -> pd.Series:
        return 1 - equity / equity.cummax()

    @staticmethod
    def _calculate_benchmark_return(portfolio: pd.DataFrame) -> float:
        if portfolio.empty:
            return 0.0
        benchmark_equity = pd.Series(portfolio["benchmark_equity"], dtype=float)
        start_equity = float(benchmark_equity.iloc[0])
        if start_equity == 0:
            return 0.0
        return float(benchmark_equity.iloc[-1]) / start_equity - 1.0
