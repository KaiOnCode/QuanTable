from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.backtest_adapter import BacktestDecisionError
from agent.backtest_jobs import BacktestJobResponse, BacktestJobService, BacktestRequest
from agent.backtest_policy import BacktestRunSpec, freeze_backtest_run_spec
from broker.views import BacktestConfigView, BacktestResultView, PerformanceMetricsView
from server.routes import agent as agent_routes
from storage.store import ContextStore
from agent.backtest_jobs import ActiveBacktestJobRunner
from dataflow.store import MarketDataStore


class _CompletedRunner:
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        return BacktestResultView(
            config=BacktestConfigView(
                ticker=spec.ticker,
                start_date=spec.date_from.isoformat(),
                end_date=spec.date_to.isoformat(),
                benchmark_symbol=spec.benchmark,
                frequency=spec.frequency,
                strategy_id=spec.strategy_id,
            ),
            summary=PerformanceMetricsView(),
            series=[],
            trades=[],
        )


class _BlockingRunner(_CompletedRunner):
    def __init__(self) -> None:
        self.started = Event()
        self.finish = Event()

    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        self.started.set()
        if not self.finish.wait(timeout=2):
            raise RuntimeError("runner timeout")
        return super().run(spec)


class _FailingRunner:
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        del spec
        raise RuntimeError("/private/prompt/token must not escape")


class _UnexpectedKeyErrorRunner:
    def __init__(self) -> None:
        self.finished = Event()

    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        del spec
        try:
            raise KeyError("/private/prompt/token must not escape")
        finally:
            self.finished.set()


class _DecisionFailingRunner:
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        del spec
        raise BacktestDecisionError("provider detail must not escape")


class _CapturingRunner(_CompletedRunner):
    def __init__(self) -> None:
        self.spec: BacktestRunSpec | None = None
        self.finished = Event()

    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        self.spec = spec
        try:
            return super().run(spec)
        finally:
            self.finished.set()


class _NoOpHistoryLoader:
    def preload(self, ticker: str, date_from: str, date_to: str) -> None:
        del ticker, date_from, date_to


@pytest.fixture
def backtest_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, ContextStore, FastAPI]]:
    store = ContextStore(tmp_path)
    store.register_strategy(_eligible_strategy())
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


def test_backtest_public_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        BacktestRequest.model_validate({**_request_payload(), "unexpected": True})
    with pytest.raises(ValidationError):
        BacktestConfigView.model_validate({"unexpected": True})


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
        terminal = _poll_until_terminal(client, created.json()["backtest_id"])

        # Then: every normal runner exception has a safe, persisted failed terminal envelope.
        assert terminal.status == "failed"
        assert terminal.error is not None
        assert terminal.error.model_dump() == {
            "code": "backtest_failed",
            "message": "Backtest failed",
        }
        terminal_json = terminal.model_dump_json()
        assert "/private" not in terminal_json
        assert "prompt" not in terminal_json
        assert "token" not in terminal_json
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

    # When: callers submit missing strategy, invalid date, and a deterministic request.
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
    deterministic = client.post("/api/agent/backtest", json=_request_payload())

    # Then: every failure has its intended stable HTTP surface and no shared route is registered.
    assert unknown.status_code == 404
    assert invalid_date.status_code == 422
    assert deterministic.status_code == 202
    paths = app.openapi()["paths"]
    assert {path for path in paths if path.startswith("/api/agent/backtest")} == {
        "/api/agent/backtest",
        "/api/agent/backtest/{backtest_id}",
        "/api/agent/backtest/{backtest_id}/trades.csv",
    }
    assert "/api/backtest" not in paths
    assert client.get("/api/agent/backtest/missing").status_code == 404
    unconfigured_service.shutdown()


def test_backtest_freezes_and_persists_strategy_before_enqueue(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
) -> None:
    _, store, _ = backtest_api
    runner = _CapturingRunner()
    service = BacktestJobService(store=store, runner=runner)

    created = service.create(BacktestRequest.model_validate(_request_payload()))
    store.register_strategy(
        {
            **_eligible_strategy(),
            "name": "Mutated after enqueue",
            "initial_capital": 999_999,
            "quant_params": {
                "lookback_bars": 2,
                "entry_threshold": 0,
                "exit_threshold": 0,
                "target_position_pct": 1,
            },
        }
    )
    registry = store._system_db()
    registry.execute("DELETE FROM strategies WHERE id = ?", ("strategy-a",))
    registry.commit()

    assert runner.finished.wait(timeout=1)
    assert runner.spec is not None
    assert runner.spec.strategy_name == "Strategy A"
    assert runner.spec.broker_config.initial_cash == 100_000
    assert runner.spec.policy.required_lookback_bars == 20
    assert store.get_strategy("strategy-a") is None
    persisted = store.get_backtest_job(created.backtest_id)
    assert persisted is not None
    assert persisted.run_spec_json == runner.spec.model_dump_json()
    service.shutdown()


