from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import hitl.executor
import quick_ask.orchestrator
from server.routes import analyze
from storage.store import ContextStore


def _parse_sse_events(text: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    current_event = "message"
    data_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("event: "):
            current_event = line[7:]
        elif line.startswith("data: "):
            data_lines.append(line[6:])
        elif line == "" and data_lines:
            events.append((current_event, json.loads("\n".join(data_lines))))
            current_event = "message"
            data_lines = []
    return events


def test_analyze_creates_pending_approval_without_hitl_executor(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ContextStore(tmp_path)

    class FakeAssistant:
        def stream(
            self,
            ticker: str,
            *,
            date: str,
            current_position_pct: float,
            session_id: str,
        ) -> Iterator[dict[str, dict[str, object]]]:
            del date, current_position_pct, session_id
            yield {
                "PM_agent": {
                    "PM_report": f"{ticker} decision\nconfidence: 0.4",
                    "Action": "BUY",
                    "Target_position_pct": 60.0,
                }
            }

    class FakeDataService:
        def get_news(self, ticker: str, window_days: int) -> list[dict[str, str]]:
            del ticker, window_days
            return []

    def fail_if_executor_is_called(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("HITL executor must not run during pending approval")

    async def noop_notify(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(quick_ask.orchestrator, "IntelliFin_Assistant", FakeAssistant)
    monkeypatch.setattr(analyze, "get_store", lambda: store, raising=False)
    monkeypatch.setattr(analyze, "_notify_analysis_completed", noop_notify)
    monkeypatch.setattr(analyze, "_notify_analysis_failed", noop_notify)
    monkeypatch.setattr("dataflow.service.DataService", FakeDataService)
    monkeypatch.setattr(
        hitl.executor.HITLExecutor,
        "process_approval_result",
        fail_if_executor_is_called,
    )
    monkeypatch.setattr("storage.store.get_store", lambda: store)

    app = FastAPI()
    app.include_router(analyze.router, prefix="/api")
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        json={
            "ticker": "AAPL",
            "strategy_id": "strategy-1",
            "account_id": "account-1",
            "decision_id": "decision-1",
            "current_position_pct": 0,
        },
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    result = next(payload for event, payload in events if event == "result")

    assert result["approval_required"] is True
    assert result["approval_status"] == "pending"
    assert result["decision_id"] == "decision-1"
    assert result["account_id"] == "account-1"
    assert result["triggered_rules"] == [
        "position_change",
        "low_confidence",
        "high_concentration",
    ]

    approvals = store.list_approvals("strategy-1")
    assert len(approvals) == 1
    assert approvals[0]["status"] == "pending"
    assert approvals[0]["decision_id"] == "decision-1"
    assert approvals[0]["account_id"] == "account-1"

    store.close()
