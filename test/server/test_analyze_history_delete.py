from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from server import analysis_runs
from server.routes import analyze


def _use_history_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(analysis_runs, "HISTORY_DIR", tmp_path)


def _create_snapshot(session_id: str = "session-1") -> dict[str, object]:
    return analysis_runs.create_running_snapshot(
        session_id=session_id,
        ticker="AAPL",
        mode="standard",
        request_payload={"ticker": "AAPL", "mode": "standard"},
    )


def test_delete_snapshot_removes_file_and_filters_future_reappearances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_history_dir(tmp_path, monkeypatch)
    _create_snapshot()

    assert analysis_runs.delete_snapshot("session-1") is True

    assert not (tmp_path / "session-1.json").exists()
    assert analysis_runs.list_snapshots() == []

    (tmp_path / "session-1.json").write_text(
        json.dumps(
            {
                "session_id": "session-1",
                "ticker": "AAPL",
                "mode": "standard",
                "status": "completed",
                "created_at": "2026-07-06T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    assert analysis_runs.list_snapshots() == []
    with pytest.raises(FileNotFoundError):
        analysis_runs.load_snapshot("session-1")


def test_delete_history_route_persists_not_found_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_history_dir(tmp_path, monkeypatch)
    _create_snapshot()

    app = FastAPI()
    app.include_router(analyze.router, prefix="/api")
    client = TestClient(app)

    delete_response = client.delete("/api/analyze/history/session-1")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}

    list_response = client.get("/api/analyze/history")
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    get_response = client.get("/api/analyze/history/session-1")
    assert get_response.status_code == 404
