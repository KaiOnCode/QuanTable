from __future__ import annotations

from typing import Any

from memory import MemoryRecord
from quick_ask import orchestrator


class FakeMemoryService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs

    def recall_records(self, ticker: str, market_context: dict[str, Any]):
        del ticker, market_context
        return [
            MemoryRecord(
                strategy_id="strategy-1",
                session_id="old-session",
                ticker="AAPL",
                episodic="prior BUY",
                trade_record={"action": "BUY"},
            )
        ]

    def recall_context(self, ticker: str, market_context: dict[str, Any]) -> str:
        del ticker, market_context
        return "memory context"

    def remember_decision(self, state: dict[str, Any]) -> str:
        assert state["strategy_id"] == "strategy-1"
        return "memory-1"


class FailingMemoryService(FakeMemoryService):
    def recall_records(self, ticker: str, market_context: dict[str, Any]):
        del ticker, market_context
        raise RuntimeError("recall failed")

    def recall_context(self, ticker: str, market_context: dict[str, Any]) -> str:
        del ticker, market_context
        raise RuntimeError("recall failed")


def test_initial_state_includes_strategy_and_memory_context(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "MemoryService", FakeMemoryService)

    state = orchestrator._build_initial_state(
        ticker="AAPL",
        date="2026-07-02T00:00:00Z",
        current_position_pct=10.0,
        strategy_id="strategy-1",
        session_id="session-1",
        memory_enabled=True,
        account_id="account-1",
        decision_id="decision-1",
    )

    assert state["strategy_id"] == "strategy-1"
    assert state["session_id"] == "session-1"
    assert state["account_id"] == "account-1"
    assert state["decision_id"] == "decision-1"
    assert state["memory_enabled"] is True
    assert state["memory_context"] == "memory context"
    assert len(state["relevant_memories"]) == 1


def test_memory_recall_failures_are_non_fatal(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "MemoryService", FailingMemoryService)

    state = orchestrator._build_initial_state(
        ticker="AAPL",
        date="2026-07-02T00:00:00Z",
        current_position_pct=10.0,
        strategy_id="strategy-1",
        session_id="session-1",
        memory_enabled=True,
        account_id=None,
        decision_id=None,
    )

    assert state["strategy_id"] == "strategy-1"
    assert state["relevant_memories"] == []
    assert state["memory_context"] == ""


def test_remember_node_returns_memory_record_id(monkeypatch) -> None:
    monkeypatch.setattr(orchestrator, "MemoryService", FakeMemoryService)

    state: Any = {
        "ticker": "AAPL",
        "strategy_id": "strategy-1",
        "memory_enabled": True,
        "PM_report": "report",
        "Action": "BUY",
    }

    result = orchestrator._remember_memory_node(state)

    assert result == {"memory_record_id": "memory-1"}
