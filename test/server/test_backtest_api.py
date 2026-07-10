from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.backtest_jobs import BacktestJobResponse, BacktestJobService, BacktestRequest
from broker.views import BacktestConfigView, BacktestResultView, PerformanceMetricsView
from server.routes import agent as agent_routes
from storage.store import ContextStore
from agent.backtest_jobs import ActiveBacktestJobRunner
from dataflow.store import MarketDataStore


class _CompletedRunner:
    def run(self, request: BacktestRequest) -> BacktestResultView:
        return BacktestResultView(
            config=BacktestConfigView(
                ticker=request.ticker,
                start_date=request.date_from.isoformat(),
                end_date=request.date_to.isoformat(),
                benchmark_symbol=request.benchmark,
                frequency=request.frequency,
                strategy_id=request.strategy_id,
            ),
            summary=PerformanceMetricsView(),
            series=[],
            trades=[],
        )


class _BlockingRunner(_CompletedRunner):
    def __init__(self) -> None:
        self.started = Event()
        self.finish = Event()

    def run(self, request: BacktestRequest) -> BacktestResultView:
        self.started.set()
        if not self.finish.wait(timeout=2):
            raise RuntimeError("runner timeout")
        return super().run(request)


class _FailingRunner:
    def run(self, request: BacktestRequest) -> BacktestResultView:
        del request
        raise RuntimeError("/private/prompt/token must not escape")


class _UnexpectedKeyErrorRunner:
    def __init__(self) -> None:
        self.finished = Event()

    def run(self, request: BacktestRequest) -> BacktestResultView:
        del request
        try:
            raise KeyError("/private/prompt/token must not escape")
        finally:
            self.finished.set()


@pytest.fixture
def backtest_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ContextStore, FastAPI]]:
    store = ContextStore(tmp_path)
    store.register_strategy({"id": "strategy-a", "name": "Strategy A"})
    service = BacktestJobService(store=store, runner=_CompletedRunner())
    monkeypatch.setattr(agent_routes, "get_store", lambda: store, raising=False)
    monkeypatch.setattr(
        agent_routes,
        "get_backtest_job_service",
        lambda: service,
        raising=False,
    )
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, store, app
    service.shutdown()
    store.close()


def test_create_poll_and_export_completed_backtest(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
) -> None:
    # Given: an ACTIVE route with a persisted strategy and an injected runner.
    client, _, _ = backtest_api
    request = {
        "strategy_id": "strategy-a",
        "ticker": "AAPL",
        "date_from": "2025-01-02",
        "date_to": "2025-01-10",
        "frequency": "weekly",
        "benchmark": "SPY",
    }

    # When: a client creates a backtest then polls its returned identifier.
    created = client.post("/api/agent/backtest", json=request)

    # Then: the API returns a durable accepted job whose canonical result can export CSV.
    assert created.status_code == 202
    body = BacktestJobResponse.model_validate(created.json())
    assert body.status in {"pending", "running", "completed"}
    backtest_id = body.backtest_id
    completed = _poll_until_terminal(client, backtest_id)
    assert completed.status == "completed"
    assert completed.result is not None
    assert completed.result.config.ticker == "AAPL"
    csv_response = client.get(f"/api/agent/backtest/{backtest_id}/trades.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-disposition"].startswith("attachment;")
    assert "ticker" in csv_response.text


