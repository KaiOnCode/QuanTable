from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

import streamlit_app
from agentgraph.execution_node import create_execution_node
from broker.backtest_runner import BacktestResult, BacktestRunner
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from streamlit_app import (
    Backtester,
    BacktestMetricCard,
    build_backtest_dashboard_data,
    render_backtest_dashboard,
)


def _sample_backtest_result() -> BacktestResult:
    return BacktestResult(
        trades=pd.DataFrame(
            [
                {
                    "order_id": "order-1",
                    "timestamp": pd.Timestamp("2026-01-02T00:00:00Z"),
                    "ticker": "AAPL",
                    "side": "BUY",
                    "quantity": 500.0,
                    "price": 100.05,
                    "fee": 50.025,
                    "slippage": 25.0,
                    "trade_value": 50_025.0,
                    "realized_pnl": -75.025,
                    "cash_after": 49_924.975,
                    "equity_after": 99_924.975,
                    "shares_after": 500.0,
                    "avg_cost_after": 100.05,
                    "session_id": "session-1",
                }
            ]
        ),
        portfolio=pd.DataFrame(
            [
                {
                    "date": "2026-01-02",
                    "timestamp": pd.Timestamp("2026-01-02T00:00:00Z"),
                    "cash": 49_924.975,
                    "equity": 99_924.975,
                    "strategy_equity": 99_924.975,
                    "close": 100.0,
                    "benchmark_equity": 100_000.0,
                    "strategy_drawdown": 0.0,
                    "benchmark_drawdown": 0.0,
                    "position_value": 50_000.0,
                    "position_count": 1,
                    "session_id": "session-1",
                },
                {
                    "date": "2026-01-03",
                    "timestamp": pd.Timestamp("2026-01-03T00:00:00Z"),
                    "cash": 49_924.975,
                    "equity": 104_924.975,
                    "strategy_equity": 104_924.975,
                    "close": 110.0,
                    "benchmark_equity": 110_000.0,
                    "strategy_drawdown": 0.0,
                    "benchmark_drawdown": 0.0,
                    "position_value": 55_000.0,
                    "position_count": 1,
                    "session_id": "session-1",
                },
            ]
        ),
        metrics={
            "total_return": 0.05,
            "max_drawdown": 0.02,
            "sharpe_ratio": 1.25,
            "win_rate": 0.5,
            "number_of_trades": 1,
        },
    )


def _figure_trace_names(figure: go.Figure) -> list[str]:
    payload = figure.to_dict()
    return [str(trace.get("name", "")) for trace in payload.get("data", [])]


class _FakeColumn:
    def __init__(self, sink: "_FakeStreamlit") -> None:
        self._sink = sink

    def metric(self, label: str, value: str) -> None:
        self._sink.metrics.append((label, value))


class _FakeTab:
    def __enter__(self) -> "_FakeTab":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


class _FakeStreamlit:
    def __init__(self) -> None:
        self.subheaders: list[str] = []
        self.captions: list[str] = []
        self.metrics: list[tuple[str, str]] = []
        self.dataframes: list[pd.DataFrame] = []
        self.figures: list[go.Figure] = []
        self.tabs_rendered: list[str] = []

    def subheader(self, text: str) -> None:
        self.subheaders.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def columns(self, count: int) -> list[_FakeColumn]:
        return [_FakeColumn(self) for _ in range(count)]

    def tabs(self, labels: list[str]) -> list[_FakeTab]:
        self.tabs_rendered = list(labels)
        return [_FakeTab() for _ in labels]

    def dataframe(self, dataframe: pd.DataFrame, *, use_container_width: bool) -> None:
        assert use_container_width is True
        self.dataframes.append(dataframe.copy())

    def plotly_chart(self, figure: go.Figure, *, use_container_width: bool) -> None:
        assert use_container_width is True
        self.figures.append(figure)


class _BuyThenHoldExecutionAgent:
    def __init__(self, broker: MockBrokerEngine) -> None:
        self._execution_node = create_execution_node(broker)
        self._calls = 0

    def run(
        self,
        ticker: str,
        date: str | None = None,
        current_position_pct: float = 0.0,
        *,
        as_of: str | None = None,
        execution_enabled: bool = False,
        strategy_id: str = "",
        account_id: str = "default",
        session_id: str = "",
    ) -> dict[str, object]:
        del date, as_of, current_position_pct
        self._calls += 1
        if self._calls == 1:
            return self._execution_node(
                {
                    "ticker": ticker,
                    "Action": "BUY",
                    "Target_position_pct": 50.0,
                    "PM_report": "Open a half-sized position.",
                    "execution_enabled": execution_enabled,
                    "strategy_id": strategy_id,
                    "account_id": account_id,
                    "session_id": session_id,
                }
            )
        return {"execution_report": "HOLD — 无需执行"}


