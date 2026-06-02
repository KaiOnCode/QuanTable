from __future__ import annotations

from collections.abc import Mapping

from langchain_core.messages import AIMessage

from agentgraph.orchestrator import IntelliFin_Assistant
from broker.config import BrokerConfig
from broker.engine import MockBrokerEngine
from broker.views import ExecutionReportView


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

    report = ExecutionReportView.model_validate_json(result["execution_report"])

    assert report.status == "executed"
    assert report.order is not None
    assert report.order.status == "executed"
    assert report.order.quantity == 500.0
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


def test_orchestrator_routes_through_hitl_approval_when_enabled() -> None:
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
    hitl_calls: list[str] = []

    def hitl_approval_node(state):
        hitl_calls.append(str(state["ticker"]))
        return {
            "approval_status": "modified",
            "modified_target_pct": 20.0,
        }

    assistant = IntelliFin_Assistant(
        broker=broker,
        enable_hitl=True,
        hitl_approval_node=hitl_approval_node,
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
    )

    result = assistant.run(
        "AAPL",
        date="2026-04-13T00:00:00Z",
        current_position_pct=0.0,
        execution_enabled=True,
        session_id="session-hitl",
    )

    report = ExecutionReportView.model_validate_json(result["execution_report"])

    assert hitl_calls == ["AAPL"]
    assert result["approval_status"] == "modified"
    assert result["modified_target_pct"] == 20.0
    assert report.status == "executed"
    assert report.order is not None
    assert report.order.status == "executed"
    assert report.order.quantity == 200.0


def test_orchestrator_passes_execution_complete_hook_to_execution_node() -> None:
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
    callback_payloads: list[tuple[ExecutionReportView, Mapping[str, object]]] = []

    def on_execution_complete(
        report: ExecutionReportView,
        state: Mapping[str, object],
    ) -> None:
        callback_payloads.append((report, state))

    assistant = IntelliFin_Assistant(
        broker=broker,
        on_execution_complete=on_execution_complete,
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
    )

    result = assistant.run(
        "AAPL",
        date="2026-04-13T00:00:00Z",
        current_position_pct=0.0,
        execution_enabled=True,
        session_id="session-hook",
    )

    report = ExecutionReportView.model_validate_json(result["execution_report"])

    assert len(callback_payloads) == 1
    callback_report, callback_state = callback_payloads[0]
    assert callback_report == report
    assert callback_report.status == "executed"
    assert callback_state["ticker"] == "AAPL"
    assert callback_state["session_id"] == "session-hook"


def test_orchestrator_run_accepts_as_of_and_identity_fields() -> None:
    captured_state: dict[str, object] = {}

    def execution_node(state):
        captured_state.update(state)
        return {"execution_report": "{}"}

    assistant = IntelliFin_Assistant(
        llm=object(),
        tool_nodes=_stub_tool_nodes(),
        agent_nodes=_stub_agent_nodes(),
        execution_node=execution_node,
        broker=MockBrokerEngine(BrokerConfig()),
    )

    assistant.run(
        "AAPL",
        date="2026-01-02T00:00:00Z",
        as_of="2026-01-02T00:00:00Z",
        current_position_pct=10.0,
        execution_enabled=True,
        strategy_id="strategy-1",
        account_id="account-1",
        session_id="session-1",
        decision_id="decision-1",
    )

    assert captured_state["date"] == "2026-01-02T00:00:00Z"
    assert captured_state["as_of"] == "2026-01-02T00:00:00Z"
    assert captured_state["strategy_id"] == "strategy-1"
    assert captured_state["account_id"] == "account-1"
    assert captured_state["session_id"] == "session-1"
    assert captured_state["decision_id"] == "decision-1"
