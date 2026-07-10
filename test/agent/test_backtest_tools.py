from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from agent.run_context import AgentRunContext, bind_agent_run_context
from agent.tools.backtest import SubmitBacktestDecisionTool
from agent.tools.financial import GetPriceTool
from broker.backtest_data import BacktestDataService
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from dataflow.store import MarketDataStore


def _context(
    tmp_path, *, as_of: str, close: float, strategy_id: str
) -> AgentRunContext:
    store = MarketDataStore(str(tmp_path / f"{strategy_id}.db"))
    store.upsert_ohlcv(
        "AAPL",
        [
            {
                "date": "2026-01-02",
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
                "volume": 10,
            },
            {
                "date": "2026-01-10",
                "open": 998,
                "high": 1000,
                "low": 997,
                "close": 999,
                "volume": 10,
            },
        ],
    )
    broker = MockBrokerEngine(BrokerConfig())
    broker.on_bar(
        {
            "AAPL": {
                "open": close - 1,
                "high": close + 1,
                "low": close - 2,
                "close": close,
            }
        }
    )
    return AgentRunContext(
        data_service=BacktestDataService(as_of=as_of, market_store=store),
        as_of=as_of,
        broker=broker,
        strategy_id=strategy_id,
        account_id=f"account-{strategy_id}",
        session_id=f"session-{strategy_id}",
        ticker="AAPL",
    )


def test_scoped_financial_tool_hides_future_sentinel_and_contexts_do_not_cross(
    tmp_path,
) -> None:
    first = _context(
        tmp_path,
        as_of="2026-01-03T00:00:00Z",
        close=100.0,
        strategy_id="first",
    )
    second = _context(
        tmp_path,
        as_of="2026-01-03T00:00:00Z",
        close=200.0,
        strategy_id="second",
    )

    def read_close(context: AgentRunContext) -> float:
        with bind_agent_run_context(context):
            payload = json.loads(GetPriceTool().execute("AAPL", days=30))
        return float(payload["latest"]["close"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        observed = list(executor.map(read_close, (first, second)))

    assert observed == [100.0, 200.0]


def test_submit_backtest_decision_uses_scoped_broker_identity(tmp_path) -> None:
    context = _context(
        tmp_path,
        as_of="2026-01-03T00:00:00Z",
        close=100.0,
        strategy_id="strategy-1",
    )

    with bind_agent_run_context(context):
        payload = json.loads(
            SubmitBacktestDecisionTool().execute(
                action="BUY",
                target_position_pct=50.0,
                confidence=0.8,
                rationale="seeded decision",
            )
        )

    fills = context.broker.get_fills(account_id=context.account_id)
    assert payload["status"] == "ok"
    assert fills[0].strategy_id == "strategy-1"
    assert fills[0].account_id == "account-strategy-1"