@pytest.mark.parametrize(
    ("strategy", "request_overrides", "status", "code"),
    [
        ({"status": "paused"}, {}, 422, "strategy_inactive"),
        ({"tickers": []}, {}, 422, "strategy_config_invalid"),
        ({}, {"ticker": "MSFT"}, 422, "ticker_not_allowed"),
        (
            {"quant_strategy_name": None, "quant_params": {}},
            {},
            422,
            "strategy_not_backtestable",
        ),
        ({"type": "hitl"}, {}, 422, "strategy_type_unsupported"),
    ],
)
def test_backtest_route_maps_eligibility_errors(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    strategy: dict[str, object],
    request_overrides: dict[str, object],
    status: int,
    code: str,
) -> None:
    client, store, _ = backtest_api
    store.register_strategy({**_eligible_strategy(), **strategy})

    response = client.post(
        "/api/agent/backtest", json={**_request_payload(), **request_overrides}
    )

    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


def test_agent_experiment_has_actionable_unavailable_provider_response(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = backtest_api
    store.register_strategy(
        {
            **_eligible_strategy(),
            "type": "agent",
            "agent_model": "deepseek-chat",
            "quant_strategy_name": None,
            "quant_params": {},
        }
    )
    service = BacktestJobService(
        store=store, runner=_CompletedRunner(), llm_available=False
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    response = client.post(
        "/api/agent/backtest",
        json={**_request_payload(), "mode": "agent_experiment"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_unavailable"
    service.shutdown()


def test_backtest_converts_empty_price_window_to_safe_failed_job(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a real cached-only production runner with no OHLCV rows in its isolated store.
    client, store, _ = backtest_api
    service = BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(
            MarketDataStore(tmp_path / "market.db"),
            history_loader=_NoOpHistoryLoader(),
        ),
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: a valid job requests a price window that cannot be prepared from cache.
    created = client.post("/api/agent/backtest", json=_request_payload())

    # Then: the persisted terminal state is a safe failure rather than a response-thread error.
    failed = _poll_until_terminal(client, created.json()["backtest_id"])
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "market_data_unavailable"
    assert failed.error.message == (
        "Historical market data is unavailable for AAPL and SPY in the requested window."
    )
    service.shutdown()


def test_backtest_converts_agent_decision_failure_to_safe_typed_error(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an agent runner failure whose provider detail must remain private.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_DecisionFailingRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the persisted worker reaches the decision boundary.
    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    # Then: callers receive a stable actionable category without provider details.
    assert failed.error is not None
    assert failed.error.code == "agent_failed"
    assert failed.error.message == (
        "The backtest agent could not produce a valid structured decision."
    )
    assert "provider detail" not in failed.model_dump_json()
    service.shutdown()


def test_backtest_recreates_completed_store_and_recovers_interrupted_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: one completed record and one running record in the same durable system database.
    store = ContextStore(tmp_path)
    store.register_strategy(_eligible_strategy())
    completed_request = BacktestRequest.model_validate(_request_payload())
    completed_id = "completed-job"
    interrupted_id = "interrupted-job"
    store.create_backtest_job(completed_id, completed_request.model_dump_json())
    store.mark_backtest_job_running(completed_id)
    strategy = store.get_strategy("strategy-a")
    assert strategy is not None
    completed_result = _CompletedRunner().run(
        freeze_backtest_run_spec(completed_request, strategy)
    )
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


def _eligible_strategy() -> dict[str, object]:
    return {
        "id": "strategy-a",
        "name": "Strategy A",
        "type": "quant",
        "status": "active",
        "tickers": ["AAPL"],
        "quant_strategy_name": "momentum",
        "quant_params": {
            "lookback_bars": 20,
            "entry_threshold": 0.05,
            "exit_threshold": -0.02,
            "target_position_pct": 50,
        },
        "execution_frequency": "daily",
        "initial_capital": 100_000,
        "max_position_pct": 100,
        "max_drawdown_pct": 20,
    }
