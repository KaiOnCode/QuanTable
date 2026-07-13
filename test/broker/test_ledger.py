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


def test_in_memory_ledger_backend_filters_by_identity_fields() -> None:
    backend = InMemoryLedgerBackend()
    ledger = TradeLedger(backend=backend)
    first_position = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.0,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    first_account = AccountSnapshot(
        cash=99_000.0,
        equity=100_000.0,
        positions=[first_position],
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )
    second_position = Position(
        ticker="MSFT",
        shares=5,
        avg_cost=200.0,
        strategy_id="strategy-2",
        account_id="account-2",
        session_id="session-2",
        decision_id="decision-2",
    )
    second_account = AccountSnapshot(
        cash=99_000.0,
        equity=100_000.0,
        positions=[second_position],
        strategy_id="strategy-2",
        account_id="account-2",
        session_id="session-2",
        decision_id="decision-2",
    )
    ledger.record_fill(
        Fill(
            order_id="order-1",
            fill_price=100.0,
            fill_qty=10,
            fee=1.0,
            slippage=0.5,
            strategy_id="strategy-1",
            account_id="account-1",
            session_id="session-1",
            decision_id="decision-1",
        ),
        first_position,
        first_account,
    )
    ledger.record_fill(
        Fill(
            order_id="order-2",
            fill_price=200.0,
            fill_qty=5,
            fee=1.0,
            slippage=0.5,
            strategy_id="strategy-2",
            account_id="account-2",
            session_id="session-2",
            decision_id="decision-2",
        ),
        second_position,
        second_account,
    )

    records = ledger.load_fill_records(
        strategy_id="strategy-2",
        account_id="account-2",
        decision_id="decision-2",
    )

    assert [record.fill.order_id for record in records] == ["order-2"]


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
    assert trades.loc[1, "realized_pnl"] == pytest.approx(0.0)


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

    assert trades.loc[0, "realized_pnl"] == pytest.approx(0.0)
    assert trades.loc[1, "realized_pnl"] == pytest.approx(96.85005)
    assert metrics["number_of_trades"] == 1
    assert metrics["total_return"] == pytest.approx(expected_total_return)
    assert metrics["max_drawdown"] == pytest.approx(expected_max_drawdown)
    assert metrics["win_rate"] == pytest.approx(1.0)
    assert metrics["avg_win"] == pytest.approx(96.85005)
    assert metrics["avg_loss"] == pytest.approx(0.0)
    assert metrics["profit_factor"] is None
    assert metrics["payoff_ratio"] is None
    annualized_return = metrics["annualized_return"]
    total_return = metrics["total_return"]
    sharpe_ratio = metrics["sharpe_ratio"]
    assert isinstance(annualized_return, int | float)
    assert isinstance(total_return, int | float)
    assert isinstance(sharpe_ratio, int | float)
    assert annualized_return > total_return
    assert sharpe_ratio > 0
    assert metrics["max_drawdown_duration"] == pytest.approx(1.0)
    assert metrics["avg_holding_period_days"] == pytest.approx(1.0)


def test_trade_ledger_uses_calendar_cagr_daily_risk_metrics_and_session_drawdown_duration() -> (
    None
):
    ledger = TradeLedger()
    session_dates = [
        ("2024-01-05", 100.0),
        ("2024-01-08", 90.0),
        ("2024-01-09", 80.0),
        ("2024-01-10", 101.0),
    ]
    ledger.record_initial_capital(100.0)

    for session_date, equity in session_dates:
        timestamp = datetime.fromisoformat(f"{session_date}T00:00:00+00:00")
        ledger.record_daily_snapshot(
            session_date,
            AccountSnapshot(
                cash=equity,
                equity=equity,
                positions=[],
                timestamp=timestamp,
            ),
        )

    metrics = ledger.compute_metrics()

    assert metrics["total_return"] == pytest.approx(0.01)
    assert metrics["annualized_return"] == pytest.approx(1.0675703052211336)
    assert metrics["annualized_volatility"] == pytest.approx(3.37443753886536)
    assert metrics["sharpe_ratio"] == pytest.approx(1.279225535203751)
    assert metrics["max_drawdown"] == pytest.approx(0.2)
    assert metrics["max_drawdown_duration"] == 2


