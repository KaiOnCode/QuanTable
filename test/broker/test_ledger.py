from __future__ import annotations

from datetime import datetime, timezone

import pytest

from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.ledger import (
    InMemoryLedgerBackend,
    LedgerFillRecord,
    LedgerSnapshotRecord,
    TradeLedger,
)
from broker.models import (
    AccountSnapshot,
    Fill,
    Order,
    OrderSide,
    OrderType,
    Position,
)


def test_trade_ledger_records_a_fill_and_exposes_it_via_trade_export() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.001,
            slippage_rate=0.0005,
        )
    )
    broker.on_bar(
        {
            "AAPL": {
                "open": 99.0,
                "high": 101.0,
                "low": 98.0,
                "close": 100.0,
            }
        }
    )
    order = broker.place_order(
        Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=10,
        )
    )

    fill = broker.get_fills(order.id)[0]
    position = broker.get_position("AAPL")
    assert position is not None

    ledger = TradeLedger()
    ledger.record_fill(
        fill=fill,
        position=position,
        account=broker.get_account(),
    )

    trades = ledger.to_trades_dataframe()

    assert len(trades) == 1
    assert trades.loc[0, "order_id"] == order.id
    assert trades.loc[0, "ticker"] == "AAPL"
    assert trades.loc[0, "side"] == "BUY"
    assert trades.loc[0, "quantity"] == pytest.approx(10.0)
    assert trades.loc[0, "price"] == pytest.approx(100.05)


def test_trade_ledger_records_daily_snapshot_and_exposes_portfolio_export() -> None:
    ledger = TradeLedger()
    account = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[
            Position(
                ticker="AAPL",
                shares=10,
                avg_cost=100.05,
                unrealized_pnl=-0.5,
            )
        ],
    )

    ledger.record_daily_snapshot("2026-04-13", account)

    portfolio = ledger.to_portfolio_dataframe()

    assert len(portfolio) == 1
    assert portfolio.loc[0, "date"] == "2026-04-13"
    assert portfolio.loc[0, "cash"] == pytest.approx(98_998.4995)
    assert portfolio.loc[0, "equity"] == pytest.approx(99_998.4995)
    assert portfolio.loc[0, "position_value"] == pytest.approx(1_000.0)
    assert portfolio.loc[0, "position_count"] == 1


def test_trade_ledger_rehydrates_trades_and_snapshots_from_shared_backend() -> None:
    backend = InMemoryLedgerBackend()
    writer = TradeLedger(backend=backend)
    account = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[
            Position(
                ticker="AAPL",
                shares=10,
                avg_cost=100.05,
                unrealized_pnl=-0.5,
            )
        ],
    )
    writer.record_fill(
        fill=Fill(
            order_id="order-1",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
        ),
        position=account.positions[0],
        account=account,
    )
    writer.record_daily_snapshot("2026-04-13", account)

    reader = TradeLedger(backend=backend)

    trades = reader.to_trades_dataframe()
    portfolio = reader.to_portfolio_dataframe()

    assert len(trades) == 1
    assert trades.loc[0, "ticker"] == "AAPL"
    assert trades.loc[0, "price"] == pytest.approx(100.05)
    assert len(portfolio) == 1
    assert portfolio.loc[0, "date"] == "2026-04-13"
    assert portfolio.loc[0, "equity"] == pytest.approx(99_998.4995)


def test_ledger_records_expose_identity_defaults() -> None:
    account = AccountSnapshot(cash=100_000.0, equity=100_000.0)
    position = Position(ticker="AAPL", shares=10, avg_cost=100.05)
    fill_record = LedgerFillRecord(
        fill=Fill(
            order_id="order-1",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
        ),
        ticker="AAPL",
        side="BUY",
        realized_pnl=-1.5005,
        position_after=position,
        account_after=account,
    )
    snapshot_record = LedgerSnapshotRecord(date="2026-04-13", account=account)

    assert fill_record.strategy_id == ""
    assert fill_record.account_id == "default"
    assert fill_record.session_id == ""
    assert fill_record.decision_id == ""
    assert snapshot_record.strategy_id == ""
    assert snapshot_record.account_id == "default"
    assert snapshot_record.session_id == ""
    assert snapshot_record.decision_id == ""


def test_in_memory_ledger_backend_round_trips_identity_fields() -> None:
    backend = InMemoryLedgerBackend()
    account = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[
            Position(
                ticker="AAPL",
                shares=10,
                avg_cost=100.05,
                strategy_id="strategy-1",
                account_id="account-1",
                session_id="session-1",
                decision_id="decision-1",
            )
        ],
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    backend.persist_fill(
        LedgerFillRecord(
            fill=Fill(
                order_id="order-1",
                fill_price=100.05,
                fill_qty=10,
                fee=1.0005,
                slippage=0.5,
                strategy_id="strategy-1",
                account_id="account-1",
                session_id="session-1",
                decision_id="decision-1",
            ),
            ticker="AAPL",
            side="BUY",
            realized_pnl=-1.5005,
            position_after=account.positions[0],
            account_after=account,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        )
    )
    backend.persist_daily_snapshot(
        LedgerSnapshotRecord(
            date="2026-04-13",
            account=account,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        )
    )

    fill_records = backend.load_fill_records(session_id="session-1")
    snapshot_records = backend.load_snapshot_records(session_id="session-1")

    assert len(fill_records) == 1
    assert fill_records[0].strategy_id == "strategy-1"
    assert fill_records[0].account_id == "account-1"
    assert fill_records[0].session_id == "session-1"
    assert fill_records[0].decision_id == "decision-1"
    assert fill_records[0].fill.strategy_id == "strategy-1"
    assert fill_records[0].position_after.account_id == "account-1"
    assert fill_records[0].account_after.decision_id == "decision-1"
    assert len(snapshot_records) == 1
    assert snapshot_records[0].strategy_id == "strategy-1"
    assert snapshot_records[0].account_id == "account-1"
    assert snapshot_records[0].session_id == "session-1"
    assert snapshot_records[0].decision_id == "decision-1"


