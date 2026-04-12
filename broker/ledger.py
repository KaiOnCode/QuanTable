from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Protocol

import pandas as pd

from broker.models import AccountSnapshot, Fill, Position


class TradeLedgerBackend(Protocol):
    """Storage abstraction so later phases can swap persistence backends."""

    def persist_fill(
        self,
        fill: Fill,
        position: Position,
        account: AccountSnapshot,
    ) -> None: ...

    def persist_daily_snapshot(self, date: str, account: AccountSnapshot) -> None: ...

    def load_fills(self, session_id: str | None = None) -> list[Fill]: ...

    def load_snapshots(
        self, session_id: str | None = None
    ) -> list[AccountSnapshot]: ...


class InMemoryLedgerBackend:
    def __init__(self) -> None:
        self._fills: list[Fill] = []
        self._snapshots: list[AccountSnapshot] = []

    def persist_fill(
        self,
        fill: Fill,
        position: Position,
        account: AccountSnapshot,
    ) -> None:
        _ = position
        _ = account
        self._fills.append(fill.model_copy(deep=True))

    def persist_daily_snapshot(self, date: str, account: AccountSnapshot) -> None:
        _ = date
        self._snapshots.append(account.model_copy(deep=True))

    def load_fills(self, session_id: str | None = None) -> list[Fill]:
        fills = [fill.model_copy(deep=True) for fill in self._fills]
        if session_id is None:
            return fills
        return [fill for fill in fills if fill.session_id == session_id]

    def load_snapshots(self, session_id: str | None = None) -> list[AccountSnapshot]:
        snapshots = [snapshot.model_copy(deep=True) for snapshot in self._snapshots]
        if session_id is None:
            return snapshots
        return [snapshot for snapshot in snapshots if snapshot.session_id == session_id]


class TradeLedger:
    """Collects trade logs and daily account snapshots through public exports."""

    _TRADE_COLUMNS = [
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
    ]
    _PORTFOLIO_COLUMNS = [
        "date",
        "timestamp",
        "cash",
        "equity",
        "position_value",
        "position_count",
        "session_id",
    ]

    def __init__(self, backend: TradeLedgerBackend | None = None) -> None:
        self._backend = backend or InMemoryLedgerBackend()
        self._trade_rows: list[dict[str, Any]] = []
        self._portfolio_rows: list[dict[str, Any]] = []
        self._latest_positions: dict[str, Position] = {}
        self._holding_start_times: dict[str, datetime] = {}
        self._closed_holding_period_days: list[float] = []

    def record_fill(
        self,
        fill: Fill,
        position: Position,
        account: AccountSnapshot,
    ) -> None:
        previous_position = self._latest_positions.get(position.ticker)
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

        self._backend.persist_fill(fill, position, account)
        self._trade_rows.append(
            {
                "order_id": fill.order_id,
                "timestamp": fill.timestamp,
                "ticker": position.ticker,
                "side": side,
                "quantity": fill.fill_qty,
                "price": fill.fill_price,
                "fee": fill.fee,
                "slippage": fill.slippage,
                "trade_value": fill.fill_price * fill.fill_qty,
                "realized_pnl": realized_pnl,
                "cash_after": account.cash,
                "equity_after": account.equity,
                "shares_after": position.shares,
                "avg_cost_after": position.avg_cost,
                "session_id": fill.session_id,
            }
        )
        self._update_holding_periods(
            ticker=position.ticker,
            previous_position=previous_position,
            next_position=position,
            timestamp=fill.timestamp,
        )
        if position.shares == 0:
            self._latest_positions.pop(position.ticker, None)
        else:
            self._latest_positions[position.ticker] = position.model_copy(deep=True)

    def record_daily_snapshot(self, date: str, account: AccountSnapshot) -> None:
        self._backend.persist_daily_snapshot(date, account)
        self._portfolio_rows.append(
            {
                "date": date,
                "timestamp": account.timestamp,
                "cash": account.cash,
                "equity": account.equity,
                "position_value": account.equity - account.cash,
                "position_count": len(account.positions),
                "session_id": account.session_id,
            }
        )

    def compute_metrics(self) -> dict[str, float | int]:
        portfolio = self.to_portfolio_dataframe()
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

        trades = self.to_trades_dataframe()
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
            "avg_holding_period_days": self._calculate_avg_holding_period_days(),
        }

    def to_trades_dataframe(self) -> pd.DataFrame:
        if not self._trade_rows:
            return pd.DataFrame(columns=pd.Index(self._TRADE_COLUMNS))
        return (
            pd.DataFrame(self._trade_rows)
            .reindex(columns=self._TRADE_COLUMNS)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def to_portfolio_dataframe(self) -> pd.DataFrame:
        if not self._portfolio_rows:
            return pd.DataFrame(columns=pd.Index(self._PORTFOLIO_COLUMNS))
        return (
            pd.DataFrame(self._portfolio_rows)
            .reindex(columns=self._PORTFOLIO_COLUMNS)
            .sort_values("timestamp")
            .reset_index(drop=True)
        )

    def to_csv(self, trades_path: str, portfolio_path: str) -> None:
        self.to_trades_dataframe().to_csv(trades_path, index=False)
        self.to_portfolio_dataframe().to_csv(portfolio_path, index=False)

    def _calculate_realized_pnl(
        self,
        *,
        previous_position: Position | None,
        signed_qty: float,
        fill: Fill,
    ) -> float:
        if previous_position is None or previous_position.shares == 0:
            return -fill.fee

        if previous_position.shares * signed_qty > 0:
            return -fill.fee

        close_qty = min(abs(previous_position.shares), abs(signed_qty))
        if close_qty == 0:
            return -fill.fee

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

    def _update_holding_periods(
        self,
        *,
        ticker: str,
        previous_position: Position | None,
        next_position: Position,
        timestamp: datetime,
    ) -> None:
        previous_sign = self._position_sign(
            previous_position.shares if previous_position is not None else 0.0
        )
        next_sign = self._position_sign(next_position.shares)

        if previous_sign == 0 and next_sign != 0:
            self._holding_start_times[ticker] = timestamp
            return

        if previous_sign != 0 and next_sign == 0:
            self._close_holding_period(ticker=ticker, timestamp=timestamp)
            return

        if previous_sign != 0 and next_sign != 0 and previous_sign != next_sign:
            self._close_holding_period(ticker=ticker, timestamp=timestamp)
            self._holding_start_times[ticker] = timestamp

    def _close_holding_period(self, *, ticker: str, timestamp: datetime) -> None:
        started_at = self._holding_start_times.pop(ticker, None)
        if started_at is None:
            return
        holding_days = (timestamp - started_at).total_seconds() / 86_400
        self._closed_holding_period_days.append(holding_days)

    def _calculate_avg_holding_period_days(self) -> float:
        if not self._closed_holding_period_days:
            return 0.0
        return sum(self._closed_holding_period_days) / len(
            self._closed_holding_period_days
        )

    def _position_sign(self, shares: float) -> int:
        if shares > 0:
            return 1
        if shares < 0:
            return -1
        return 0
