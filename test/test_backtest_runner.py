from __future__ import annotations

import pandas as pd

from broker.backtest_runner import BacktestRunner
from broker.config import BrokerConfig


class StubAgent:
    def run(self, *args, **kwargs):  # pragma: no cover - should stay unused here
        raise AssertionError("empty backtests should not invoke the agent")


def test_backtest_runner_returns_empty_exports_for_an_empty_price_window() -> None:
    runner = BacktestRunner(BrokerConfig(), agent=StubAgent())

    result = runner.run(
        ticker="AAPL",
        price_df=pd.DataFrame(columns=pd.Index(["Open", "High", "Low", "Close"])),
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert result.trades.empty
    assert result.portfolio.empty
    assert result.metrics["number_of_trades"] == 0