def test_trade_ledger_keeps_previous_positions_isolated_by_account_id() -> None:
    ledger = TradeLedger()
    account_a_position = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.05,
        account_id="account-a",
        session_id="shared-session",
    )
    account_b_position = Position(
        ticker="AAPL",
        shares=5,
        avg_cost=101.05,
        account_id="account-b",
        session_id="shared-session",
    )
    ledger.record_fill(
        fill=Fill(
            order_id="account-a-order",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
            account_id="account-a",
            session_id="shared-session",
        ),
        position=account_a_position,
        account=AccountSnapshot(
            cash=98_998.4995,
            equity=99_998.4995,
            positions=[account_a_position],
            account_id="account-a",
            session_id="shared-session",
        ),
    )

    ledger.record_fill(
        fill=Fill(
            order_id="account-b-order",
            fill_price=101.05,
            fill_qty=5,
            fee=0.50525,
            slippage=0.25,
            account_id="account-b",
            session_id="shared-session",
        ),
        position=account_b_position,
        account=AccountSnapshot(
            cash=99_494.24475,
            equity=99_999.49475,
            positions=[account_b_position],
            account_id="account-b",
            session_id="shared-session",
        ),
    )

    trades = ledger.to_trades_dataframe()

    assert trades.loc[1, "side"] == "BUY"
    assert trades.loc[1, "realized_pnl"] == pytest.approx(-0.75525)


def test_trade_ledger_exports_csv_from_persisted_backend_records(tmp_path) -> None:
    backend = InMemoryLedgerBackend()
    writer = TradeLedger(backend=backend)
    account = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[
            Position(
                ticker="AAPL",
                shares=10,
                avg_cost=100.05,
                unrealized_pnl=-0.5,
            )
        ],
    )
    writer.record_fill(
        fill=Fill(
            order_id="order-1",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
        ),
        position=account.positions[0],
        account=account,
    )
    writer.record_daily_snapshot("2026-04-13", account)

    reader = TradeLedger(backend=backend)
    trades_path = tmp_path / "trades.csv"
    portfolio_path = tmp_path / "portfolio.csv"

    reader.to_csv(str(trades_path), str(portfolio_path))

    trades_text = trades_path.read_text()
    portfolio_text = portfolio_path.read_text()

    assert "order_id,timestamp,ticker,side" in trades_text
    assert "AAPL,BUY,10.0,100.05" in trades_text
    assert "date,timestamp,cash,equity" in portfolio_text
    assert "2026-04-13" in portfolio_text


def test_trade_ledger_computes_core_metrics_from_snapshots_and_round_trip_fills() -> (
    None
):
    ledger = TradeLedger()

    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry_timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    exit_timestamp = datetime(2026, 1, 3, tzinfo=timezone.utc)

    ledger.record_daily_snapshot(
        "2026-01-01",
        AccountSnapshot(
            cash=100_000.0,
            equity=100_000.0,
            positions=[],
            timestamp=started_at,
        ),
    )

    open_position = Position(ticker="AAPL", shares=10, avg_cost=100.05)
    account_after_entry = AccountSnapshot(
        cash=98_998.4995,
        equity=99_998.4995,
        positions=[open_position],
        timestamp=entry_timestamp,
    )
    ledger.record_fill(
        fill=Fill(
            order_id="entry-order",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
            timestamp=entry_timestamp,
        ),
        position=open_position,
        account=account_after_entry,
    )
    ledger.record_daily_snapshot("2026-01-02", account_after_entry)

    flat_position = Position(ticker="AAPL", shares=0, avg_cost=0.0)
    account_after_exit = AccountSnapshot(
        cash=100_096.85005,
        equity=100_096.85005,
        positions=[],
        timestamp=exit_timestamp,
    )
    ledger.record_fill(
        fill=Fill(
            order_id="exit-order",
            fill_price=109.945,
            fill_qty=10,
            fee=1.09945,
            slippage=0.55,
            timestamp=exit_timestamp,
        ),
        position=flat_position,
        account=account_after_exit,
    )
    ledger.record_daily_snapshot("2026-01-03", account_after_exit)

    trades = ledger.to_trades_dataframe()
    metrics = ledger.compute_metrics()

    expected_total_return = account_after_exit.equity / 100_000.0 - 1
    expected_max_drawdown = (100_000.0 - account_after_entry.equity) / 100_000.0

    assert trades.loc[0, "realized_pnl"] == pytest.approx(-1.5005)
    assert trades.loc[1, "realized_pnl"] == pytest.approx(97.30055)
    assert metrics["number_of_trades"] == 2
    assert metrics["total_return"] == pytest.approx(expected_total_return)
    assert metrics["max_drawdown"] == pytest.approx(expected_max_drawdown)
    assert metrics["win_rate"] == pytest.approx(0.5)
    assert metrics["avg_win"] == pytest.approx(97.30055)
    assert metrics["avg_loss"] == pytest.approx(-1.5005)
    assert metrics["profit_factor"] == pytest.approx(64.84541819393536)
    assert metrics["payoff_ratio"] == pytest.approx(64.84541819393536)
    assert metrics["annualized_return"] > metrics["total_return"]
    assert metrics["sharpe_ratio"] > 0
    assert metrics["max_drawdown_duration"] == pytest.approx(1.0)
    assert metrics["avg_holding_period_days"] == pytest.approx(1.0)