def test_build_backtest_dashboard_data_formats_tables_and_metric_cards() -> None:
    result = _sample_backtest_result()

    dashboard = build_backtest_dashboard_data(result)

    assert list(dashboard.trades_table.columns) == [
        "Time",
        "Ticker",
        "Side",
        "Quantity",
        "Price",
        "Fee",
        "Slippage",
        "Realized PnL",
    ]
    assert dashboard.trades_table.to_dict("records") == [
        {
            "Time": "2026-01-02 00:00:00",
            "Ticker": "AAPL",
            "Side": "BUY",
            "Quantity": 500.0,
            "Price": 100.05,
            "Fee": 50.025,
            "Slippage": 25.0,
            "Realized PnL": -75.025,
        }
    ]
    assert list(dashboard.portfolio_table.columns) == [
        "Date",
        "Time",
        "Cash",
        "Equity",
        "Position Value",
        "Open Positions",
    ]
    assert dashboard.metric_cards == [
        BacktestMetricCard(label="Total Return", value="5.00%"),
        BacktestMetricCard(label="Max Drawdown", value="2.00%"),
        BacktestMetricCard(label="Sharpe Ratio", value="1.25"),
        BacktestMetricCard(label="Win Rate", value="50.00%"),
        BacktestMetricCard(label="Trades", value="1"),
    ]
    assert list(dashboard.performance_table.columns) == [
        "Date",
        "Strategy Equity",
        "Benchmark Equity",
        "Strategy Drawdown",
        "Benchmark Drawdown",
    ]
    assert dashboard.performance_table.to_dict("records") == [
        {
            "Date": "2026-01-02",
            "Strategy Equity": 99_924.975,
            "Benchmark Equity": 100_000.0,
            "Strategy Drawdown": 0.0,
            "Benchmark Drawdown": 0.0,
        },
        {
            "Date": "2026-01-03",
            "Strategy Equity": 104_924.975,
            "Benchmark Equity": 110_000.0,
            "Strategy Drawdown": 0.0,
            "Benchmark Drawdown": 0.0,
        },
    ]


def test_render_backtest_dashboard_sends_metric_cards_and_tables_to_streamlit() -> None:
    fake_streamlit = _FakeStreamlit()
    dashboard = build_backtest_dashboard_data(_sample_backtest_result())

    render_backtest_dashboard(dashboard, streamlit_api=fake_streamlit)

    assert fake_streamlit.subheaders == [
        "📒 Broker Backtest",
        "Overview",
        "Performance",
        "Trade Log",
        "Portfolio Timeline",
    ]
    assert fake_streamlit.tabs_rendered == [
        "Overview",
        "Performance",
        "Trades",
        "Portfolio",
    ]
    assert fake_streamlit.captions == [
        "Strategy KPIs",
        "Strategy vs Benchmark and drawdown over the backtest window.",
        "Executed fills exported from the trade ledger.",
        "Daily account snapshots exported from the trade ledger.",
    ]
    assert fake_streamlit.metrics == [
        ("Total Return", "5.00%"),
        ("Max Drawdown", "2.00%"),
        ("Sharpe Ratio", "1.25"),
        ("Win Rate", "50.00%"),
        ("Trades", "1"),
    ]
    assert len(fake_streamlit.dataframes) == 2
    assert len(fake_streamlit.figures) == 2
    assert _figure_trace_names(fake_streamlit.figures[0]) == [
        "Strategy Equity",
        "Benchmark Equity",
    ]
    assert _figure_trace_names(fake_streamlit.figures[1]) == [
        "Strategy Drawdown",
        "Benchmark Drawdown",
    ]
    assert list(fake_streamlit.dataframes[0].columns) == [
        "Time",
        "Ticker",
        "Side",
        "Quantity",
        "Price",
        "Fee",
        "Slippage",
        "Realized PnL",
    ]
    assert list(fake_streamlit.dataframes[1].columns) == [
        "Date",
        "Time",
        "Cash",
        "Equity",
        "Position Value",
        "Open Positions",
    ]


def test_backtester_run_execution_backtest_builds_runner_inputs(
    monkeypatch,
) -> None:
    expected_result = _sample_backtest_result()

    @dataclass
    class _CapturedRunnerCall:
        config: BrokerConfig | None = None
        ticker: str = ""
        price_df: pd.DataFrame | None = None
        start_date: str = ""
        end_date: str = ""

    captured = _CapturedRunnerCall()

    class _StubRunner:
        def __init__(self, config: BrokerConfig) -> None:
            captured.config = config

        def run(
            self,
            ticker: str,
            price_df: pd.DataFrame,
            start_date: str,
            end_date: str,
        ) -> BacktestResult:
            captured.ticker = ticker
            captured.price_df = price_df.copy()
            captured.start_date = start_date
            captured.end_date = end_date
            return expected_result

    def _fake_prices(
        ticker: str,
        lookback_days: int,
        end_date: str | None = None,
    ) -> dict[str, object]:
        assert ticker == "AAPL"
        assert lookback_days == 2
        assert end_date == "2026-01-02T00:00:00Z"
        return {
            "ticker": "AAPL",
            "rows": [
                {
                    "ts": "2026-01-01T00:00:00Z",
                    "o": 99.0,
                    "h": 101.0,
                    "l": 98.0,
                    "c": 100.0,
                },
                {
                    "ts": "2026-01-02T00:00:00Z",
                    "o": 100.0,
                    "h": 102.0,
                    "l": 99.0,
                    "c": 101.0,
                },
            ],
        }

    monkeypatch.setattr(streamlit_app, "df_get_prices", _fake_prices)
    backtester = Backtester(runner_factory=_StubRunner)

    result = backtester.run_execution_backtest(
        ticker="AAPL",
        end_date="2026-01-02",
        lookback_days=2,
        initial_cash=123_456.0,
        commission_rate=0.002,
        slippage_rate=0.003,
    )

    assert result is expected_result
    config = captured.config
    assert config is not None
    assert config.initial_cash == 123_456.0
    assert config.commission_rate == 0.002
    assert config.slippage_rate == 0.003
    assert captured.ticker == "AAPL"
    assert captured.start_date == "2026-01-01"
    assert captured.end_date == "2026-01-02"
    price_df = captured.price_df
    assert price_df is not None
    assert list(price_df.columns) == ["Open", "High", "Low", "Close"]
    assert [str(value)[:10] for value in price_df.index] == ["2026-01-01", "2026-01-02"]


