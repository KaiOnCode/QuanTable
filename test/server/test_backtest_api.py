from __future__ import annotations

from collections.abc import Iterator
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Event

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.backtest_adapter import BacktestDecisionError
from agent.backtest_jobs import (
    BacktestJobResponse,
    BacktestJobService,
    BacktestReplayUnavailableError,
    BacktestRequest,
    _canonical_input_snapshot,
    default_backtest_job_service,
)
from agent.backtest_policy import (
    BacktestMode,
    BacktestRunSpec,
    StrategyEligibilityError,
    freeze_backtest_run_spec,
)
from broker.backtest_runner import BacktestRunObserver
from broker.views import (
    BacktestConfigView,
    BacktestDecisionView,
    BacktestProgressView,
    BacktestResultView,
    PerformanceMetricsView,
)
from server.routes import agent as agent_routes
from storage.store import (
    BacktestDecisionEvidence,
    BacktestInputSnapshotContent,
    ContextStore,
)
from agent.backtest_jobs import ActiveBacktestJobRunner
from broker.backtest_data import BacktestDataError
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

    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target = pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.0,
                    "Volume": 1000.0,
                }
            ],
            index=pd.to_datetime([spec.date_from.isoformat()]),
        )
        observer.bind_input_snapshot(target, target)
        return self.run(spec)


class _FeatureHashRunner(_CompletedRunner):
    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target = pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.0,
                    "Volume": 1000.0,
                }
            ],
            index=pd.to_datetime([spec.date_from.isoformat()]),
        )
        signal_date = f"{spec.date_from.isoformat()}T00:00:00Z"
        observer.bind_input_snapshot(target, target)
        observer.begin_decision(1, signal_date, spec.policy_hash)
        observer.record_decision(
            BacktestDecisionView(
                sequence=1,
                signal_date=signal_date,
                status="completed",
                attempts=2,
                target_position_pct=40.0,
                confidence=0.8,
                feature_hash="f" * 64,
                policy_hash=spec.policy_hash,
            )
        )
        return self.run(spec)


class _ExecutionEvidenceRunner(_CompletedRunner):
    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target = pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.0,
                    "Volume": 1000.0,
                }
            ],
            index=pd.to_datetime([spec.date_from.isoformat()]),
        )
        signal_date = f"{spec.date_from.isoformat()}T00:00:00Z"
        observer.bind_input_snapshot(target, target)
        observer.begin_decision(1, signal_date, spec.policy_hash)
        observer.record_decision(
            BacktestDecisionView(
                sequence=1,
                signal_date=signal_date,
                status="completed",
                target_position_pct=40.0,
                confidence=0.8,
                feature_hash="f" * 64,
                policy_hash=spec.policy_hash,
            )
        )
        observer.record_execution(1, signal_date)
        return self.run(spec)


class _UnobservableCompletedRunner:
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        return _CompletedRunner().run(spec)


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
        raise BacktestDecisionError(
            code="agent_failed",
            stage="agent_execution",
            decision_date=f"{spec.date_from.isoformat()}T00:00:00Z",
            attempt=1,
        )


class _ProviderFailingRunner:
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        raise BacktestDecisionError(
            code="provider_failed",
            stage="provider",
            decision_date=f"{spec.date_from.isoformat()}T00:00:00Z",
            attempt=1,
        )


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


class _NthDecisionFailingObservabilityRunner:
    def __init__(self, unsafe_error_metadata: bool = False) -> None:
        self._unsafe_error_metadata = unsafe_error_metadata

    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target = pd.DataFrame(
            [
                {
                    "Open": 100.0,
                    "High": 101.0,
                    "Low": 99.0,
                    "Close": 100.0,
                    "Volume": 1000.0,
                }
            ],
            index=pd.to_datetime(["2025-01-02"]),
        )
        benchmark = target * 2.0
        provider_sentinel = "provider-secret://do-not-persist"
        observer.bind_input_snapshot(target, benchmark)
        observer.record_progress(
            BacktestProgressView(
                bars_total=2,
                bars_processed=2,
                decisions_total=2,
                decisions_eligible=2,
                decisions_completed=1,
                current_decision_date=provider_sentinel,
            )
        )
        observer.begin_decision(1, "2025-01-02T00:00:00Z", provider_sentinel)
        observer.record_decision(
            BacktestDecisionView(
                sequence=1,
                signal_date=provider_sentinel,
                execution_date=provider_sentinel,
                status="completed",
                attempts=1,
                target_position_pct=50.0,
                confidence=0.9,
                feature_hash=provider_sentinel,
                policy_hash=provider_sentinel,
                error_code=provider_sentinel,
                error_stage=provider_sentinel,
            )
        )
        observer.begin_decision(2, "2025-01-03T00:00:00Z", provider_sentinel)
        failure = BacktestDecisionError(
            code="decision_schema_invalid",
            stage="structured_output",
            decision_date="2025-01-03T00:00:00Z",
            attempt=2,
        )
        if self._unsafe_error_metadata:
            setattr(failure, "stage", provider_sentinel)
            setattr(failure, "decision_date", provider_sentinel)
            setattr(failure, "attempt", 0)
        raise failure from RuntimeError(provider_sentinel)


