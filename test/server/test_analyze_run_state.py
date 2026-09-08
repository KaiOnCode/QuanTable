from __future__ import annotations

import json
from pathlib import Path

from server import analysis_runs


def test_analysis_snapshot_starts_as_running(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analysis_runs, "HISTORY_DIR", tmp_path)

    snapshot = analysis_runs.create_running_snapshot(
        session_id="session-1",
        ticker="AAPL",
        mode="standard",
        request_payload={
            "ticker": "AAPL",
            "mode": "standard",
            "strategy_id": "default",
            "account_id": "default",
        },
    )

    saved = json.loads((tmp_path / "session-1.json").read_text(encoding="utf-8"))
    assert snapshot["status"] == "running"
    assert saved["status"] == "running"
    assert saved["result"] is None
    assert saved["progress_events"] == []


def test_analysis_snapshot_records_progress_and_result(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(analysis_runs, "HISTORY_DIR", tmp_path)
    analysis_runs.create_running_snapshot(
        session_id="session-1",
        ticker="AAPL",
        mode="standard",
        request_payload={"ticker": "AAPL", "mode": "standard"},
    )

    analysis_runs.record_progress(
        "session-1",
        {
            "agent": "market_analyst",
            "status": "completed",
            "report": "market report",
        },
    )
    analysis_runs.complete_snapshot(
        "session-1",
        {"session_id": "session-1", "action": "HOLD", "direction": "Neutral"},
    )

    saved = json.loads((tmp_path / "session-1.json").read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert saved["agent_reports"]["market_analyst"] == "market report"
    assert saved["result"]["action"] == "HOLD"


def test_analysis_snapshot_records_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(analysis_runs, "HISTORY_DIR", tmp_path)
    analysis_runs.create_running_snapshot(
        session_id="session-1",
        ticker="AAPL",
        mode="standard",
        request_payload={"ticker": "AAPL", "mode": "standard"},
    )

    analysis_runs.fail_snapshot("session-1", "provider timeout")

    saved = json.loads((tmp_path / "session-1.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
    assert saved["error"] == "provider timeout"
    assert saved["completed_at"]