def test_backtester_run_execution_backtest_filters_to_explicit_date_range(
    monkeypatch,
) -> None:
    expected_result = _sample_backtest_result()

    @dataclass
    class _CapturedRunnerCall:
        ticker: str = ""
        price_df: pd.DataFrame | None = None
        start_date: str = ""
        end_date: str = ""

    captured = _CapturedRunnerCall()

    class _StubRunner:
        def __init__(self, config: BrokerConfig) -> None:
            del config

        def run(
            self,
            ticker: str,
            price_df: pd.DataFrame,
            start_date: str,
            end_date: str,
        ) -> BacktestResult:
            captured.ticker = ticker
            captured.price_df = price_df.copy()
            captured.start_date = start_date
            captured.end_date = end_date
            return expected_result

    def _fake_prices(
        ticker: str,
        lookback_days: int,
        end_date: str | None = None,
    ) -> dict[str, object]:
        assert ticker == "AAPL"
        assert lookback_days >= 3
        assert end_date == "2026-01-04T00:00:00Z"
        return {
            "ticker": "AAPL",
            "rows": [
                {
                    "ts": "2026-01-01T00:00:00Z",
                    "o": 98.0,
                    "h": 100.0,
                    "l": 97.0,
                    "c": 99.0,
                },
                {
                    "ts": "2026-01-02T00:00:00Z",
                    "o": 99.0,
                    "h": 101.0,
                    "l": 98.0,
                    "c": 100.0,
                },
                {
                    "ts": "2026-01-03T00:00:00Z",
                    "o": 100.0,
                    "h": 102.0,
                    "l": 99.0,
                    "c": 101.0,
                },
                {
                    "ts": "2026-01-04T00:00:00Z",
                    "o": 101.0,
                    "h": 103.0,
                    "l": 100.0,
                    "c": 102.0,
                },
            ],
        }

    monkeypatch.setattr(streamlit_app, "df_get_prices", _fake_prices)
    backtester = Backtester(runner_factory=_StubRunner)

    result = backtester.run_execution_backtest(
        ticker="AAPL",
        start_date="2026-01-02",
        end_date="2026-01-04",
    )

    assert result is expected_result
    assert captured.ticker == "AAPL"
    assert captured.start_date == "2026-01-02"
    assert captured.end_date == "2026-01-04"
    assert captured.price_df is not None
    assert [str(value)[:10] for value in captured.price_df.index] == [
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    ]


def test_multibar_backtest_result_renders_dashboard_for_explicit_date_range() -> None:
    broker = MockBrokerEngine(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        )
    )
    runner = BacktestRunner(
        BrokerConfig(
            initial_cash=100_000.0,
            commission_rate=0.0,
            slippage_rate=0.0,
        ),
        broker=broker,
        agent=_BuyThenHoldExecutionAgent(broker),
    )
    price_df = pd.DataFrame(
        [
            {"Open": 98.0, "High": 100.0, "Low": 97.0, "Close": 99.0},
            {"Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0},
            {"Open": 100.0, "High": 102.0, "Low": 99.0, "Close": 101.0},
            {"Open": 101.0, "High": 103.0, "Low": 100.0, "Close": 102.0},
        ],
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]),
    )

    result = runner.run(
        ticker="AAPL",
        price_df=price_df,
        benchmark_df=price_df.copy(),
        start_date="2026-01-02",
        end_date="2026-01-04",
    )
    dashboard = build_backtest_dashboard_data(result)
    fake_streamlit = _FakeStreamlit()

    render_backtest_dashboard(dashboard, streamlit_api=fake_streamlit)

    assert list(dashboard.performance_table["Date"]) == [
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    ]
    assert fake_streamlit.tabs_rendered == [
        "Overview",
        "Performance",
        "Trades",
        "Portfolio",
    ]
    assert len(fake_streamlit.figures) == 2
    assert len(fake_streamlit.dataframes) == 2
