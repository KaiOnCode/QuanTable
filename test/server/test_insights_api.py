from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from queue import Queue

import pytest
from fastapi.testclient import TestClient

from server.main import app
from storage.store import ContextStore


def _isolate_app_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    from server import main

    monkeypatch.setattr(main, "recover_interrupted_backtest_jobs", lambda: 0)
    monkeypatch.setattr(main, "recover_interrupted_report_jobs", lambda: 0)
    monkeypatch.setattr(main, "recover_interrupted_insight_generations", lambda: 0)


def test_insights_list_projects_non_finite_market_values_as_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a legacy-compatible brief contains a provider NaN value.
    from server.routes import insights

    store = ContextStore(tmp_path)
    store.save_daily_brief(
        {
            "id": "brief-nan",
            "title": "Market brief",
            "market_data": {
                "asia": {
                    "000001.SS": {
                        "name": "SSE Composite Index",
                        "price": math.nan,
                        "change_pct": math.nan,
                        "currency": "CNY",
                    }
                }
            },
            "generated_at": "2026-07-14T00:00:00Z",
        }
    )
    with sqlite3.connect(tmp_path / "insights.db") as db:
        db.execute(
            "UPDATE daily_briefs SET market_data_json = ? WHERE id = ?",
            (
                '{"asia":{"000001.SS":{"name":"SSE Composite Index",'
                '"price":NaN,"change_pct":NaN,"currency":"CNY"}}}',
                "brief-nan",
            ),
        )
        db.commit()
    monkeypatch.setattr(insights, "get_store", lambda: store)
    _isolate_app_recovery(monkeypatch)

    # When: the public list endpoint serializes the stored brief.
    with TestClient(app) as client:
        response = client.get("/api/insights?limit=20")

    # Then: the endpoint stays JSON-compliant and exposes unavailable values as null.
    assert response.status_code == 200
    market = response.json()["insights"][0]["market_data"]["asia"]["000001.SS"]
    assert market["price"] is None
    assert market["change_pct"] is None
    store.close()


def test_generation_job_survives_the_starting_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: generation emits durable progress before producing a persisted brief id.
    from server.routes import insights

    store = ContextStore(tmp_path)

    def fake_run(*, hours: int, progress_queue: Queue) -> dict[str, object]:
        assert hours == 24
        progress_queue.put(
            (
                "progress",
                {"stage": "market", "status": "done", "detail": "25 tickers fetched"},
            )
        )
        return {"id": "brief-complete"}

    monkeypatch.setattr(insights, "get_store", lambda: store)
    monkeypatch.setattr(insights, "_run_morning_brief", fake_run)
    _isolate_app_recovery(monkeypatch)

    # When: the client starts generation and later reconnects by job id.
    with TestClient(app) as client:
        generation_id = "b" * 32
        accepted = client.post(
            f"/api/insights/generate?hours=24&generation_id={generation_id}"
        )
        assert accepted.status_code == 202
        assert accepted.json()["id"] == generation_id

        body: dict[str, object] = {}
        for _ in range(100):
            status = client.get(f"/api/insights/generate/{generation_id}")
            assert status.status_code == 200
            body = status.json()
            if body["status"] in {"completed", "failed"}:
                break
            time.sleep(0.01)
        repeated = client.post(
            f"/api/insights/generate?hours=24&generation_id={generation_id}"
        )

    # Then: persisted state is terminal and contains the result link after reconnect.
    assert body["status"] == "completed"
    assert body["result_insight_id"] == "brief-complete"
    assert body["progress"] == {
        "market": {
            "stage": "market",
            "status": "done",
            "detail": "25 tickers fetched",
        }
    }
    assert repeated.status_code == 202
    assert repeated.json()["id"] == generation_id
    assert repeated.json()["result_insight_id"] == "brief-complete"
    store.close()
