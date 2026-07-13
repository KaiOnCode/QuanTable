from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd
from pydantic import BaseModel

from broker.models import AccountSnapshot, Fill, Position


class LedgerFillRecord(BaseModel):
    """A persisted trade row plus the broker state immediately after the fill."""

    fill: Fill
    ticker: str
    side: str
    realized_pnl: float
    position_after: Position
    account_after: AccountSnapshot
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class LedgerSnapshotRecord(BaseModel):
    """A persisted end-of-day account snapshot keyed by trading date."""

    date: str
    account: AccountSnapshot
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""


class LedgerInitialCapitalRecord(BaseModel):
    initial_capital: float
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""


class ClosedTradeRecord(BaseModel):
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


type _EpisodeKey = tuple[str, str, str, str]


@dataclass(slots=True)
class _LongOnlyEpisode:
    entry_at: datetime
    ticker: str
    entry_quantity: float
    entry_notional: float
    entry_cost: float
    remaining_quantity: float
    remaining_cost: float
    fees: float
    slippage: float
    strategy_id: str
    account_id: str
    session_id: str
    exit_quantity: float = 0.0
    exit_notional: float = 0.0
    net_realized_pnl: float = 0.0


@dataclass(frozen=True, slots=True)
class _OpenLongPositionAccounting:
    average_cost_basis: float
    unrealized_pnl: float


def _matches_identity(
    *,
    record_strategy_id: str,
    record_account_id: str,
    record_decision_id: str,
    strategy_id: str | None,
    account_id: str | None,
    decision_id: str | None,
) -> bool:
    if strategy_id is not None and record_strategy_id != strategy_id:
        return False
    if account_id is not None and record_account_id != account_id:
        return False
    if decision_id is not None and record_decision_id != decision_id:
        return False
    return True


class TradeLedgerBackend(Protocol):
    """Storage abstraction so later phases can swap persistence backends."""

    def persist_fill(self, record: LedgerFillRecord) -> None: ...

    def persist_daily_snapshot(self, record: LedgerSnapshotRecord) -> None: ...

    def persist_initial_capital(self, record: LedgerInitialCapitalRecord) -> None: ...

    def load_fill_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerFillRecord]: ...

    def load_snapshot_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerSnapshotRecord]: ...

    def load_initial_capital_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
    ) -> list[LedgerInitialCapitalRecord]: ...


class InMemoryLedgerBackend:
    def __init__(self) -> None:
        self._fill_records: list[LedgerFillRecord] = []
        self._snapshot_records: list[LedgerSnapshotRecord] = []
        self._initial_capital_records: list[LedgerInitialCapitalRecord] = []

    def persist_fill(self, record: LedgerFillRecord) -> None:
        self._fill_records.append(record.model_copy(deep=True))

    def persist_daily_snapshot(self, record: LedgerSnapshotRecord) -> None:
        self._snapshot_records.append(record.model_copy(deep=True))

    def persist_initial_capital(self, record: LedgerInitialCapitalRecord) -> None:
        self._initial_capital_records.append(record.model_copy(deep=True))

    def load_fill_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerFillRecord]:
        records = [record.model_copy(deep=True) for record in self._fill_records]
        if session_id is not None:
            records = [
                record for record in records if record.fill.session_id == session_id
            ]
        return [
            record
            for record in records
            if _matches_identity(
                record_strategy_id=record.strategy_id,
                record_account_id=record.account_id,
                record_decision_id=record.decision_id,
                strategy_id=strategy_id,
                account_id=account_id,
                decision_id=decision_id,
            )
        ]

    def load_snapshot_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerSnapshotRecord]:
        records = [record.model_copy(deep=True) for record in self._snapshot_records]
        if session_id is not None:
            records = [
                record for record in records if record.account.session_id == session_id
            ]
        return [
            record
            for record in records
            if _matches_identity(
                record_strategy_id=record.strategy_id,
                record_account_id=record.account_id,
                record_decision_id=record.decision_id,
                strategy_id=strategy_id,
                account_id=account_id,
                decision_id=decision_id,
            )
        ]

    def load_initial_capital_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
    ) -> list[LedgerInitialCapitalRecord]:
        return [
            record.model_copy(deep=True)
            for record in self._initial_capital_records
            if (session_id is None or record.session_id == session_id)
            and (strategy_id is None or record.strategy_id == strategy_id)
            and (account_id is None or record.account_id == account_id)
        ]


