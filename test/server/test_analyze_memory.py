from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import quick_ask.orchestrator
from server import analysis_runs
from server.routes import analyze


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


def test_analyze_passes_memory_identity_and_returns_record_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAssistant:
        def stream(
            self,
            ticker: str,
            *,
            date: str,
            current_position_pct: float,
            strategy_id: str,
            session_id: str,
            memory_enabled: bool,
            account_id: str,
            decision_id: str,
        ) -> Iterator[dict[str, dict[str, object]]]:
            captured.update(
                {
                    "ticker": ticker,
                    "date": date,
                    "current_position_pct": current_position_pct,
                    "strategy_id": strategy_id,
                    "session_id": session_id,
                    "memory_enabled": memory_enabled,
                    "account_id": account_id,
                    "decision_id": decision_id,
                }
            )
            yield {
                "PM_agent": {
                    "PM_report": (
                        "方向: Neutral\n"
                        "时间范围: 1-3d\n"
                        "置信度: 0.8\n"
                        "一句话结论: 继续观察"
                    ),
                    "Action": "HOLD",
                    "Target_position_pct": 0.0,
                }
            }
            yield {"remember_memory": {"memory_record_id": "memory-1"}}

    class FakeDataService:
        def get_news(self, ticker: str, window_days: int) -> list[dict[str, str]]:
            del ticker, window_days
            return []

    async def noop_notify(*args: object, **kwargs: object) -> None:
        del args, kwargs

    monkeypatch.setattr(quick_ask.orchestrator, "IntelliFin_Assistant", FakeAssistant)
    monkeypatch.setattr(analysis_runs, "HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr("dataflow.service.DataService", FakeDataService)
    monkeypatch.setattr(analyze, "_notify_analysis_completed", noop_notify)
    monkeypatch.setattr(analyze, "_notify_analysis_failed", noop_notify)
    monkeypatch.setattr(analyze, "_load_settings", lambda: {"memory_enabled": False})

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
            "current_position_pct": 12.0,
        },
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    result = next(payload for event, payload in events if event == "result")

    assert captured["strategy_id"] == "strategy-1"
    assert captured["account_id"] == "account-1"
    assert captured["decision_id"] == "decision-1"
    assert captured["memory_enabled"] is False
    assert result["memory_record_id"] == "memory-1"
    assert result["memory_enabled"] is False
