from __future__ import annotations

from langchain_core.messages import AIMessage

from agentgraph.orchestrator import IntelliFin_Assistant
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.models import ExecutionReport, OrderStatus


def _stub_tool_nodes():
    return {
        "market_analyst": lambda state: {},
        "news_analyst": lambda state: {},
        "fundamentals_analyst": lambda state: {},
    }


def _stub_agent_nodes():
    return {
        "market_analyst": lambda state: {
            "market_analyst_messages": [AIMessage(content="market ready")],
            "market_report": "market ready",
        },
        "news_analyst": lambda state: {
            "news_analyst_messages": [AIMessage(content="news ready")],
            "news_report": "news ready",
        },
        "fundamentals_analyst": lambda state: {
            "fundamentals_analyst_messages": [AIMessage(content="fundamentals ready")],
            "fundamental_report": "fundamentals ready",
        },
        "risk_analyst": lambda state: {
            "risk_analyst_messages": [AIMessage(content="risk ready")],
            "risk_report": "risk ready",
        },
        "PM_agent": lambda state: {
            "PM_agent_messages": [AIMessage(content="pm ready")],
            "Action": "BUY",
            "Target_position_pct": 50.0,
            "PM_report": "Increase exposure on breakout.",
        },
    }


def test_orchestrator_runs_execution_node_after_pm_agent_when_broker_is_enabled() -> (
    None
):
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

    assistant = IntelliFin_Assistant(
        broker=broker,
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
    )

    result = assistant.run(
        "AAPL",
        date="2026-04-13T00:00:00Z",
        current_position_pct=0.0,
        execution_enabled=True,
        session_id="session-graph",
    )

    report = ExecutionReport.model_validate_json(result["execution_report"])

    assert report.order.status is OrderStatus.FILLED
    assert report.order.qty == 500.0
    assert report.session_id == "session-graph"


def test_orchestrator_keeps_pm_agent_terminal_when_no_broker_is_configured() -> None:
    assistant = IntelliFin_Assistant(
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
    )

    result = assistant.run(
        "AAPL",
        date="2026-04-13T00:00:00Z",
        current_position_pct=0.0,
        execution_enabled=True,
        session_id="session-no-broker",
    )

    assert result["Action"] == "BUY"
    assert "execution_report" not in result