def test_trade_ledger_reports_zero_volatility_and_null_sharpe_for_flat_equity() -> None:
    ledger = TradeLedger()
    ledger.record_initial_capital(100.0)
    for session_date in ("2024-01-02", "2024-01-03", "2024-01-04"):
        ledger.record_daily_snapshot(
            session_date,
            AccountSnapshot(
                cash=100.0,
                equity=100.0,
                positions=[],
                timestamp=datetime.fromisoformat(f"{session_date}T00:00:00+00:00"),
            ),
        )

    metrics = ledger.compute_metrics()

    assert metrics["annualized_return"] == pytest.approx(0.0)
    assert metrics["annualized_volatility"] == pytest.approx(0.0)
    assert metrics["sharpe_ratio"] is None


def test_trade_ledger_uses_initial_capital_and_keeps_open_entries_out_of_trade_stats() -> (
    None
):
    ledger = TradeLedger()
    runtime_timestamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    initial_capital = 100_000.0
    ledger.record_initial_capital(initial_capital)
    first_post_decision_equity = 99_924.9750632725
    final_equity = 104_924.975
    open_position = Position(ticker="AAPL", shares=10, avg_cost=100.05)
    account_after_entry = AccountSnapshot(
        cash=98_924.4750632725,
        equity=first_post_decision_equity,
        positions=[open_position],
        timestamp=runtime_timestamp,
    )
    ledger.record_fill(
        fill=Fill(
            order_id="entry-order",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
            timestamp=runtime_timestamp,
        ),
        position=open_position,
        account=account_after_entry,
    )
    ledger.record_daily_snapshot("2026-01-02", account_after_entry)
    ledger.record_daily_snapshot(
        "2026-01-03",
        AccountSnapshot(
            cash=98_924.4750632725,
            equity=final_equity,
            positions=[open_position],
            timestamp=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
    )

    metrics = ledger.compute_metrics()
    initial_capital_return = final_equity / initial_capital - 1

    total_return = metrics["total_return"]
    assert isinstance(total_return, int | float)
    assert total_return * 100 == pytest.approx(4.924975)
    assert total_return == pytest.approx(initial_capital_return)
    assert metrics["number_of_trades"] == 0
    assert metrics["win_rate"] == 0.0


def test_trade_ledger_reconstructs_a_single_average_cost_episode() -> None:
    ledger = TradeLedger()
    session_id = "average-cost-episode"
    entry_one_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    entry_two_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    partial_exit_at = datetime(2024, 1, 4, tzinfo=timezone.utc)
    final_exit_at = datetime(2024, 1, 5, tzinfo=timezone.utc)

    entry_one_position = Position(
        ticker="AAPL", shares=10, avg_cost=100.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="entry-one",
            fill_price=100.0,
            fill_qty=10,
            fee=10.0,
            slippage=0.0,
            timestamp=entry_one_at,
            session_id=session_id,
        ),
        entry_one_position,
        AccountSnapshot(
            cash=98_990.0,
            equity=99_990.0,
            positions=[entry_one_position],
            timestamp=entry_one_at,
            session_id=session_id,
        ),
    )

    entry_two_position = Position(
        ticker="AAPL", shares=20, avg_cost=105.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="entry-two",
            fill_price=110.0,
            fill_qty=10,
            fee=11.0,
            slippage=0.0,
            timestamp=entry_two_at,
            session_id=session_id,
        ),
        entry_two_position,
        AccountSnapshot(
            cash=97_879.0,
            equity=100_079.0,
            positions=[entry_two_position],
            timestamp=entry_two_at,
            session_id=session_id,
        ),
    )

    partial_exit_position = Position(
        ticker="AAPL", shares=15, avg_cost=105.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="partial-exit",
            fill_price=120.0,
            fill_qty=5,
            fee=6.0,
            slippage=0.0,
            timestamp=partial_exit_at,
            session_id=session_id,
        ),
        partial_exit_position,
        AccountSnapshot(
            cash=98_473.0,
            equity=100_273.0,
            positions=[partial_exit_position],
            timestamp=partial_exit_at,
            session_id=session_id,
        ),
    )

    ledger.record_fill(
        Fill(
            order_id="final-exit",
            fill_price=90.0,
            fill_qty=15,
            fee=13.5,
            slippage=0.0,
            timestamp=final_exit_at,
            session_id=session_id,
        ),
        Position(ticker="AAPL", shares=0, avg_cost=0.0, session_id=session_id),
        AccountSnapshot(
            cash=99_809.5,
            equity=99_809.5,
            positions=[],
            timestamp=final_exit_at,
            session_id=session_id,
        ),
    )

    executions = ledger.to_executions_dataframe(session_id=session_id)
    closed_trades = ledger.to_closed_trades_dataframe(session_id=session_id)

    assert executions.loc[2, "realized_pnl"] == pytest.approx(63.75)
    assert len(closed_trades) == 1
    assert closed_trades.loc[0, "average_cost_basis"] == pytest.approx(106.05)
    assert closed_trades.loc[0, "net_realized_pnl"] == pytest.approx(-190.50)
    assert closed_trades.loc[0, "fees"] == pytest.approx(40.50)
    assert closed_trades.loc[0, "holding_period_trading_days"] == 3