class _ReplayMustNotRunRunner:
    def __init__(self) -> None:
        self.called = False

    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        del spec
        self.called = True
        raise AssertionError("internal replay must not run a provider-backed runner")


class _NoOpHistoryLoader:
    def preload(
        self,
        ticker: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> None:
        del ticker, date_from, date_to, warmup_bars


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
        assert terminal.error.model_dump(exclude_none=True) == {
            "code": "backtest_failed",
            "stage": "runner",
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


def test_default_service_preflights_actual_provider_model_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ContextStore(tmp_path / "provider-preflight.db")
    store.register_strategy(
        {
            **_eligible_strategy(),
            "id": "agent-unsupported",
            "type": "agent",
            "agent_model": "deepseek-chat",
            "quant_strategy_name": None,
            "quant_params": {},
        }
    )
    store.register_strategy({**_eligible_strategy(), "id": "quant-supported"})
    monkeypatch.setenv("OPENAI_API_KEY", "configured-not-emitted")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.deepseek.com/v1")
    monkeypatch.setattr("agent.backtest_jobs.ActiveBacktestJobRunner", _CompletedRunner)
    service = default_backtest_job_service(store)

    with pytest.raises(StrategyEligibilityError) as raised:
        service.create(
            BacktestRequest(
                strategy_id="agent-unsupported",
                ticker="AAPL",
                date_from=date(2025, 1, 2),
                date_to=date(2025, 1, 10),
                frequency="daily",
                benchmark="SPY",
                mode=BacktestMode.AGENT_EXPERIMENT,
            )
        )

    assert raised.value.code == "provider_capability_unsupported"
    assert raised.value.http_status == 503
    deterministic = service.create(
        BacktestRequest(
            strategy_id="quant-supported",
            ticker="AAPL",
            date_from=date(2025, 1, 2),
            date_to=date(2025, 1, 10),
            frequency="daily",
            benchmark="SPY",
            mode=BacktestMode.DETERMINISTIC,
        )
    )
    assert deterministic.status in {"pending", "running", "completed"}
    service.shutdown()
    completed = service.get(deterministic.backtest_id)
    assert completed is not None
    assert completed.status == "completed"


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


def test_active_backtest_fingerprint_is_stable_across_cache_hits_and_restart(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, store, _ = backtest_api
    market_store = MarketDataStore(tmp_path / "fingerprint-market.db")
    dates = pd.bdate_range("2024-12-02", periods=24)
    for ticker, offset in (("AAPL", 100.0), ("SPY", 400.0)):
        market_store.upsert_ohlcv(
            ticker,
            [
                {
                    "date": trading_date.strftime("%Y-%m-%d"),
                    "open": offset + index,
                    "high": offset + index + 1,
                    "low": offset + index - 1,
                    "close": offset + index + 0.5,
                    "volume": 1000,
                }
                for index, trading_date in enumerate(dates)
            ],
        )
    service = BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(
            market_store,
            history_loader=_NoOpHistoryLoader(),
        ),
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    payload = {
        **_request_payload(),
        "date_from": dates[20].strftime("%Y-%m-%d"),
        "date_to": dates[23].strftime("%Y-%m-%d"),
        "frequency": "daily",
    }

    first = _poll_until_terminal(
        client, client.post("/api/agent/backtest", json=payload).json()["backtest_id"]
    )
    second = _poll_until_terminal(
        client, client.post("/api/agent/backtest", json=payload).json()["backtest_id"]
    )

    assert first.status == second.status == "completed"
    assert first.result is not None and second.result is not None
    assert (
        first.result.provenance.data_snapshot_hash
        == second.result.provenance.data_snapshot_hash
    )
    assert first.result.config.warmup_bars == 20
    assert first.result.config.data_auto_adjust is True
    assert first.result.config.data_actions is False
    assert first.result.config.data_end_exclusive == (
        dates[23] + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert first.result.config.data_lookback_days == 39
    assert first.result.config.data_provider_buffer_days == 100
    assert first.result.config.data_provider_end_semantics == "exclusive"
    assert (
        first.result.config.data_timezone_normalization
        == "exchange_session_date_to_UTC_midnight"
    )
    assert first.result.config.evaluation_bar_count == 4
    assert first.result.config.sample_first_date == dates[20].strftime("%Y-%m-%d")
    assert first.result.config.sample_last_date == dates[23].strftime("%Y-%m-%d")
    assert first.progress.decisions_not_ready == 0
    assert first.decisions[0].status == "completed"
    assert len(first.result.series) == 4
    persisted = store.get_backtest_job(first.backtest_id)
    assert persisted is not None
    assert persisted.input_snapshot_hash == first.result.config.data_snapshot_hash
    snapshot = store.get_backtest_input_snapshot(persisted.input_snapshot_hash or "")
    assert snapshot is not None
    canonical = json.loads(gzip.decompress(snapshot.payload))
    assert canonical["data_provenance"]["target"] == {
        "actions": False,
        "auto_adjust": True,
        "corporate_actions_mode": "provider_adjusted_prices",
        "date_from": dates[20].strftime("%Y-%m-%d"),
        "date_to": dates[23].strftime("%Y-%m-%d"),
        "end_exclusive": (dates[23] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "interval": "1d",
        "library_version": first.result.config.data_provider_version,
        "lookback_days": 39,
        "provider": "yfinance",
        "provider_buffer_days": 100,
        "provider_end_semantics": "exclusive",
        "row_adjustment_modes": ["unknown"],
        "ticker": "AAPL",
        "provider_timezone": "unknown",
        "timezone_normalization": "exchange_session_date_to_UTC_midnight",
        "warmup_bars": 20,
    }
    service.shutdown()
    reopened = BacktestJobService(store=store, runner=_CompletedRunner())
    restored = reopened.get(first.backtest_id)
    assert restored is not None and restored.result is not None
    assert (
        restored.result.provenance.data_snapshot_hash
        == first.result.provenance.data_snapshot_hash
    )
    reopened.shutdown()


def test_input_snapshot_redacts_unknown_provenance_and_hashes_adjustment_mode() -> None:
    index = pd.to_datetime(["2025-01-02"], utc=True)
    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000.0],
        },
        index=index,
    )
    frame.attrs["backtest_data_provenance"] = {
        "provider": "yfinance",
        "api_key": "SNAPSHOT_SECRET",
    }
    frame.attrs["adjustment_modes"] = ("raw_prices",)
    raw = _canonical_input_snapshot(frame, frame)
    adjusted_frame = frame.copy()
    adjusted_frame.attrs["adjustment_modes"] = ("provider_adjusted_prices",)
    adjusted = _canonical_input_snapshot(adjusted_frame, adjusted_frame)

    assert raw.content_hash != adjusted.content_hash
    assert b"SNAPSHOT_SECRET" not in gzip.decompress(raw.payload)
    payload = json.loads(gzip.decompress(raw.payload))
    assert payload["data_provenance"]["target"]["row_adjustment_modes"] == [
        "raw_prices"
    ]
    with pytest.raises(BacktestDataError, match="canonical OHLCV"):
        _canonical_input_snapshot(frame.assign(secret_numeric=123456), frame)


def test_active_backtest_fails_typed_when_all_decisions_are_not_ready(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, store, _ = backtest_api
    market_store = MarketDataStore(tmp_path / "insufficient-market.db")
    dates = pd.bdate_range("2025-01-02", periods=2)
    for ticker, offset in (("AAPL", 100.0), ("SPY", 400.0)):
        market_store.upsert_ohlcv(
            ticker,
            [
                {
                    "date": trading_date.strftime("%Y-%m-%d"),
                    "open": offset + index,
                    "high": offset + index + 1,
                    "low": offset + index - 1,
                    "close": offset + index + 0.5,
                    "volume": 1000,
                }
                for index, trading_date in enumerate(dates)
            ],
        )
    service = BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(
            market_store, history_loader=_NoOpHistoryLoader()
        ),
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    failed = _poll_until_terminal(
        client,
        client.post(
            "/api/agent/backtest",
            json={
                **_request_payload(),
                "date_from": dates[0].strftime("%Y-%m-%d"),
                "date_to": dates[-1].strftime("%Y-%m-%d"),
                "frequency": "daily",
            },
        ).json()["backtest_id"],
    )

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "insufficient_history"
    assert failed.error.stage == "data"
    assert failed.progress.decisions_total == 1
    assert failed.progress.decisions_not_ready == 1
    assert failed.progress.decisions_completed == 0
    assert [decision.status for decision in failed.decisions] == ["not_ready"]
    service.shutdown()


def test_backtest_persists_feature_hash_and_attempt_evidence(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_FeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    created = client.post("/api/agent/backtest", json=_request_payload())
    completed = _poll_until_terminal(client, created.json()["backtest_id"])

    assert completed.status == "completed"
    assert completed.decisions[0].feature_hash == "f" * 64
    assert completed.decisions[0].attempts == 2
    persisted = store.get_backtest_decisions(completed.backtest_id)
    assert persisted[0].feature_hash == "f" * 64
    assert persisted[0].attempts == 2
    service.shutdown()


def test_backtest_fails_when_execution_evidence_update_is_not_persisted(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = backtest_api
    monkeypatch.setattr(
        store,
        "update_backtest_decision_execution",
        lambda _job_id, _sequence, _execution_date: False,
    )
    service = BacktestJobService(store=store, runner=_ExecutionEvidenceRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "backtest_failed"
    assert failed.error.stage == "persistence"
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
    assert failed.error.stage == "agent_execution"
    assert failed.error.decision_date == "2025-01-02T00:00:00Z"
    assert failed.error.attempt == 1
    assert failed.error.message == "Backtest agent execution failed"
    assert "provider detail" not in failed.model_dump_json()
    service.shutdown()


def test_backtest_decision_evidence_write_failure_still_terminates_job(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = backtest_api

    record_decision = store.record_backtest_decision

    def fail_decision_evidence_write(evidence: BacktestDecisionEvidence) -> None:
        if evidence.status == "failed":
            raise OSError("private database detail")
        record_decision(evidence)

    monkeypatch.setattr(store, "record_backtest_decision", fail_decision_evidence_write)
    service = BacktestJobService(
        store=store, runner=_NthDecisionFailingObservabilityRunner()
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "backtest_failed"
    assert failed.error.stage == "persistence"
    assert "private database detail" not in failed.model_dump_json()
    service.shutdown()


@pytest.mark.parametrize(
    "payload",
    [
        {
            "strategy_id": "strategy-1",
            "ticker": "AAPL",
            "date_from": "2025-01-01",
            "date_to": "2025-01-31",
            "api_key": "BACKTEST_SECRET",
        },
        ["BACKTEST_SECRET"],
    ],
)
def test_backtest_request_validation_never_echoes_input(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    payload: object,
) -> None:
    client, _, _ = backtest_api

    response = client.post("/api/agent/backtest", json=payload)

    assert response.status_code == 422
    assert "BACKTEST_SECRET" not in response.text
    assert '"input"' not in response.text
    assert '"ctx"' not in response.text


def test_backtest_persists_safe_provider_failure_category(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ProviderFailingRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.code == "provider_failed"
    assert failed.error.stage == "provider"
    assert failed.error.attempt == 1
    assert failed.error.message == "Backtest decision provider failed"
    service.shutdown()


def test_backtest_nth_decision_failure_keeps_prior_safe_evidence_and_secret_out(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an observer-aware runner which records one decision then fails the next with a provider cause.
    client, store, _ = backtest_api
    service = BacktestJobService(
        store=store, runner=_NthDecisionFailingObservabilityRunner()
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the real ACTIVE route creates and polls the durable job.
    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    # Then: callers receive exact safe location metadata and retained prior evidence, never the provider cause.
    assert failed.status == "failed"
    assert failed.error is not None
    assert failed.error.model_dump(exclude_none=True) == {
        "code": "decision_schema_invalid",
        "stage": "structured_output",
        "decision_date": "2025-01-03T00:00:00Z",
        "attempt": 2,
        "message": "Backtest decision could not be validated",
    }
    assert failed.progress.model_dump() == {
        "bars_total": 2,
        "bars_processed": 2,
        "decisions_total": 2,
        "decisions_eligible": 2,
        "decisions_not_ready": 0,
        "decisions_completed": 1,
        "current_decision_date": None,
    }
    assert [decision.sequence for decision in failed.decisions] == [1, 2]
    assert failed.decisions[0].model_dump(exclude_none=True) == {
        "sequence": 1,
        "signal_date": "2025-01-02T00:00:00Z",
        "status": "completed",
        "attempts": 1,
        "target_position_pct": 50.0,
        "confidence": 0.9,
        "policy_hash": failed.decisions[0].policy_hash,
    }
    assert len(failed.decisions[0].policy_hash) == 64
    assert failed.decisions[1].model_dump(exclude_none=True) == {
        "sequence": 2,
        "signal_date": "2025-01-03T00:00:00Z",
        "status": "failed",
        "attempts": 2,
        "policy_hash": failed.decisions[0].policy_hash,
        "error_code": "decision_schema_invalid",
        "error_stage": "structured_output",
    }
    assert "provider-secret" not in failed.model_dump_json()
    db_dump = "\n".join(
        str(row[0])
        for row in store._system_db()
        .execute(
            "SELECT COALESCE(error_json, '') FROM backtest_jobs "
            "UNION ALL SELECT COALESCE(progress_json, '') FROM backtest_jobs "
            "UNION ALL SELECT COALESCE(feature_hash, '') FROM backtest_decisions "
            "UNION ALL SELECT COALESCE(policy_hash, '') FROM backtest_decisions "
            "UNION ALL SELECT COALESCE(error_code, '') FROM backtest_decisions "
            "UNION ALL SELECT COALESCE(error_stage, '') FROM backtest_decisions"
        )
        .fetchall()
        if row[0] is not None
    )
    assert "provider-secret" not in db_dump
    persisted = store.get_backtest_job(created.json()["backtest_id"])
    assert persisted is not None
    assert persisted.input_snapshot_hash is not None
    snapshot = store.get_backtest_input_snapshot(persisted.input_snapshot_hash)
    assert snapshot is not None
    canonical_snapshot = gzip.decompress(snapshot.payload)
    assert hashlib.sha256(canonical_snapshot).hexdigest() == snapshot.content_hash
    assert b'"target"' in canonical_snapshot
    assert b'"benchmark"' in canonical_snapshot
    service.shutdown()


def test_backtest_rejects_v1_success_without_bound_snapshot(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a runner can produce a result but does not expose the required snapshot sink.
    client, _, _ = backtest_api
    service = BacktestJobService(
        store=backtest_api[1], runner=_UnobservableCompletedRunner()
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the ACTIVE route creates a v1 job through that runner.
    created = client.post("/api/agent/backtest", json=_request_payload())
    terminal = _poll_until_terminal(client, created.json()["backtest_id"])

    # Then: a missing frozen input snapshot prevents a trusted completed result.
    assert terminal.status == "failed"
    assert terminal.error is not None
    assert terminal.error.code == "backtest_failed"
    assert terminal.error.stage == "snapshot"
    service.shutdown()


def test_backtest_redacts_runtime_invalid_typed_error_metadata(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a runner raises a nominally typed error mutated with provider-controlled metadata.
    client, store, _ = backtest_api
    service = BacktestJobService(
        store=store, runner=_NthDecisionFailingObservabilityRunner(True)
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the real route persists the failed v1 job and returns its terminal summary.
    created = client.post("/api/agent/backtest", json=_request_payload())
    failed = _poll_until_terminal(client, created.json()["backtest_id"])

    # Then: invalid runtime metadata is replaced with safe fallbacks in DB and API evidence.
    assert failed.error is not None
    assert failed.error.model_dump(exclude_none=True) == {
        "code": "decision_schema_invalid",
        "attempt": 1,
        "message": "Backtest decision could not be validated",
    }
    assert failed.decisions[1].attempts == 1
    assert failed.decisions[1].error_stage is None
    assert "provider-secret" not in failed.model_dump_json()
    db_dump = "\n".join(
        str(row[0])
        for row in store._system_db()
        .execute(
            "SELECT COALESCE(error_json, '') FROM backtest_jobs "
            "UNION ALL SELECT COALESCE(error_stage, '') FROM backtest_decisions"
        )
        .fetchall()
    )
    assert "provider-secret" not in db_dump
    service.shutdown()


def test_backtest_replay_rehydrates_only_frozen_spec_and_snapshot_after_restart(
    tmp_path: Path,
) -> None:
    # Given: a completed v1 job with a content-addressed compressed snapshot and no mutable Strategy dependency.
    store = ContextStore(tmp_path / "data")
    request = BacktestRequest.model_validate(_request_payload())
    strategy = _eligible_strategy()
    spec = freeze_backtest_run_spec(request, strategy)
    canonical = (
        b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,'
        b'"target":{"columns":[],"rows":[]}}'
    )
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    store.create_backtest_job(
        "replayable", request.model_dump_json(), spec.model_dump_json()
    )
    store.bind_backtest_input_snapshot("replayable", snapshot)
    store.close()
    rebuilt_store = ContextStore(tmp_path / "data")
    runner = _ReplayMustNotRunRunner()
    lookup_calls: list[str] = []

    def reject_strategy_lookup(strategy_id: str) -> dict[str, object] | None:
        lookup_calls.append(strategy_id)
        raise AssertionError("internal replay must not resolve Strategy")

    service = BacktestJobService(
        store=rebuilt_store,
        runner=runner,
        strategy_resolver=reject_strategy_lookup,
    )
    try:
        # When: the internal replay owner reads the persisted job after a storage restart.
        replay = service.replay("replayable")

        # Then: it returns exactly frozen material and does not invoke strategy/provider seams.
        assert replay.spec == spec
        assert replay.snapshot.content_hash == snapshot.content_hash
        assert gzip.decompress(replay.snapshot.payload) == canonical
        assert lookup_calls == []
        assert runner.called is False
        with pytest.raises(BacktestReplayUnavailableError):
            service.replay("missing")
    finally:
        service.shutdown()
        rebuilt_store.close()


def test_backtest_reads_legacy_completed_result_with_unverified_warning(
    tmp_path: Path,
) -> None:
    # Given: a pre-v1 completed result that is valid for the older public result shape.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    request = BacktestRequest.model_validate(_request_payload())
    result = _CompletedRunner().run(
        freeze_backtest_run_spec(request, _eligible_strategy())
    )
    with sqlite3.connect(data_dir / "system.db") as db:
        db.execute(
            "CREATE TABLE backtest_jobs ("
            "id TEXT PRIMARY KEY, request_json TEXT NOT NULL, "
            "status TEXT NOT NULL, result_json TEXT, error_json TEXT, "
            "created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL"
            ")"
        )
        db.execute(
            "INSERT INTO backtest_jobs "
            "(id, request_json, status, result_json, error_json, created_at, started_at, completed_at, updated_at) "
            "VALUES (?, '{}', 'completed', ?, NULL, '2025-01-10T00:00:00Z', NULL, '2025-01-10T00:00:00Z', '2025-01-10T00:00:00Z')",
            ("legacy-completed", result.model_dump_json()),
        )
    store = ContextStore(data_dir)
    service = BacktestJobService(store=store, runner=_CompletedRunner())
    try:
        # When: Todo 3's view adapter reads the migrated legacy job.
        response = service.get("legacy-completed")

        # Then: the original result remains readable but provenance is honestly marked unverified.
        assert response is not None
        assert response.status == "completed"
        assert response.result is not None
        assert "legacy_result_unverified" in response.result.warnings
        stored = store.get_backtest_job("legacy-completed")
        assert stored is not None
        assert stored.contract_version == 0
        assert stored.input_snapshot_hash is None
    finally:
        service.shutdown()
        store.close()


def test_backtest_recreates_completed_store_and_recovers_interrupted_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: one completed record and one running record in the same durable system database.
    store = ContextStore(tmp_path)
    store.register_strategy(_eligible_strategy())
    completed_request = BacktestRequest.model_validate(_request_payload())
    strategy = store.get_strategy("strategy-a")
    assert strategy is not None
    frozen_spec = freeze_backtest_run_spec(completed_request, strategy)
    completed_id = "completed-job"
    interrupted_id = "interrupted-job"
    store.create_backtest_job(
        completed_id,
        completed_request.model_dump_json(),
        frozen_spec.model_dump_json(),
    )
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    store.bind_backtest_input_snapshot(
        completed_id,
        BacktestInputSnapshotContent(
            content_hash=hashlib.sha256(canonical).hexdigest(),
            payload=gzip.compress(canonical, mtime=0),
            uncompressed_bytes=len(canonical),
            row_count_target=0,
            row_count_benchmark=0,
        ),
    )
    store.mark_backtest_job_running(completed_id)
    completed_result = _CompletedRunner().run(frozen_spec)
    store.complete_backtest_job(completed_id, completed_result.model_dump_json())
    store.create_backtest_job(
        interrupted_id,
        completed_request.model_dump_json(),
        frozen_spec.model_dump_json(),
    )
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