def test_backtest_persists_running_then_failed_job_with_safe_error(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a blocking fake runner and a second fake runner which raises an unsafe error.
    client, store, _ = backtest_api
    blocking_runner = _BlockingRunner()
    blocking_service = BacktestJobService(store=store, runner=blocking_runner)
    monkeypatch.setattr(
        agent_routes, "get_backtest_job_service", lambda: blocking_service
    )
    request = _request_payload()

    # When: a job begins work before its runner is released.
    accepted = client.post("/api/agent/backtest", json=request)
    assert accepted.status_code == 202
    backtest_id = accepted.json()["backtest_id"]
    assert blocking_runner.started.wait(timeout=1)

    # Then: polling observes running, CSV rejects it, and a failed runner stores only safe error data.
    running = client.get(f"/api/agent/backtest/{backtest_id}")
    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert (
        client.get(f"/api/agent/backtest/{backtest_id}/trades.csv").status_code == 409
    )
    blocking_runner.finish.set()
    assert _poll_until_terminal(client, backtest_id).status == "completed"

    failing_service = BacktestJobService(store=store, runner=_FailingRunner())
    monkeypatch.setattr(
        agent_routes, "get_backtest_job_service", lambda: failing_service
    )
    failed = client.post("/api/agent/backtest", json=request)
    failed_job = _poll_until_terminal(client, failed.json()["backtest_id"])
    assert failed_job.status == "failed"
    assert failed_job.error is not None
    assert failed_job.error.code == "backtest_failed"
    assert "/private" not in failed.text
    blocking_service.shutdown()
    failing_service.shutdown()


def test_backtest_marks_unexpected_runner_key_error_as_safe_terminal_failure(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an injected runner exits with an unexpected KeyError after the API accepts work.
    client, store, _ = backtest_api
    runner = _UnexpectedKeyErrorRunner()
    service = BacktestJobService(store=store, runner=runner)
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the actual route persists and dispatches a backtest job through its executor.
    try:
        created = client.post("/api/agent/backtest", json=_request_payload())
        assert created.status_code == 202
        assert runner.finished.wait(timeout=1)
        terminal = client.get(f"/api/agent/backtest/{created.json()['backtest_id']}")

        # Then: every normal runner exception has a safe, persisted failed terminal envelope.
        assert terminal.status_code == 200
        assert terminal.json()["status"] == "failed"
        assert terminal.json()["error"] == {
            "code": "backtest_failed",
            "message": "Backtest failed",
        }
        assert "/private" not in terminal.text
        assert "prompt" not in terminal.text
        assert "token" not in terminal.text
    finally:
        service.shutdown()


def test_backtest_validates_identity_request_and_openapi_surface(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a mounted ACTIVE route with no configured LLM service.
    client, store, app = backtest_api
    unconfigured_service = BacktestJobService(
        store=store,
        runner=_CompletedRunner(),
        llm_available=False,
    )
    monkeypatch.setattr(
        agent_routes, "get_backtest_job_service", lambda: unconfigured_service
    )

    # When: callers submit missing strategy, invalid date, and unavailable LLM requests.
    unknown = client.post(
        "/api/agent/backtest",
        json={**_request_payload(), "strategy_id": "unknown"},
    )
    invalid_date = client.post(
        "/api/agent/backtest",
        json={
            **_request_payload(),
            "date_from": "2025-01-10",
            "date_to": "2025-01-02",
        },
    )
    unavailable = client.post("/api/agent/backtest", json=_request_payload())

    # Then: every failure has its intended stable HTTP surface and no shared route is registered.
    assert unknown.status_code == 404
    assert invalid_date.status_code == 422
    assert unavailable.status_code == 422
    paths = app.openapi()["paths"]
    assert {path for path in paths if path.startswith("/api/agent/backtest")} == {
        "/api/agent/backtest",
        "/api/agent/backtest/{backtest_id}",
        "/api/agent/backtest/{backtest_id}/trades.csv",
    }
    assert "/api/backtest" not in paths
    assert client.get("/api/agent/backtest/missing").status_code == 404
    unconfigured_service.shutdown()


def test_backtest_converts_empty_price_window_to_safe_failed_job(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a real cached-only production runner with no OHLCV rows in its isolated store.
    client, store, _ = backtest_api
    service = BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(MarketDataStore(tmp_path / "market.db")),
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: a valid job requests a price window that cannot be prepared from cache.
    created = client.post("/api/agent/backtest", json=_request_payload())

    # Then: the persisted terminal state is a safe failure rather than a response-thread error.
    failed = _poll_until_terminal(client, created.json()["backtest_id"])
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "backtest_failed"
    service.shutdown()


def test_backtest_recreates_completed_store_and_recovers_interrupted_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: one completed record and one running record in the same durable system database.
    store = ContextStore(tmp_path)
    completed_request = BacktestRequest.model_validate(_request_payload())
    completed_id = "completed-job"
    interrupted_id = "interrupted-job"
    store.create_backtest_job(completed_id, completed_request.model_dump_json())
    store.mark_backtest_job_running(completed_id)
    completed_result = _CompletedRunner().run(completed_request)
    store.complete_backtest_job(completed_id, completed_result.model_dump_json())
    store.create_backtest_job(interrupted_id, completed_request.model_dump_json())
    store.mark_backtest_job_running(interrupted_id)
    store.close()
    rebuilt_store = ContextStore(tmp_path)

    # When: the FastAPI lifespan invokes only the storage-level recovery function.
    from server import main

    monkeypatch.setattr(
        main,
        "recover_interrupted_backtest_jobs",
        rebuilt_store.recover_interrupted_backtest_jobs,
    )
    with TestClient(main.app):
        pass

    # Then: completed output survives reconstruction while pending/running work becomes typed interrupted failure.
    completed = rebuilt_store.get_backtest_job(completed_id)
    interrupted = rebuilt_store.get_backtest_job(interrupted_id)
    assert completed is not None
    assert completed.status == "completed"
    assert (
        BacktestResultView.model_validate_json(
            completed.result_json or "{}"
        ).config.ticker
        == "AAPL"
    )
    assert interrupted is not None
    assert interrupted.status == "failed"
    assert interrupted.error_json is not None
    assert "interrupted" in interrupted.error_json
    rebuilt_store.close()


def _poll_until_terminal(client: TestClient, backtest_id: str) -> BacktestJobResponse:
    for _ in range(100):
        response = client.get(f"/api/agent/backtest/{backtest_id}")
        assert response.status_code == 200
        payload = BacktestJobResponse.model_validate(response.json())
        if payload.status in {"completed", "failed"}:
            return payload
    raise AssertionError("backtest job did not reach a terminal status")


def _request_payload() -> dict[str, str]:
    return {
        "strategy_id": "strategy-a",
        "ticker": "AAPL",
        "date_from": date(2025, 1, 2).isoformat(),
        "date_to": date(2025, 1, 10).isoformat(),
        "frequency": "weekly",
        "benchmark": "SPY",
    }