def test_trade_ledger_counts_friday_to_monday_as_one_business_session_without_snapshots() -> (
    None
):
    ledger = TradeLedger()
    session_id = "friday-to-monday"
    entry_at = datetime(2024, 1, 5, tzinfo=timezone.utc)
    exit_at = datetime(2024, 1, 8, tzinfo=timezone.utc)
    entry_position = Position(
        ticker="AAPL", shares=10, avg_cost=100.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="friday-entry",
            fill_price=100.0,
            fill_qty=10,
            fee=0.0,
            slippage=0.0,
            timestamp=entry_at,
            session_id=session_id,
        ),
        entry_position,
        AccountSnapshot(
            cash=99_000.0,
            equity=100_000.0,
            positions=[entry_position],
            timestamp=entry_at,
            session_id=session_id,
        ),
    )
    ledger.record_fill(
        Fill(
            order_id="monday-exit",
            fill_price=110.0,
            fill_qty=10,
            fee=0.0,
            slippage=0.0,
            timestamp=exit_at,
            session_id=session_id,
        ),
        Position(ticker="AAPL", shares=0, avg_cost=0.0, session_id=session_id),
        AccountSnapshot(
            cash=100_100.0,
            equity=100_100.0,
            positions=[],
            timestamp=exit_at,
            session_id=session_id,
        ),
    )

    closed_trades = ledger.to_closed_trades_dataframe(session_id=session_id)

    assert len(closed_trades) == 1
    assert closed_trades.loc[0, "holding_period_trading_days"] == 1


def test_trade_ledger_does_not_double_charge_slippage_in_closed_trade_pnl() -> None:
    ledger = TradeLedger()
    session_id = "round-trip-cost-diagnostics"
    entry_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    exit_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    entry_position = Position(
        ticker="AAPL", shares=10, avg_cost=100.05, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="entry",
            fill_price=100.05,
            fill_qty=10,
            fee=1.0005,
            slippage=0.5,
            timestamp=entry_at,
            session_id=session_id,
        ),
        entry_position,
        AccountSnapshot(
            cash=98_998.4995,
            equity=99_998.4995,
            positions=[entry_position],
            timestamp=entry_at,
            session_id=session_id,
        ),
    )
    ledger.record_fill(
        Fill(
            order_id="exit",
            fill_price=109.945,
            fill_qty=10,
            fee=1.09945,
            slippage=0.55,
            timestamp=exit_at,
            session_id=session_id,
        ),
        Position(ticker="AAPL", shares=0, avg_cost=0.0, session_id=session_id),
        AccountSnapshot(
            cash=100_096.85005,
            equity=100_096.85005,
            positions=[],
            timestamp=exit_at,
            session_id=session_id,
        ),
    )

    closed_trades = ledger.to_closed_trades_dataframe(session_id=session_id)

    assert len(closed_trades) == 1
    assert closed_trades.loc[0, "net_realized_pnl"] == pytest.approx(96.85005)
    assert closed_trades.loc[0, "fees"] == pytest.approx(2.09995)
    assert closed_trades.loc[0, "slippage"] == pytest.approx(1.05)


