from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pandas as pd

from agentgraph.orchestrator import IntelliFin_Assistant
from broker.config import BrokerConfig
from broker.engine import BarData, MockBrokerEngine
from broker.ledger import TradeLedger
from broker.models import AccountSnapshot
from broker.views import BacktestConfigView, BacktestResultView, to_backtest_result_view


BacktestScopedAgentFactory = Callable[[str, MockBrokerEngine], Any]


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    portfolio: pd.DataFrame
    metrics: dict[str, float | int]
    view: BacktestResultView = field(
        default_factory=lambda: BacktestResultView(
            config=BacktestConfigView(),
            summary=to_backtest_result_view(
                config=BacktestConfigView(),
                metrics={},
                portfolio=pd.DataFrame(),
            ).summary,
        )
    )


class BacktestRunner:
    """Minimal backtest entry point reserved for fuller Phase 4 expansion."""

    def __init__(
        self,
        config: BrokerConfig,
        *,
        broker: MockBrokerEngine | None = None,
        ledger: TradeLedger | None = None,
        agent: Any | None = None,
        scoped_agent_factory: BacktestScopedAgentFactory | None = None,
    ) -> None:
        if agent is not None and scoped_agent_factory is not None:
            msg = "agent and scoped_agent_factory cannot both be provided"
            raise ValueError(msg)
        self._config = config
        self.broker = broker or MockBrokerEngine(config)
        self.ledger = ledger or TradeLedger()
        if agent is not None:
            self.agent = agent
        elif scoped_agent_factory is not None:
            self.agent = None
        else:
            self.agent = IntelliFin_Assistant(broker=self.broker)
        self._scoped_agent_factory = scoped_agent_factory
        self.broker.register_on_fill(self.ledger.record_fill)

    def run(
        self,
        ticker: str,
        price_df: pd.DataFrame,
        start_date: str,
        end_date: str,
        *,
        strategy_id: str = "",
        account_id: str = "default",
    ) -> BacktestResult:
        date_filtered = price_df.loc[start_date:end_date].copy()
        session_id = f"backtest-{ticker.lower()}-{uuid4().hex[:8]}"

        for trading_date, row in date_filtered.iterrows():
            self.broker.on_bar({ticker: self._row_to_bar(row)})
            as_of = self._to_iso_date(trading_date)
            if self._scoped_agent_factory is not None:
                agent = self._scoped_agent_factory(as_of, self.broker)
            else:
                agent = self.agent
                if agent is None:
                    msg = "backtest agent is not configured"
                    raise RuntimeError(msg)
            current_position_pct = self._calculate_current_position_pct(
                ticker,
                account_id=account_id,
            )
            agent.run(
                ticker,
                date=as_of,
                as_of=as_of,
                current_position_pct=current_position_pct,
                execution_enabled=True,
                session_id=session_id,
                strategy_id=strategy_id,
                account_id=account_id,
            )
            trading_timestamp = self._require_timestamp(trading_date)
            self.ledger.record_daily_snapshot(
                date=trading_timestamp.strftime("%Y-%m-%d"),
                account=self._account_snapshot_for_date(
                    trading_timestamp,
                    session_id,
                    strategy_id=strategy_id,
                    account_id=account_id,
                ),
            )

        portfolio = self._build_portfolio_performance_view(
            date_filtered,
            session_id=session_id,
        )
        metrics = self.ledger.compute_metrics(session_id=session_id)
        return BacktestResult(
            trades=self.ledger.to_trades_dataframe(session_id=session_id),
            portfolio=portfolio,
            metrics=metrics,
            view=to_backtest_result_view(
                config=BacktestConfigView(
                    tickers=[ticker],
                    start_date=start_date,
                    end_date=end_date,
                    benchmark_symbol="SPY",
                    strategy_id=strategy_id,
                    account_id=account_id,
                ),
                metrics=metrics,
                portfolio=portfolio,
                trades=self.ledger.load_fill_records(session_id=session_id),
                benchmark_return=self._calculate_benchmark_return(portfolio),
            ),
        )

    def _row_to_bar(self, row: pd.Series) -> BarData:
        return BarData(
            open=self._get_row_value(row, "Open", "open"),
            high=self._get_row_value(row, "High", "high"),
            low=self._get_row_value(row, "Low", "low"),
            close=self._get_row_value(row, "Close", "close"),
        )

    def _get_row_value(self, row: pd.Series, *column_names: str) -> float:
        for column_name in column_names:
            if column_name in row:
                return float(row[column_name])
        msg = f"missing required price column; expected one of {column_names!r}"
        raise KeyError(msg)

    def _calculate_current_position_pct(
        self,
        ticker: str,
        account_id: str = "default",
    ) -> float:
        account = self.broker.get_account(account_id=account_id)
        position = self.broker.get_position(ticker, account_id=account_id)
        if position is None or account.equity == 0:
            return 0.0

        latest_price = self.broker.get_latest_price(ticker)
        if latest_price is None:
            return 0.0

        position_value = position.shares * latest_price
        return position_value / account.equity * 100.0

    def _to_iso_date(self, trading_date: Any) -> str:
        timestamp = self._require_timestamp(trading_date)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(UTC)
        else:
            timestamp = timestamp.tz_convert(UTC)
        return timestamp.isoformat().replace("+00:00", "Z")

    def _account_snapshot_for_date(
        self,
        trading_date: Any,
        session_id: str,
        *,
        strategy_id: str = "",
        account_id: str = "default",
    ) -> AccountSnapshot:
        snapshot = self.broker.get_account(account_id=account_id)
        snapshot.timestamp = cast(
            datetime,
            self._require_timestamp(self._to_iso_date(trading_date)).to_pydatetime(),
        )
        snapshot.strategy_id = strategy_id
        snapshot.account_id = account_id
        snapshot.session_id = session_id
        return snapshot

    def _require_timestamp(self, trading_date: Any) -> pd.Timestamp:
        timestamp = pd.Timestamp(trading_date)
        if timestamp is pd.NaT:
            msg = "invalid backtest trading timestamp"
            raise ValueError(msg)
        return cast(pd.Timestamp, timestamp)

    def _build_portfolio_performance_view(
        self,
        price_df: pd.DataFrame,
        *,
        session_id: str,
    ) -> pd.DataFrame:
        portfolio = self.ledger.to_portfolio_dataframe(session_id=session_id)
        if portfolio.empty:
            return portfolio

        close_by_date = {
            self._require_timestamp(trading_date).strftime(
                "%Y-%m-%d"
            ): self._get_row_value(row, "Close", "close")
            for trading_date, row in price_df.iterrows()
        }

        portfolio = portfolio.copy()
        close_values = [
            float(close_by_date[str(date_value)])
            for date_value in portfolio["date"].tolist()
        ]
        portfolio["close"] = pd.Series(close_values, index=portfolio.index, dtype=float)
        portfolio["strategy_equity"] = self._float_series(portfolio, "equity")
        benchmark_start_close = float(portfolio.iloc[0]["close"])
        benchmark_shares = (
            self._config.initial_cash / benchmark_start_close
            if benchmark_start_close != 0
            else 0.0
        )
        benchmark_equity = self._float_series(portfolio, "close") * benchmark_shares
        portfolio["benchmark_equity"] = benchmark_equity
        portfolio["strategy_drawdown"] = self._calculate_drawdown_series(
            self._float_series(portfolio, "strategy_equity")
        )
        portfolio["benchmark_drawdown"] = self._calculate_drawdown_series(
            self._float_series(portfolio, "benchmark_equity")
        )
        return portfolio

    def _calculate_drawdown_series(self, equity_series: pd.Series) -> pd.Series:
        running_max = equity_series.cummax()
        return 1 - equity_series / running_max

    def _float_series(self, dataframe: pd.DataFrame, column: str) -> pd.Series:
        return pd.Series(dataframe[column], index=dataframe.index, dtype=float)

    def _calculate_benchmark_return(self, portfolio: pd.DataFrame) -> float:
        if portfolio.empty or "benchmark_equity" not in portfolio:
            return 0.0
        benchmark_equity = self._float_series(portfolio, "benchmark_equity")
        start_equity = float(benchmark_equity.iloc[0])
        if start_equity == 0:
            return 0.0
        return float(benchmark_equity.iloc[-1]) / start_equity - 1
