from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from agentgraph.orchestrator import IntelliFin_Assistant
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.ledger import TradeLedger


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    portfolio: pd.DataFrame
    metrics: dict[str, float | int]


class BacktestRunner:
    """Minimal backtest entry point reserved for fuller Phase 4 expansion."""

    def __init__(
        self,
        config: BrokerConfig,
        *,
        broker: MockBrokerEngine | None = None,
        ledger: TradeLedger | None = None,
        agent: Any | None = None,
    ) -> None:
        self.broker = broker or MockBrokerEngine(config)
        self.ledger = ledger or TradeLedger()
        self.agent = agent or IntelliFin_Assistant(broker=self.broker)

    def run(
        self,
        ticker: str,
        price_df: pd.DataFrame,
        start_date: str,
        end_date: str,
    ) -> BacktestResult:
        del ticker
        date_filtered = price_df.loc[start_date:end_date].copy()
        for _date, _row in date_filtered.iterrows():
            # Phase 4 only lands the public runner shape. The execution loop will
            # expand in a later slice once orchestration contracts settle.
            pass

        return BacktestResult(
            trades=self.ledger.to_trades_dataframe(),
            portfolio=self.ledger.to_portfolio_dataframe(),
            metrics=self.ledger.compute_metrics(),
        )