def test_trade_ledger_keeps_closed_episodes_isolated_by_strategy() -> None:
    ledger = TradeLedger()
    session_id = "strategy-isolation"
    account_id = "shared-account"
    entry_a_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    entry_b_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    exit_b_at = datetime(2024, 1, 4, tzinfo=timezone.utc)

    position_a = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.0,
        strategy_id="strategy-a",
        account_id=account_id,
        session_id=session_id,
    )
    ledger.record_fill(
        Fill(
            order_id="a-entry",
            fill_price=100.0,
            fill_qty=10,
            fee=0.0,
            slippage=0.0,
            timestamp=entry_a_at,
            strategy_id="strategy-a",
            account_id=account_id,
            session_id=session_id,
        ),
        position_a,
        AccountSnapshot(
            cash=99_000.0,
            equity=100_000.0,
            positions=[position_a],
            timestamp=entry_a_at,
            strategy_id="strategy-a",
            account_id=account_id,
            session_id=session_id,
        ),
    )

    position_b = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=200.0,
        strategy_id="strategy-b",
        account_id=account_id,
        session_id=session_id,
    )
    ledger.record_fill(
        Fill(
            order_id="b-entry",
            fill_price=200.0,
            fill_qty=10,
            fee=0.0,
            slippage=0.0,
            timestamp=entry_b_at,
            strategy_id="strategy-b",
            account_id=account_id,
            session_id=session_id,
        ),
        position_b,
        AccountSnapshot(
            cash=98_000.0,
            equity=100_000.0,
            positions=[position_b],
            timestamp=entry_b_at,
            strategy_id="strategy-b",
            account_id=account_id,
            session_id=session_id,
        ),
    )

    ledger.record_fill(
        Fill(
            order_id="b-exit",
            fill_price=210.0,
            fill_qty=10,
            fee=0.0,
            slippage=0.0,
            timestamp=exit_b_at,
            strategy_id="strategy-b",
            account_id=account_id,
            session_id=session_id,
        ),
        Position(
            ticker="AAPL",
            shares=0,
            avg_cost=0.0,
            strategy_id="strategy-b",
            account_id=account_id,
            session_id=session_id,
        ),
        AccountSnapshot(
            cash=100_100.0,
            equity=100_100.0,
            positions=[],
            timestamp=exit_b_at,
            strategy_id="strategy-b",
            account_id=account_id,
            session_id=session_id,
        ),
    )

    closed_trades = ledger.to_closed_trades_dataframe(session_id=session_id)

    assert closed_trades["strategy_id"].tolist() == ["strategy-b"]
    assert closed_trades.loc[0, "net_realized_pnl"] == pytest.approx(100.0)


def test_trade_ledger_reports_open_average_cost_episode_without_closing_it() -> None:
    ledger = TradeLedger()
    session_id = "open-average-cost-episode"
    ledger.record_initial_capital(100_000.0, session_id=session_id)
    entry_one_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    entry_two_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    partial_exit_at = datetime(2024, 1, 4, tzinfo=timezone.utc)

    entry_one_position = Position(
        ticker="AAPL", shares=10, avg_cost=100.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="open-entry-one",
            fill_price=100.0,
            fill_qty=10,
            fee=10.0,
            slippage=0.0,
            timestamp=entry_one_at,
            session_id=session_id,
        ),
        entry_one_position,
        AccountSnapshot(
            cash=98_990.0,
            equity=99_990.0,
            positions=[entry_one_position],
            timestamp=entry_one_at,
            session_id=session_id,
        ),
    )
    entry_two_position = Position(
        ticker="AAPL", shares=20, avg_cost=105.0, session_id=session_id
    )
    ledger.record_fill(
        Fill(
            order_id="open-entry-two",
            fill_price=110.0,
            fill_qty=10,
            fee=11.0,
            slippage=0.0,
            timestamp=entry_two_at,
            session_id=session_id,
        ),
        entry_two_position,
        AccountSnapshot(
            cash=97_879.0,
            equity=100_079.0,
            positions=[entry_two_position],
            timestamp=entry_two_at,
            session_id=session_id,
        ),
    )
    open_position = Position(
        ticker="AAPL", shares=15, avg_cost=105.0, session_id=session_id
    )
    account_after_partial_exit = AccountSnapshot(
        cash=98_473.0,
        equity=100_123.0,
        positions=[open_position],
        timestamp=partial_exit_at,
        session_id=session_id,
    )
    ledger.record_fill(
        Fill(
            order_id="open-partial-exit",
            fill_price=120.0,
            fill_qty=5,
            fee=6.0,
            slippage=0.0,
            timestamp=partial_exit_at,
            session_id=session_id,
        ),
        open_position,
        account_after_partial_exit,
    )
    ledger.record_daily_snapshot("2024-01-04", account_after_partial_exit)

    executions = ledger.to_executions_dataframe(session_id=session_id)
    metrics = ledger.compute_metrics(session_id=session_id)
    closed_trades = ledger.to_closed_trades_dataframe(session_id=session_id)

    assert ledger.to_trades_dataframe(session_id=session_id).equals(executions)
    assert executions.loc[2, "avg_cost_after"] == pytest.approx(106.05)
    assert executions.loc[2, "realized_pnl"] == pytest.approx(63.75)
    assert metrics["realized_pnl"] == pytest.approx(63.75)
    assert metrics["unrealized_pnl"] == pytest.approx(59.25)
    assert metrics["net_pnl"] == pytest.approx(123.0)
    assert metrics["total_fees"] == pytest.approx(27.0)
    assert metrics["total_slippage"] == pytest.approx(0.0)
    assert metrics["turnover"] == pytest.approx(0.027)
    assert metrics["average_daily_gross_exposure"] == pytest.approx(1650.0 / 100123.0)
    assert metrics["number_of_closed_trades"] == 0
    assert closed_trades.empty