class TradeLedger:
    """Collects trade logs and daily account snapshots through public exports."""

    _TRADE_COLUMNS = (
        "order_id",
        "timestamp",
        "ticker",
        "side",
        "quantity",
        "price",
        "fee",
        "slippage",
        "trade_value",
        "realized_pnl",
        "cash_after",
        "equity_after",
        "shares_after",
        "avg_cost_after",
        "session_id",
        "strategy_id",
        "account_id",
        "decision_id",
    )
    _PORTFOLIO_COLUMNS = (
        "date",
        "timestamp",
        "cash",
        "equity",
        "position_value",
        "position_count",
        "session_id",
        "strategy_id",
        "account_id",
        "decision_id",
    )
    _CLOSED_TRADE_COLUMNS = (
        "entry_at",
        "exit_at",
        "ticker",
        "quantity",
        "entry_vwap",
        "exit_vwap",
        "average_cost_basis",
        "net_realized_pnl",
        "fees",
        "slippage",
        "holding_period_trading_days",
        "session_id",
        "strategy_id",
        "account_id",
        "decision_id",
    )

    def __init__(self, backend: TradeLedgerBackend | None = None) -> None:
        self._backend = backend or InMemoryLedgerBackend()

    def record_initial_capital(
        self,
        initial_capital: float,
        *,
        session_id: str = "",
        strategy_id: str = "",
        account_id: str = "default",
    ) -> None:
        self._backend.persist_initial_capital(
            LedgerInitialCapitalRecord(
                initial_capital=initial_capital,
                strategy_id=strategy_id,
                account_id=account_id,
                session_id=session_id,
            )
        )

    def record_fill(
        self,
        fill: Fill,
        position: Position,
        account: AccountSnapshot,
    ) -> None:
        previous_position = self._get_latest_position(
            ticker=position.ticker,
            strategy_id=fill.strategy_id,
            account_id=fill.account_id,
            session_id=fill.session_id,
        )
        previous_shares = (
            previous_position.shares if previous_position is not None else 0.0
        )
        signed_qty = position.shares - previous_shares
        side = "BUY" if signed_qty > 0 else "SELL"
        realized_pnl = self._calculate_realized_pnl(
            previous_position=previous_position,
            signed_qty=signed_qty,
            fill=fill,
        )

        self._backend.persist_fill(
            LedgerFillRecord(
                fill=fill.model_copy(deep=True),
                ticker=position.ticker,
                side=side,
                realized_pnl=realized_pnl,
                position_after=position.model_copy(deep=True),
                account_after=account.model_copy(deep=True),
                strategy_id=fill.strategy_id,
                account_id=fill.account_id,
                session_id=fill.session_id,
                decision_id=fill.decision_id,
            )
        )

    def record_daily_snapshot(self, date: str, account: AccountSnapshot) -> None:
        self._backend.persist_daily_snapshot(
            LedgerSnapshotRecord(
                date=date,
                account=account.model_copy(deep=True),
                strategy_id=account.strategy_id,
                account_id=account.account_id,
                session_id=account.session_id,
                decision_id=account.decision_id,
            )
        )

    def compute_metrics(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252,
    ) -> dict[str, float | int | None]:
        if periods_per_year <= 0:
            raise ValueError("periods_per_year must be positive")
        portfolio = self.to_portfolio_dataframe(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        if portfolio.empty:
            return {
                "total_return": 0.0,
                "annualized_return": None,
                "annualized_volatility": None,
                "max_drawdown": 0.0,
                "max_drawdown_duration": 0,
                "sharpe_ratio": None,
                "win_rate": 0.0,
                "profit_factor": None,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "payoff_ratio": None,
                "number_of_trades": 0,
                "number_of_fills": 0,
                "number_of_orders": 0,
                "number_of_rejections": 0,
                "number_of_closed_trades": 0,
                "avg_holding_period_days": 0.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "net_pnl": 0.0,
                "total_fees": 0.0,
                "total_slippage": 0.0,
                "turnover": 0.0,
                "average_daily_gross_exposure": 0.0,
                "fees": 0.0,
                "slippage": 0.0,
            }

        equity_series = portfolio["equity"].astype(float)
        start_equity = self._initial_capital_for(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            first_equity=float(portfolio.iloc[0]["equity"]),
        )
        end_equity = float(equity_series.iloc[-1])
        total_return = end_equity / start_equity - 1 if start_equity != 0 else 0.0

        first_session_date = date.fromisoformat(str(portfolio.iloc[0]["date"]))
        last_session_date = date.fromisoformat(str(portfolio.iloc[-1]["date"]))
        calendar_days = (last_session_date - first_session_date).days
        annualized_return: float | None = None
        if start_equity > 0 and total_return >= -1 and calendar_days > 0:
            candidate = (1 + total_return) ** (365 / calendar_days) - 1
            if math.isfinite(candidate):
                annualized_return = candidate

        running_max = equity_series.cummax()
        drawdowns = 1 - equity_series / running_max
        max_drawdown = float(drawdowns.max()) if not drawdowns.empty else 0.0
        max_drawdown_duration = self._calculate_max_drawdown_duration(drawdowns)

        returns = equity_series.pct_change().dropna()
        annualized_volatility: float | None = None
        sharpe_ratio: float | None = None
        if len(returns) > 1:
            std = float(returns.std(ddof=1))
            annualized_volatility = std * math.sqrt(periods_per_year)
            if std > 0 and math.isfinite(annualized_volatility):
                daily_risk_free_rate = risk_free_rate / periods_per_year
                candidate = float(
                    (returns.mean() - daily_risk_free_rate)
                    / std
                    * math.sqrt(periods_per_year)
                )
                if math.isfinite(candidate):
                    sharpe_ratio = candidate

        executions = self.load_execution_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        closed_trades = self.load_closed_trade_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        closed_trade_pnl_values = [
            closed_trade.net_realized_pnl for closed_trade in closed_trades
        ]
        winning_trades = [value for value in closed_trade_pnl_values if value > 0]
        losing_trades = [value for value in closed_trade_pnl_values if value < 0]
        number_of_closed_trades = len(closed_trades)
        win_rate = (
            float(len(winning_trades) / number_of_closed_trades)
            if number_of_closed_trades
            else 0.0
        )

        gross_profit = sum(winning_trades)
        gross_loss = -sum(losing_trades)
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        else:
            profit_factor = None

        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0.0
        if avg_loss < 0:
            payoff_ratio = avg_win / abs(avg_loss)
        else:
            payoff_ratio = None

        realized_pnl = sum(record.realized_pnl for record in executions)
        net_pnl = end_equity - start_equity
        total_fees = sum(record.fill.fee for record in executions)
        total_slippage = sum(record.fill.slippage for record in executions)
        turnover = (
            sum(
                abs(record.fill.fill_price * record.fill.fill_qty)
                for record in executions
            )
            / start_equity
            if start_equity != 0
            else 0.0
        )
        daily_gross_exposures = [
            abs(float(row["position_value"])) / float(row["equity"])
            if float(row["equity"]) != 0
            else 0.0
            for _, row in portfolio.iterrows()
        ]

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "max_drawdown": max_drawdown,
            "max_drawdown_duration": max_drawdown_duration,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "payoff_ratio": payoff_ratio,
            "number_of_trades": number_of_closed_trades,
            "number_of_fills": len(executions),
            "number_of_orders": 0,
            "number_of_rejections": 0,
            "number_of_closed_trades": number_of_closed_trades,
            "avg_holding_period_days": self._average_holding_period_days(closed_trades),
            "realized_pnl": realized_pnl,
            "unrealized_pnl": net_pnl - realized_pnl,
            "net_pnl": net_pnl,
            "total_fees": total_fees,
            "total_slippage": total_slippage,
            "turnover": turnover,
            "average_daily_gross_exposure": (
                sum(daily_gross_exposures) / len(daily_gross_exposures)
                if daily_gross_exposures
                else 0.0
            ),
            "fees": total_fees,
            "slippage": total_slippage,
        }

    def to_trades_dataframe(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> pd.DataFrame:
        return self.to_executions_dataframe(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )

    def to_executions_dataframe(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> pd.DataFrame:
        records = self.load_execution_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        if not records:
            return pd.DataFrame(columns=pd.Index(self._TRADE_COLUMNS))

        return (
            pd.DataFrame(
                [self._trade_record_to_row(record) for record in records],
                columns=pd.Index(self._TRADE_COLUMNS),
            )
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def to_closed_trades_dataframe(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> pd.DataFrame:
        records = self.load_closed_trade_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        if not records:
            return pd.DataFrame(columns=pd.Index(self._CLOSED_TRADE_COLUMNS))

        return (
            pd.DataFrame(
                [self._closed_trade_record_to_row(record) for record in records],
                columns=pd.Index(self._CLOSED_TRADE_COLUMNS),
            )
            .sort_values("exit_at")
            .reset_index(drop=True)
        )

    def to_portfolio_dataframe(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> pd.DataFrame:
        records = self._backend.load_snapshot_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        if not records:
            return pd.DataFrame(columns=pd.Index(self._PORTFOLIO_COLUMNS))

        return (
            pd.DataFrame(
                [self._snapshot_record_to_row(record) for record in records],
                columns=pd.Index(self._PORTFOLIO_COLUMNS),
            )
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def to_csv(self, trades_path: str, portfolio_path: str) -> None:
        self.to_trades_dataframe().to_csv(trades_path, index=False)
        self.to_portfolio_dataframe().to_csv(portfolio_path, index=False)

    def load_fill_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerFillRecord]:
        return self.load_execution_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )

    def load_execution_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerFillRecord]:
        executions, _ = self._reconstruct_long_only_episodes(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        return executions

    def load_closed_trade_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[ClosedTradeRecord]:
        _, closed_trades = self._reconstruct_long_only_episodes(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )
        return closed_trades

    def load_snapshot_records(
        self,
        session_id: str | None = None,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        decision_id: str | None = None,
    ) -> list[LedgerSnapshotRecord]:
        return self._backend.load_snapshot_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=decision_id,
        )

    def open_long_position_accounting(
        self,
        *,
        ticker: str,
        mark_price: float,
        session_id: str,
        strategy_id: str,
        account_id: str,
    ) -> _OpenLongPositionAccounting | None:
        executions, _ = self._reconstruct_long_only_episodes(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
            decision_id=None,
        )
        for execution in reversed(executions):
            if execution.ticker != ticker:
                continue
            shares = execution.position_after.shares
            if shares <= 0:
                return None
            average_cost_basis = execution.position_after.avg_cost
            return _OpenLongPositionAccounting(
                average_cost_basis=average_cost_basis,
                unrealized_pnl=(mark_price - average_cost_basis) * shares,
            )
        return None

    def _reconstruct_long_only_episodes(
        self,
        *,
        session_id: str | None,
        strategy_id: str | None,
        account_id: str | None,
        decision_id: str | None,
    ) -> tuple[list[LedgerFillRecord], list[ClosedTradeRecord]]:
        records = sorted(
            self._backend.load_fill_records(
                session_id=session_id,
                strategy_id=strategy_id,
                account_id=account_id,
            ),
            key=lambda record: record.fill.timestamp,
        )
        snapshot_dates = self._snapshot_dates_by_identity(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
        )
        short_identity_keys = {
            (
                record.session_id,
                record.strategy_id,
                record.account_id,
                record.ticker,
            )
            for record in records
            if record.position_after.shares < 0
        }
        previous_shares_by_key: dict[_EpisodeKey, float] = {}
        open_episodes: dict[_EpisodeKey, _LongOnlyEpisode] = {}
        executions: list[LedgerFillRecord] = []
        closed_trades: list[ClosedTradeRecord] = []

        for record in records:
            key = (
                record.session_id,
                record.strategy_id,
                record.account_id,
                record.ticker,
            )
            if key in short_identity_keys:
                executions.append(record.model_copy(deep=True))
                continue
            previous_shares = previous_shares_by_key.get(key, 0.0)
            next_shares = record.position_after.shares
            signed_quantity = next_shares - previous_shares
            execution = record.model_copy(deep=True)
            execution.realized_pnl = 0.0

            if signed_quantity > 0:
                execution.side = "BUY"
                episode = open_episodes.get(key)
                entry_notional = record.fill.fill_price * signed_quantity
                entry_cost = entry_notional + record.fill.fee
                if episode is None:
                    episode = _LongOnlyEpisode(
                        entry_at=record.fill.timestamp,
                        ticker=record.ticker,
                        entry_quantity=signed_quantity,
                        entry_notional=entry_notional,
                        entry_cost=entry_cost,
                        remaining_quantity=signed_quantity,
                        remaining_cost=entry_cost,
                        fees=record.fill.fee,
                        slippage=record.fill.slippage,
                        strategy_id=record.strategy_id,
                        account_id=record.account_id,
                        session_id=record.session_id,
                    )
                    open_episodes[key] = episode
                else:
                    episode.entry_quantity += signed_quantity
                    episode.entry_notional += entry_notional
                    episode.entry_cost += entry_cost
                    episode.remaining_quantity += signed_quantity
                    episode.remaining_cost += entry_cost
                    episode.fees += record.fill.fee
                    episode.slippage += record.fill.slippage
                execution.position_after = execution.position_after.model_copy(
                    update={
                        "avg_cost": (
                            episode.remaining_cost / episode.remaining_quantity
                        )
                    }
                )
            elif signed_quantity < 0:
                execution.side = "SELL"
                episode = open_episodes.get(key)
                if episode is not None and episode.remaining_quantity > 0:
                    closed_quantity = min(-signed_quantity, episode.remaining_quantity)
                    fee_allocation = record.fill.fee * (
                        closed_quantity / -signed_quantity
                    )
                    slippage_allocation = record.fill.slippage * (
                        closed_quantity / -signed_quantity
                    )
                    cost_per_share = episode.remaining_cost / episode.remaining_quantity
                    realized_pnl = (
                        record.fill.fill_price * closed_quantity
                        - fee_allocation
                        - cost_per_share * closed_quantity
                    )
                    execution.realized_pnl = realized_pnl
                    episode.remaining_quantity -= closed_quantity
                    episode.remaining_cost -= cost_per_share * closed_quantity
                    episode.exit_quantity += closed_quantity
                    episode.exit_notional += record.fill.fill_price * closed_quantity
                    episode.fees += fee_allocation
                    episode.slippage += slippage_allocation
                    episode.net_realized_pnl += realized_pnl

                    if episode.remaining_quantity > 0:
                        execution.position_after = execution.position_after.model_copy(
                            update={
                                "avg_cost": (
                                    episode.remaining_cost / episode.remaining_quantity
                                )
                            }
                        )

                    if math.isclose(
                        episode.remaining_quantity, 0.0, rel_tol=0.0, abs_tol=1e-12
                    ):
                        closed_trades.append(
                            ClosedTradeRecord(
                                entry_at=episode.entry_at,
                                exit_at=record.fill.timestamp,
                                ticker=episode.ticker,
                                quantity=episode.entry_quantity,
                                entry_vwap=(
                                    episode.entry_notional / episode.entry_quantity
                                ),
                                exit_vwap=episode.exit_notional / episode.exit_quantity,
                                average_cost_basis=(
                                    episode.entry_cost / episode.entry_quantity
                                ),
                                net_realized_pnl=episode.net_realized_pnl,
                                fees=episode.fees,
                                slippage=episode.slippage,
                                holding_period_trading_days=(
                                    self._holding_period_trading_days(
                                        entry_at=episode.entry_at,
                                        exit_at=record.fill.timestamp,
                                        strategy_id=episode.strategy_id,
                                        account_id=episode.account_id,
                                        session_id=episode.session_id,
                                        snapshot_dates=snapshot_dates,
                                    )
                                ),
                                strategy_id=episode.strategy_id,
                                account_id=episode.account_id,
                                session_id=episode.session_id,
                                decision_id=record.decision_id,
                            )
                        )
                        del open_episodes[key]

            executions.append(execution)
            previous_shares_by_key[key] = next_shares

        if decision_id is not None:
            executions = [
                execution
                for execution in executions
                if execution.decision_id == decision_id
            ]
            closed_trades = [
                closed_trade
                for closed_trade in closed_trades
                if closed_trade.decision_id == decision_id
            ]
        return executions, closed_trades

    def _snapshot_dates_by_identity(
        self,
        *,
        session_id: str | None,
        strategy_id: str | None,
        account_id: str | None,
    ) -> dict[tuple[str, str, str], set[str]]:
        snapshot_dates: dict[tuple[str, str, str], set[str]] = {}
        for record in self._backend.load_snapshot_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
        ):
            key = (record.session_id, record.strategy_id, record.account_id)
            snapshot_dates.setdefault(key, set()).add(record.date)
        return snapshot_dates

    def _holding_period_trading_days(
        self,
        *,
        entry_at: datetime,
        exit_at: datetime,
        strategy_id: str,
        account_id: str,
        session_id: str,
        snapshot_dates: dict[tuple[str, str, str], set[str]],
    ) -> int:
        entry_date = entry_at.date().isoformat()
        exit_date = exit_at.date().isoformat()
        observed_dates = {
            date
            for date in snapshot_dates.get((session_id, strategy_id, account_id), set())
            if entry_date <= date <= exit_date
        }
        if len(observed_dates) > 1:
            return len(observed_dates) - 1
        return max(len(pd.bdate_range(entry_at.date(), exit_at.date())) - 1, 0)

    def _initial_capital_for(
        self,
        *,
        session_id: str | None,
        strategy_id: str | None,
        account_id: str | None,
        first_equity: float,
    ) -> float:
        records = self._backend.load_initial_capital_records(
            session_id=session_id,
            strategy_id=strategy_id,
            account_id=account_id,
        )
        if records:
            return records[-1].initial_capital
        return first_equity

    def _average_holding_period_days(
        self, closed_trades: list[ClosedTradeRecord]
    ) -> float:
        if not closed_trades:
            return 0.0
        return sum(
            closed_trade.holding_period_trading_days for closed_trade in closed_trades
        ) / len(closed_trades)

    def _trade_record_to_row(self, record: LedgerFillRecord) -> dict[str, object]:
        return {
            "order_id": record.fill.order_id,
            "timestamp": record.fill.timestamp,
            "ticker": record.ticker,
            "side": record.side,
            "quantity": record.fill.fill_qty,
            "price": record.fill.fill_price,
            "fee": record.fill.fee,
            "slippage": record.fill.slippage,
            "trade_value": record.fill.fill_price * record.fill.fill_qty,
            "realized_pnl": record.realized_pnl,
            "cash_after": record.account_after.cash,
            "equity_after": record.account_after.equity,
            "shares_after": record.position_after.shares,
            "avg_cost_after": record.position_after.avg_cost,
            "session_id": record.fill.session_id,
            "strategy_id": record.strategy_id,
            "account_id": record.account_id,
            "decision_id": record.decision_id,
        }

    def _closed_trade_record_to_row(
        self, record: ClosedTradeRecord
    ) -> dict[str, object]:
        return {
            "entry_at": record.entry_at,
            "exit_at": record.exit_at,
            "ticker": record.ticker,
            "quantity": record.quantity,
            "entry_vwap": record.entry_vwap,
            "exit_vwap": record.exit_vwap,
            "average_cost_basis": record.average_cost_basis,
            "net_realized_pnl": record.net_realized_pnl,
            "fees": record.fees,
            "slippage": record.slippage,
            "holding_period_trading_days": record.holding_period_trading_days,
            "session_id": record.session_id,
            "strategy_id": record.strategy_id,
            "account_id": record.account_id,
            "decision_id": record.decision_id,
        }

    def _snapshot_record_to_row(
        self,
        record: LedgerSnapshotRecord,
    ) -> dict[str, object]:
        return {
            "date": record.date,
            "timestamp": record.account.timestamp,
            "cash": record.account.cash,
            "equity": record.account.equity,
            "position_value": record.account.equity - record.account.cash,
            "position_count": len(record.account.positions),
            "session_id": record.account.session_id,
            "strategy_id": record.strategy_id,
            "account_id": record.account_id,
            "decision_id": record.decision_id,
        }

    def _get_latest_position(
        self,
        *,
        ticker: str,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> Position | None:
        records = self._backend.load_fill_records(session_id=session_id)
        for record in reversed(records):
            if (
                record.ticker == ticker
                and record.strategy_id == strategy_id
                and record.account_id == account_id
            ):
                return record.position_after.model_copy(deep=True)
        return None

    def _calculate_realized_pnl(
        self,
        *,
        previous_position: Position | None,
        signed_qty: float,
        fill: Fill,
    ) -> float:
        if previous_position is None or previous_position.shares == 0:
            return 0.0

        if previous_position.shares * signed_qty > 0:
            return 0.0

        close_qty = min(abs(previous_position.shares), abs(signed_qty))
        if close_qty == 0:
            return 0.0

        if previous_position.shares > 0 and signed_qty < 0:
            gross_realized_pnl = (
                fill.fill_price - previous_position.avg_cost
            ) * close_qty
        else:
            gross_realized_pnl = (
                previous_position.avg_cost - fill.fill_price
            ) * close_qty
        return gross_realized_pnl - fill.fee

    def _calculate_max_drawdown_duration(self, drawdowns: pd.Series) -> int:
        max_duration = 0
        current_duration = 0
        for drawdown in drawdowns:
            if drawdown > 0:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0
        return max_duration
