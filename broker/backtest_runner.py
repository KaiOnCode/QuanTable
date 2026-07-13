from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC
from typing import Hashable, Literal, Protocol
from uuid import uuid4

import pandas as pd

from broker.config import BrokerConfig
from broker.engine import BarData, MockBrokerEngine
from broker.ledger import TradeLedger
from broker.models import AccountSnapshot, Order, OrderSide, OrderType
from broker.views import (
    BacktestConfigView,
    BacktestDecisionView,
    BacktestProgressView,
    BacktestResultView,
    to_backtest_result_view,
)


class BacktestRunError(RuntimeError):
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
        self._config = config
        self.broker = broker if broker is not None else MockBrokerEngine(config)
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
    ) -> BacktestResult:
        target, benchmark = self._aligned_windows(
            price_df, benchmark_df, start_date, end_date
        )
        if observer is not None:
            observer.bind_input_snapshot(target, benchmark)
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
        for trading_date, row in target.iterrows():
            self.broker.on_bar({ticker: self._row_to_bar(row)})
            as_of = self._to_iso_date(trading_date)
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
                if self._decision_executor is not None:
                    closes = tuple(
                        self._row_value(item, "Close", "close")
                        for _, item in target.loc[:trading_date].iterrows()
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
                    self._place_target_order(
                        ticker=ticker,
                        target_position_pct=typed_decision.target_position_pct,
                        current_position_pct=current_position_pct,
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
                progress = progress.model_copy(
                    update={"decisions_completed": progress.decisions_completed + 1}
                )
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
            self.ledger.record_daily_snapshot(
                date=self._to_timestamp(trading_date).strftime("%Y-%m-%d"),
                account=self._account_snapshot_for_date(
                    trading_date,
                    session_id,
                    strategy_id,
                    account_id,
                ),
            )
        portfolio = self._build_portfolio_performance_view(
            target, benchmark, session_id
        )
        metrics = self.ledger.compute_metrics(session_id=session_id)
        return BacktestResult(
            trades=self.ledger.to_trades_dataframe(session_id=session_id),
            portfolio=portfolio,
            metrics=metrics,
            view=to_backtest_result_view(
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
            ),
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

    def _place_target_order(
        self,
        *,
        ticker: str,
        target_position_pct: float,
        current_position_pct: float,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> None:
        target = target_position_pct
        if target < 0 or target > self._config.max_position_pct * 100:
            raise BacktestRunError("typed decision violates long-only position limit")
        delta = target - current_position_pct
        if abs(delta) <= 1e-9:
            return
        account = self.broker.get_account(account_id=account_id)
        price = self.broker.get_latest_price(ticker)
        if price is None or price <= 0:
            raise BacktestRunError("typed decision requires a positive reference price")
        desired_shares = account.equity * target / 100 / price
        position = self.broker.get_position(ticker, account_id=account_id)
        current_shares = 0.0 if position is None else position.shares
        quantity = abs(desired_shares - current_shares)
        if quantity <= 1e-9:
            return
        self.broker.place_order(
            Order(
                ticker=ticker,
                side=OrderSide.BUY if delta > 0 else OrderSide.SELL,
                type=OrderType.MARKET,
                qty=quantity,
                strategy_id=strategy_id,
                account_id=account_id,
                session_id=session_id,
            )
        )

    def _agent_for(self, as_of: str) -> BacktestAgent:
        if self._scoped_agent_factory is not None:
            return self._scoped_agent_factory(as_of, self.broker)
        if self._agent is None:
            raise BacktestRunError("backtest agent is not configured")
        return self._agent

    def _aligned_windows(
        self,
        price_df: pd.DataFrame,
        benchmark_df: pd.DataFrame | None,
        start_date: str,
        end_date: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if benchmark_df is None:
            raise BacktestRunError("independent benchmark_df is required")
        if self._to_timestamp(start_date) > self._to_timestamp(end_date):
            raise BacktestRunError("start_date must not be after end_date")
        target = price_df.loc[start_date:end_date].copy()
        benchmark = benchmark_df.loc[start_date:end_date].copy()
        if target.empty or benchmark.empty:
            raise BacktestRunError(
                "target and benchmark require non-empty price windows"
            )
        common_dates = target.index.intersection(benchmark.index)
        if common_dates.empty:
            raise BacktestRunError("target and benchmark have no overlapping dates")
        return target.loc[common_dates], benchmark.loc[common_dates]

    def _decision_dates(
        self, index: pd.Index, frequency: str
    ) -> tuple[frozenset[pd.Timestamp], BacktestFrequency]:
        dates = pd.DatetimeIndex(index)
        match frequency:
            case "daily":
                selected = dates
                canonical_frequency: BacktestFrequency = "daily"
            case "weekly":
                selected = dates[~dates.to_period("W").duplicated()]
                canonical_frequency = "weekly"
            case "monthly":
                selected = dates[~dates.to_period("M").duplicated()]
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
        benchmark_close = {
            self._to_timestamp(trading_date).strftime("%Y-%m-%d"): self._row_value(
                row, "Close", "close"
            )
            for trading_date, row in benchmark.iterrows()
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