def test_trade_ledger_filters_a_reconstructed_exit_by_decision_id() -> None:
    ledger = TradeLedger()
    session_id = "decision-filtered-exit"
    strategy_id = "strategy-a"
    account_id = "account-a"
    entry_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    exit_at = datetime(2024, 1, 3, tzinfo=timezone.utc)
    entry_position = Position(
        ticker="AAPL",
        shares=10,
        avg_cost=100.0,
        strategy_id=strategy_id,
        account_id=account_id,
        session_id=session_id,
    )
    ledger.record_fill(
        Fill(
            order_id="entry",
            fill_price=100.0,
            fill_qty=10,
            fee=10.0,
            slippage=0.0,
            timestamp=entry_at,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
            decision_id="entry-decision",
        ),
        entry_position,
        AccountSnapshot(
            cash=8_990.0,
            equity=9_990.0,
            positions=[entry_position],
            timestamp=entry_at,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
        ),
    )
    ledger.record_fill(
        Fill(
            order_id="exit",
            fill_price=120.0,
            fill_qty=10,
            fee=10.0,
            slippage=0.0,
            timestamp=exit_at,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
            decision_id="exit-decision",
        ),
        Position(
            ticker="AAPL",
            shares=0.0,
            avg_cost=0.0,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
        ),
        AccountSnapshot(
            cash=10_180.0,
            equity=10_180.0,
            positions=[],
            timestamp=exit_at,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
        ),
    )

    executions = ledger.to_executions_dataframe(
        session_id=session_id,
        strategy_id=strategy_id,
        account_id=account_id,
        decision_id="exit-decision",
    )

    assert executions["order_id"].tolist() == ["exit"]
    assert executions.loc[0, "side"] == "SELL"
    assert executions.loc[0, "realized_pnl"] == pytest.approx(180.0)


def test_trade_ledger_rehydrates_initial_capital_by_session_strategy_and_account() -> (
    None
):
    backend = InMemoryLedgerBackend()
    session_id = "rehydrated-initial-capital"
    writer = TradeLedger(backend=backend)
    writer.record_initial_capital(
        100_000.0,
        **{
            "session_id": session_id,
            "strategy_id": "strategy-a",
            "account_id": "account-a",
        },
    )
    writer.record_initial_capital(
        200_000.0,
        **{
            "session_id": session_id,
            "strategy_id": "strategy-b",
            "account_id": "account-b",
        },
    )
    writer.record_daily_snapshot(
        "2024-01-02",
        AccountSnapshot(
            cash=98_924.975,
            equity=99_924.975,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            strategy_id="strategy-a",
            account_id="account-a",
            session_id=session_id,
        ),
    )
    writer.record_daily_snapshot(
        "2024-01-03",
        AccountSnapshot(
            cash=104_924.975,
            equity=104_924.975,
            timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc),
            strategy_id="strategy-a",
            account_id="account-a",
            session_id=session_id,
        ),
    )
    writer.record_daily_snapshot(
        "2024-01-02",
        AccountSnapshot(
            cash=199_000.0,
            equity=199_000.0,
            timestamp=datetime(2024, 1, 2, tzinfo=timezone.utc),
            strategy_id="strategy-b",
            account_id="account-b",
            session_id=session_id,
        ),
    )
    writer.record_daily_snapshot(
        "2024-01-03",
        AccountSnapshot(
            cash=210_000.0,
            equity=210_000.0,
            timestamp=datetime(2024, 1, 3, tzinfo=timezone.utc),
            strategy_id="strategy-b",
            account_id="account-b",
            session_id=session_id,
        ),
    )

    reader = TradeLedger(backend=backend)
    strategy_a_metrics = reader.compute_metrics(
        session_id=session_id,
        strategy_id="strategy-a",
        account_id="account-a",
    )
    strategy_b_metrics = reader.compute_metrics(
        session_id=session_id,
        strategy_id="strategy-b",
        account_id="account-b",
    )

    assert strategy_a_metrics["total_return"] == pytest.approx(0.04924975)
    assert strategy_b_metrics["total_return"] == pytest.approx(0.05)
