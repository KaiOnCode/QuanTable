from __future__ import annotations

import math
from datetime import datetime
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


class TradeLedgerBackend(Protocol):
    """Storage abstraction so later phases can swap persistence backends."""

    def persist_fill(self, record: LedgerFillRecord) -> None: ...

    def persist_daily_snapshot(self, record: LedgerSnapshotRecord) -> None: ...

    def load_fill_records(
        self,
        session_id: str | None = None,
    ) -> list[LedgerFillRecord]: ...

    def load_snapshot_records(
        self,
        session_id: str | None = None,
    ) -> list[LedgerSnapshotRecord]: ...


class InMemoryLedgerBackend:
    def __init__(self) -> None:
        self._fill_records: list[LedgerFillRecord] = []
        self._snapshot_records: list[LedgerSnapshotRecord] = []

    def persist_fill(self, record: LedgerFillRecord) -> None:
        self._fill_records.append(record.model_copy(deep=True))

    def persist_daily_snapshot(self, record: LedgerSnapshotRecord) -> None:
        self._snapshot_records.append(record.model_copy(deep=True))

    def load_fill_records(
        self,
        session_id: str | None = None,
    ) -> list[LedgerFillRecord]:
        records = [record.model_copy(deep=True) for record in self._fill_records]
        if session_id is None:
            return records
        return [record for record in records if record.fill.session_id == session_id]

    def load_snapshot_records(
        self,
        session_id: str | None = None,
    ) -> list[LedgerSnapshotRecord]:
        records = [record.model_copy(deep=True) for record in self._snapshot_records]
        if session_id is None:
            return records
        return [record for record in records if record.account.session_id == session_id]


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

    def __init__(self, backend: TradeLedgerBackend | None = None) -> None:
        self._backend = backend or InMemoryLedgerBackend()

    def record_fill(
        self,
        fill: Fill,
        position: Position,
        account: AccountSnapshot,
    ) -> None:
        previous_position = self._get_latest_position(
            ticker=position.ticker,
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

    def compute_metrics(self, session_id: str | None = None) -> dict[str, float | int]:
        portfolio = self.to_portfolio_dataframe(session_id=session_id)
        if portfolio.empty:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_duration": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "payoff_ratio": 0.0,
                "number_of_trades": 0,
                "avg_holding_period_days": 0.0,
            }

        equity_series = portfolio["equity"].astype(float)
        start_equity = float(equity_series.iloc[0])
        end_equity = float(equity_series.iloc[-1])
        total_return = end_equity / start_equity - 1 if start_equity != 0 else 0.0

        start_timestamp = pd.Timestamp(portfolio.iloc[0]["timestamp"])
        end_timestamp = pd.Timestamp(portfolio.iloc[-1]["timestamp"])
        elapsed_days = max(
            (end_timestamp - start_timestamp).total_seconds() / 86_400,
            1.0,
        )
        annualized_return = 0.0
        if start_equity > 0 and total_return > -1:
            annualized_return = (1 + total_return) ** (365 / elapsed_days) - 1

        running_max = equity_series.cummax()
        drawdowns = 1 - equity_series / running_max
        max_drawdown = float(drawdowns.max()) if not drawdowns.empty else 0.0
        max_drawdown_duration = float(self._calculate_max_drawdown_duration(drawdowns))

        returns = equity_series.pct_change().dropna()
        sharpe_ratio = 0.0
        if len(returns) > 1:
            std = float(returns.std(ddof=1))
            if std > 0:
                sharpe_ratio = float(returns.mean() / std * math.sqrt(252))

        trades = self.to_trades_dataframe(session_id=session_id)
        realized_pnl_values = (
            [float(value) for value in trades["realized_pnl"].tolist()]
            if not trades.empty
            else []
        )
        winning_trades = [value for value in realized_pnl_values if value > 0]
        losing_trades = [value for value in realized_pnl_values if value < 0]
        number_of_trades = len(realized_pnl_values)
        win_rate = (
            float(len(winning_trades) / number_of_trades) if number_of_trades else 0.0
        )

        gross_profit = sum(winning_trades)
        gross_loss = -sum(losing_trades)
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = math.inf
        else:
            profit_factor = 0.0

        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0.0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0.0
        if avg_loss < 0:
            payoff_ratio = avg_win / abs(avg_loss)
        elif avg_win > 0:
            payoff_ratio = math.inf
        else:
            payoff_ratio = 0.0

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "max_drawdown": max_drawdown,
            "max_drawdown_duration": max_drawdown_duration,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "payoff_ratio": payoff_ratio,
            "number_of_trades": number_of_trades,
            "avg_holding_period_days": self._calculate_avg_holding_period_days(
                session_id=session_id,
            ),
        }

    def to_trades_dataframe(self, session_id: str | None = None) -> pd.DataFrame:
        records = self._backend.load_fill_records(session_id=session_id)
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

    def to_portfolio_dataframe(self, session_id: str | None = None) -> pd.DataFrame:
        records = self._backend.load_snapshot_records(session_id=session_id)
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
    ) -> list[LedgerFillRecord]:
        return self._backend.load_fill_records(session_id=session_id)

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
        account_id: str,
        session_id: str,
    ) -> Position | None:
        records = self._backend.load_fill_records(session_id=session_id)
        for record in reversed(records):
            if record.ticker == ticker and record.account_id == account_id:
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
            return -(fill.fee + fill.slippage)

        if previous_position.shares * signed_qty > 0:
            return -(fill.fee + fill.slippage)

        close_qty = min(abs(previous_position.shares), abs(signed_qty))
        if close_qty == 0:
            return -(fill.fee + fill.slippage)

        if previous_position.shares > 0 and signed_qty < 0:
            gross_realized_pnl = (
                fill.fill_price - previous_position.avg_cost
            ) * close_qty
        else:
            gross_realized_pnl = (
                previous_position.avg_cost - fill.fill_price
            ) * close_qty
        return gross_realized_pnl - fill.fee - fill.slippage

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

    def _calculate_avg_holding_period_days(
        self,
        session_id: str | None = None,
    ) -> float:
        fill_records = sorted(
            self._backend.load_fill_records(session_id=session_id),
            key=lambda record: record.fill.timestamp,
        )
        holding_start_times: dict[tuple[str, str, str], datetime] = {}
        previous_shares_by_key: dict[tuple[str, str, str], float] = {}
        closed_holding_period_days: list[float] = []

        for record in fill_records:
            key = (record.fill.session_id, record.account_id, record.ticker)
            previous_shares = previous_shares_by_key.get(key, 0.0)
            next_shares = record.position_after.shares
            previous_sign = self._position_sign(previous_shares)
            next_sign = self._position_sign(next_shares)

            if previous_sign == 0 and next_sign != 0:
                holding_start_times[key] = record.fill.timestamp
            elif previous_sign != 0 and next_sign == 0:
                started_at = holding_start_times.pop(key, None)
                if started_at is not None:
                    closed_holding_period_days.append(
                        (record.fill.timestamp - started_at).total_seconds() / 86_400
                    )
            elif previous_sign != 0 and next_sign != 0 and previous_sign != next_sign:
                started_at = holding_start_times.get(key)
                if started_at is not None:
                    closed_holding_period_days.append(
                        (record.fill.timestamp - started_at).total_seconds() / 86_400
                    )
                holding_start_times[key] = record.fill.timestamp

            previous_shares_by_key[key] = next_shares

        if not closed_holding_period_days:
            return 0.0
        return sum(closed_holding_period_days) / len(closed_holding_period_days)

    def _position_sign(self, shares: float) -> int:
        if shares > 0:
            return 1
        if shares < 0:
            return -1
        return 0
