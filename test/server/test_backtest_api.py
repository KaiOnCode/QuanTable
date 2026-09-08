from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from threading import Event
from time import monotonic, sleep

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent.backtest_adapter import BacktestDecisionError
from agent.backtest_jobs import (
    BacktestJobAcceptedResponse,
    BacktestJobResponse,
    BacktestJobService,
    BacktestReplayUnavailableError,
    BacktestRequest,
    _canonical_economic_result_hash,
    _canonical_input_snapshot,
    _replay_snapshot_frames,
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
    BacktestNoTradeReasonView,
    BacktestProgressView,
    BacktestResultView,
    PerformanceMetricsView,
)
from server.routes import agent as agent_routes
from storage.store import (
    BacktestDecisionEvidence,
    BacktestInputSnapshotContent,
    BacktestInputSnapshotRecord,
    ContextStore,
)
from agent.backtest_jobs import ActiveBacktestJobRunner
from broker.backtest_data import BacktestDataError
from dataflow.store import MarketDataStore


def _frozen_replay_provenance(spec: BacktestRunSpec, ticker: str) -> dict[str, object]:
    return {
        "provider": "yfinance",
        "library_version": "test",
        "ticker": ticker,
        "date_from": spec.date_from.isoformat(),
        "date_to": spec.date_to.isoformat(),
        "end_exclusive": (spec.date_to + timedelta(days=1)).strftime("%Y-%m-%d"),
        "lookback_days": 1,
        "provider_buffer_days": 100,
        "interval": "1d",
        "auto_adjust": True,
        "actions": False,
        "warmup_bars": spec.policy.required_lookback_bars,
        "corporate_actions_mode": "provider_adjusted_prices",
        "provider_end_semantics": "exclusive",
        "provider_timezone": "UTC",
        "timezone_normalization": "exchange_session_date_to_UTC_midnight",
    }


def _frozen_replay_frames(spec: BacktestRunSpec) -> tuple[pd.DataFrame, pd.DataFrame]:
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
        index=pd.to_datetime([spec.date_from.isoformat()], utc=True),
    )
    benchmark = target.copy()
    target.attrs["backtest_data_provenance"] = _frozen_replay_provenance(
        spec, spec.ticker
    )
    target.attrs["adjustment_modes"] = ("unknown",)
    benchmark.attrs["backtest_data_provenance"] = _frozen_replay_provenance(
        spec, spec.benchmark
    )
    benchmark.attrs["adjustment_modes"] = ("unknown",)
    return target, benchmark


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
        target, benchmark = _frozen_replay_frames(spec)
        observer.bind_input_snapshot(target, benchmark)
        return self.run(spec)


class _FeatureHashRunner(_CompletedRunner):
    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target, benchmark = _frozen_replay_frames(spec)
        signal_date = f"{spec.date_from.isoformat()}T00:00:00Z"
        observer.bind_input_snapshot(target, benchmark)
        observer.begin_decision(1, signal_date, spec.policy_hash)
        observer.record_decision(
            BacktestDecisionView(
                sequence=1,
                signal_date=signal_date,
                status="completed",
                attempts=2,
                target_position_pct=40.0,
                confidence=0.8,
                action="BUY",
                rationale="enter target",
                feature_hash="f" * 64,
                policy_hash=spec.policy_hash,
            )
        )
        return self.run(spec)


class _NoTradeReasonRunner(_CompletedRunner):
    def run(self, spec: BacktestRunSpec) -> BacktestResultView:
        return (
            super()
            .run(spec)
            .model_copy(
                update={
                    "no_trade_reasons": [
                        BacktestNoTradeReasonView(code="all_hold", count=1)
                    ]
                }
            )
        )


class _ReplayableFeatureHashRunner(_FeatureHashRunner):
    def __init__(self) -> None:
        self.replayed_snapshot_hashes: list[str] = []

    def run_replay_with_observability(
        self,
        spec: BacktestRunSpec,
        snapshot: BacktestInputSnapshotRecord,
        observer: BacktestRunObserver,
    ) -> BacktestResultView:
        self.replayed_snapshot_hashes.append(snapshot.content_hash)
        return self.run_with_observability(spec, observer)

    def run_with_observability(
        self, spec: BacktestRunSpec, observer: BacktestRunObserver
    ) -> BacktestResultView:
        target, benchmark = _frozen_replay_frames(spec)
        signal_date = f"{spec.date_from.isoformat()}T00:00:00Z"
        observer.bind_input_snapshot(target, benchmark)
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
        target, benchmark = _frozen_replay_frames(spec)
        signal_date = f"{spec.date_from.isoformat()}T00:00:00Z"
        observer.bind_input_snapshot(target, benchmark)
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


class _ReplayHistoryMustNotRun:
    def preload(
        self,
        ticker: str,
        date_from: str,
        date_to: str,
        warmup_bars: int = 0,
    ) -> None:
        del ticker, date_from, date_to, warmup_bars
        raise AssertionError("replay must not fetch historical data")


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
    client, store, _ = backtest_api
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
    body = BacktestJobAcceptedResponse.model_validate(created.json())
    assert body.status == "pending"
    backtest_id = body.id
    completed = _poll_until_terminal(client, backtest_id)
    assert completed.status == "completed"
    assert completed.result is not None
    assert completed.config is not None
    assert completed.config.ticker == "AAPL"
    persisted = store.get_backtest_job(backtest_id)
    assert persisted is not None
    assert persisted.run_spec_json is not None
    assert persisted.input_snapshot_hash is not None
    assert persisted.result_json is not None
    persisted_result = BacktestResultView.model_validate_json(persisted.result_json)
    frozen_spec = BacktestRunSpec.model_validate_json(persisted.run_spec_json)
    assert (
        persisted_result.provenance.canonical_result_hash
        == _canonical_economic_result_hash(
            frozen_spec,
            persisted_result,
            data_snapshot_hash=persisted.input_snapshot_hash,
        )
    )
    csv_response = client.get(f"/api/agent/backtest/{backtest_id}/trades.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-disposition"].startswith("attachment;")
    assert "ticker" in csv_response.text


def test_backtest_acceptance_and_get_use_the_v1_public_contract(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
) -> None:
    # Given: a valid deterministic request accepted by the ACTIVE route.
    client, store, _ = backtest_api

    # When: the caller creates a job, then polls its durable identity.
    created = client.post("/api/agent/backtest", json=_request_payload())

    # Then: acceptance is deliberately not a racing worker snapshot.
    assert created.status_code == 202
    assert set(created.json()) == {"id", "status", "contract_version"}
    accepted = BacktestJobAcceptedResponse.model_validate(created.json())
    assert accepted.status == "pending"
    assert accepted.contract_version == 1

    terminal = _poll_until_terminal(client, accepted.id)
    assert set(terminal.model_dump(mode="json")) == {
        "id",
        "status",
        "request",
        "config",
        "progress",
        "decisions",
        "result",
        "error",
        "created_at",
        "updated_at",
    }
    assert terminal.status == "completed"
    assert terminal.request is not None
    assert terminal.request.model_dump(mode="json") == {
        **_request_payload(),
        "mode": "deterministic",
    }
    assert terminal.config is not None
    assert terminal.config.ticker == "AAPL"
    assert terminal.error is None
    assert terminal.result is not None
    assert set(terminal.result.model_dump(mode="json")) == {
        "outcome",
        "warnings",
        "no_trade_reasons",
        "metrics",
        "equity",
        "orders",
        "fills",
        "closed_trades",
        "end_position",
        "snapshot",
        "provenance",
    }
    persisted = store.get_backtest_job(accepted.id)
    assert persisted is not None
    assert persisted.input_snapshot_hash is not None
    snapshot = store.get_backtest_input_snapshot(persisted.input_snapshot_hash)
    assert snapshot is not None
    assert terminal.result.snapshot is not None
    assert terminal.result.snapshot.compressed_bytes == snapshot.compressed_bytes
    assert terminal.result.snapshot.uncompressed_bytes == snapshot.uncompressed_bytes


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("strategy_id", "strategy-b"),
        ("ticker", "MSFT"),
        ("date_from", "2025-01-03"),
        ("date_to", "2025-01-09"),
        ("frequency", "daily"),
        ("benchmark", "QQQ"),
        ("mode", "agent_experiment"),
    ],
)
def test_completed_get_rejects_valid_request_tamper_against_frozen_spec(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    tampered_value: str,
) -> None:
    # Given: a completed v1 job whose persisted request is valid but differs from its frozen spec.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    created = client.post("/api/agent/backtest", json=_request_payload())
    assert created.status_code == 202
    job_id = created.json()["id"]
    assert _poll_until_terminal(client, job_id).status == "completed"
    persisted = store.get_backtest_job(job_id)
    assert persisted is not None
    request_payload = json.loads(persisted.request_json)
    request_payload[field] = tampered_value
    with sqlite3.connect(tmp_path / "system.db") as database:
        database.execute(
            "UPDATE backtest_jobs SET request_json = ? WHERE id = ?",
            (json.dumps(request_payload), job_id),
        )
        database.commit()

    # When: callers read or export the tampered completed record.
    response = client.get(f"/api/agent/backtest/{job_id}")

    # Then: the valid-but-mismatched request fails closed through every public seam.
    assert response.status_code == 200
    payload = BacktestJobResponse.model_validate(response.json())
    assert payload.status == "failed"
    assert payload.result is None
    assert payload.decisions == []
    assert payload.error is not None
    assert payload.error.code == "storage_corrupt"
    for export_path in (
        "trades.csv",
        "closed-trades.csv",
        "decisions.csv",
        "decisions.json",
    ):
        export = client.get(f"/api/agent/backtest/{job_id}/{export_path}")
        assert export.status_code == 409
        assert export.json()["detail"]["code"] == "export_unavailable"
    service.shutdown()


def test_backtest_public_result_preserves_observed_no_trade_reasons(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed runner records an observed all-hold no-trade cause.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_NoTradeReasonRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the client creates and polls the durable public job resource.
    created = client.post("/api/agent/backtest", json=_request_payload())
    terminal = _poll_until_terminal(client, created.json()["id"])

    # Then: the v1 result preserves the runner's observed reason without browser inference.
    assert terminal.status == "completed"
    assert terminal.result is not None
    assert terminal.result.model_dump(mode="json")["no_trade_reasons"] == [
        {"code": "all_hold", "count": 1}
    ]
    service.shutdown()


def test_backtest_api_contract_documentation_round_trips_the_v1_terminal_example() -> (
    None
):
    # Given: the contract documents an exact terminal-success result field list and JSON.
    document = Path("docs/api-contracts.md").read_text()
    heading = "**Terminal-success response (exact JSON shape):**"
    result_fields_start = document.index(
        "`result` is non-null only for terminal success"
    )
    result_fields_end = document.index("`error` is non-null", result_fields_start)
    block_start = document.index("```json", document.index(heading)) + len("```json")
    block_end = document.index("```", block_start)
    payload = json.loads(document[block_start:block_end])

    # When: the prose and JSON example are checked against the public response model.
    # Then: both representations include the required snapshot field exactly.
    assert "`snapshot`" in document[result_fields_start:result_fields_end]
    assert (
        BacktestJobResponse.model_validate(payload).model_dump(mode="json") == payload
    )


def test_backtest_exports_use_fixed_public_columns_and_safe_downloads(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed job with persisted safe decision evidence.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_FeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    # When: the caller requests every completed-job export representation.
    created = client.post("/api/agent/backtest", json=_request_payload())
    assert created.status_code == 202
    backtest_id = created.json()["id"]
    assert _poll_until_terminal(client, backtest_id).status == "completed"
    exports = {
        "trades": client.get(f"/api/agent/backtest/{backtest_id}/trades.csv"),
        "closed-trades": client.get(
            f"/api/agent/backtest/{backtest_id}/closed-trades.csv"
        ),
        "decisions": client.get(f"/api/agent/backtest/{backtest_id}/decisions.csv"),
        "decisions-json": client.get(
            f"/api/agent/backtest/{backtest_id}/decisions.json"
        ),
    }

    # Then: each representation is narrow, typed, and safe to download.
    assert exports["trades"].status_code == 200
    assert exports["trades"].text.splitlines()[0] == (
        "date,ticker,side,quantity,price,realized_pl,equity_after"
    )
    assert exports["closed-trades"].text.splitlines()[0] == (
        "entry_date,exit_date,ticker,quantity,entry_vwap,exit_vwap,"
        "net_realized_pl,fees,slippage,holding_period_trading_days"
    )
    assert exports["decisions"].text.splitlines()[0] == (
        "sequence,signal_date,execution_date,status,target_position_pct,"
        "confidence,action,rationale,attempts,error_code"
    )
    assert exports["decisions-json"].json() == [
        {
            "sequence": 1,
            "signal_date": "2025-01-02T00:00:00Z",
            "execution_date": None,
            "status": "completed",
            "target_position_pct": 40.0,
            "confidence": 0.8,
            "action": "BUY",
            "rationale": "enter target",
            "attempts": 2,
            "error_code": None,
        }
    ]
    for kind, response in exports.items():
        extension = "json" if kind == "decisions-json" else "csv"
        filename_kind = "decisions" if kind == "decisions-json" else kind
        assert response.headers["content-disposition"] == (
            f'attachment; filename="backtest-{backtest_id}-{filename_kind}.{extension}"'
        )
    assert exports["trades"].headers["content-type"] == "text/csv; charset=utf-8"
    assert exports["decisions-json"].headers["content-type"] == "application/json"
    service.shutdown()


def test_backtest_replay_reuses_only_the_frozen_snapshot_and_new_identity(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed v1 job whose persisted evidence is independently corrupted.
    client, store, _ = backtest_api
    runner = _ReplayableFeatureHashRunner()
    strategy_reads: list[str] = []

    def resolve_strategy(strategy_id: str) -> dict[str, object] | None:
        strategy_reads.append(strategy_id)
        return store.get_strategy(strategy_id)

    service = BacktestJobService(
        store=store,
        runner=runner,
        strategy_resolver=resolve_strategy,
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    strategy_reads.clear()

    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")

    assert replayed.status_code == 202
    replay_acceptance = BacktestJobAcceptedResponse.model_validate(replayed.json())
    assert replay_acceptance.id != source_id
    assert strategy_reads == []
    assert _poll_until_terminal(client, replay_acceptance.id).status == "completed"
    replay_row = store.get_backtest_job(replay_acceptance.id)
    assert replay_row is not None
    assert replay_row.input_snapshot_hash == source_row.input_snapshot_hash
    assert runner.replayed_snapshot_hashes == [source_row.input_snapshot_hash]

    unavailable_id = "a" * 32
    request = BacktestRequest.model_validate(_request_payload())
    spec = freeze_backtest_run_spec(request, _eligible_strategy())
    store.create_backtest_job(
        unavailable_id,
        request.model_dump_json(),
        spec.model_dump_json(),
    )
    unavailable = client.post(f"/api/agent/backtest/{unavailable_id}/replay")
    assert unavailable.status_code == 409
    assert unavailable.json()["detail"]["code"] == "replay_unavailable"
    service.shutdown()


@pytest.mark.parametrize(
    "request_tamper",
    ["invalid_json", "valid_but_different"],
)
def test_backtest_replay_rejects_request_and_spec_incoherence_before_acceptance(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    request_tamper: str,
) -> None:
    # Given: a completed source whose persisted request no longer coheres with its spec.
    client, store, _ = backtest_api
    runner = _ReplayableFeatureHashRunner()
    service = BacktestJobService(store=store, runner=runner)
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    if request_tamper == "invalid_json":
        replacement = "{"
    else:
        request_payload = json.loads(source_row.request_json)
        request_payload["ticker"] = "MSFT"
        replacement = json.dumps(request_payload)
    database = store._system_db()
    database.execute(
        "UPDATE backtest_jobs SET request_json = ? WHERE id = ?",
        (replacement, source_id),
    )
    database.commit()

    # When: the source is replayed through the public acceptance boundary.
    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")
    if replayed.status_code == 202:
        _poll_until_terminal(client, replayed.json()["id"])
    service.shutdown()

    # Then: replay fails before child allocation or runner submission.
    assert replayed.status_code == 409
    assert replayed.json()["detail"]["code"] == "replay_unavailable"
    assert database.execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0] == 1
    assert runner.replayed_snapshot_hashes == []


def test_backtest_replay_rejects_corrupt_snapshot_before_acceptance(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)

    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    with sqlite3.connect(tmp_path / "system.db") as database:
        database.execute(
            "UPDATE backtest_input_snapshots SET payload = ? WHERE content_hash = ?",
            (b"corrupt", source_row.input_snapshot_hash),
        )

    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")

    assert replayed.status_code == 409
    assert replayed.json()["detail"]["code"] == "replay_unavailable"
    service.shutdown()


def test_backtest_replay_rejects_truncated_gzip_snapshot_before_acceptance(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a source job has a truncated gzip stream whose database metadata is otherwise coherent.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    snapshot = store.get_backtest_input_snapshot(source_row.input_snapshot_hash)
    assert snapshot is not None
    truncated_payload = snapshot.payload[:-1]
    with sqlite3.connect(tmp_path / "system.db") as database:
        database.execute(
            "UPDATE backtest_input_snapshots SET payload = ?, compressed_bytes = ? "
            "WHERE content_hash = ?",
            (truncated_payload, len(truncated_payload), source_row.input_snapshot_hash),
        )
        database.commit()

    # When: replay verifies the frozen input before allocating a child job.
    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")

    # Then: gzip corruption is a public replay-unavailable error, never a 500.
    assert replayed.status_code == 409
    assert replayed.json()["detail"]["code"] == "replay_unavailable"
    assert (
        store._system_db().execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0]
        == 1
    )
    service.shutdown()


def test_backtest_replay_rejects_snapshot_metadata_mismatch_before_acceptance(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Given: a source job has a byte-valid frozen payload whose persisted size metadata is tampered.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    with sqlite3.connect(tmp_path / "system.db") as database:
        database.execute(
            "UPDATE backtest_input_snapshots "
            "SET uncompressed_bytes = uncompressed_bytes + 1 "
            "WHERE content_hash = ?",
            (source_row.input_snapshot_hash,),
        )
        database.commit()

    # When: the public replay endpoint reads the frozen record.
    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")

    # Then: validation fails before a new job can be accepted.
    assert replayed.status_code == 409
    assert replayed.json()["detail"]["code"] == "replay_unavailable"
    assert (
        store._system_db().execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0]
        == 1
    )
    service.shutdown()


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "target_ticker",
        "benchmark_ticker",
        "evaluation_start",
        "evaluation_end",
        "provider_contract",
        "requested_warmup",
        "zero_ohlc",
        "negative_ohlc",
        "boolean_ohlcv",
        "noncanonical_date",
        "no_evaluation_target",
        "later_than_end",
        "target_empty",
    ],
)
def test_backtest_replay_rejects_semantically_invalid_snapshot_before_acceptance(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    # Given: a completed v1 job whose frozen payload is re-signed after semantic tamper.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    assert source_row.run_spec_json is not None
    assert source_row.result_json is not None
    snapshot = store.get_backtest_input_snapshot(source_row.input_snapshot_hash)
    assert snapshot is not None
    payload = json.loads(gzip.decompress(snapshot.payload))
    if tamper_kind == "target_ticker":
        payload["data_provenance"]["target"]["ticker"] = "MSFT"
    elif tamper_kind == "benchmark_ticker":
        payload["data_provenance"]["benchmark"]["ticker"] = "QQQ"
    elif tamper_kind == "evaluation_start":
        payload["data_provenance"]["target"]["date_from"] = "2025-01-03"
    elif tamper_kind == "evaluation_end":
        payload["data_provenance"]["benchmark"]["date_to"] = "2025-01-09"
    elif tamper_kind == "provider_contract":
        payload["data_provenance"]["target"]["provider"] = "fixture"
    elif tamper_kind == "requested_warmup":
        payload["data_provenance"]["target"]["warmup_bars"] = 1
    elif tamper_kind == "zero_ohlc":
        payload["target"]["rows"][0][1:5] = [0.0, 0.0, 0.0, 0.0]
    elif tamper_kind == "negative_ohlc":
        payload["target"]["rows"][0][1:5] = [-100.0, -99.0, -101.0, -100.0]
    elif tamper_kind == "boolean_ohlcv":
        payload["target"]["rows"][0][1:6] = [True, True, True, True, True]
    elif tamper_kind == "noncanonical_date":
        payload["target"]["rows"][0][0] = "2025-01-02T00:00:00Z"
    elif tamper_kind == "no_evaluation_target":
        payload["target"]["rows"][0][0] = "2025-01-01"
    elif tamper_kind == "later_than_end":
        payload["target"]["rows"][0][0] = "2025-01-11"
    else:
        payload["target"] = {"columns": [], "rows": []}
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    replacement = gzip.compress(canonical, mtime=0)
    replacement_hash = hashlib.sha256(canonical).hexdigest()
    spec = BacktestRunSpec.model_validate_json(source_row.run_spec_json)
    stored_result = BacktestResultView.model_validate_json(source_row.result_json)
    rebound_result = stored_result.model_copy(
        update={
            "config": stored_result.config.model_copy(
                update={"data_snapshot_hash": replacement_hash}
            ),
            "provenance": stored_result.provenance.model_copy(
                update={"data_snapshot_hash": replacement_hash}
            ),
        }
    )
    rebound_result = rebound_result.model_copy(
        update={
            "provenance": rebound_result.provenance.model_copy(
                update={
                    "canonical_result_hash": _canonical_economic_result_hash(
                        spec,
                        rebound_result,
                        data_snapshot_hash=replacement_hash,
                    )
                }
            )
        }
    )
    with sqlite3.connect(tmp_path / "system.db") as database:
        database.execute("PRAGMA foreign_keys = OFF")
        database.execute(
            "UPDATE backtest_jobs SET input_snapshot_hash = ?, result_json = ? "
            "WHERE id = ?",
            (replacement_hash, rebound_result.model_dump_json(), source_id),
        )
        database.execute(
            "UPDATE backtest_input_snapshots "
            "SET content_hash = ?, payload = ?, compressed_bytes = ?, "
            "uncompressed_bytes = ?, row_count_target = ? "
            "WHERE content_hash = ?",
            (
                replacement_hash,
                replacement,
                len(replacement),
                len(canonical),
                len(payload["target"]["rows"]),
                snapshot.content_hash,
            ),
        )
        database.commit()

    # When: completed-read and replay inspect the same syntactically valid evidence.
    completed = client.get(f"/api/agent/backtest/{source_id}")
    replayed = client.post(f"/api/agent/backtest/{source_id}/replay")

    # Then: both seams fail closed and replay allocates no child job.
    assert completed.status_code == 200
    completed_payload = BacktestJobResponse.model_validate(completed.json())
    assert completed_payload.status == "failed"
    assert completed_payload.result is None
    assert completed_payload.error is not None
    assert completed_payload.error.code == "storage_corrupt"
    assert replayed.status_code == 409
    assert replayed.json()["detail"]["code"] == "replay_unavailable"
    assert (
        store._system_db().execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0]
        == 1
    )
    service.shutdown()


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "snapshot_metadata",
        "truncated_snapshot",
        "decision_projection",
        "decision_status_type",
        "decision_attempts_type",
        "config_projection",
        "config_rehashed",
        "config_snapshot_hash_rehashed",
        "nonfinite_config",
    ],
)
def test_completed_read_rejects_tampered_frozen_evidence_and_exports(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    tamper_kind: str,
) -> None:
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    assert source.status_code == 202
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    assert source_row.result_json is not None
    database_path = tmp_path / "system.db"
    with sqlite3.connect(database_path) as database:
        if tamper_kind == "snapshot_metadata":
            database.execute(
                "UPDATE backtest_input_snapshots "
                "SET uncompressed_bytes = uncompressed_bytes + 1 "
                "WHERE content_hash = ?",
                (source_row.input_snapshot_hash,),
            )
        elif tamper_kind == "truncated_snapshot":
            snapshot = store.get_backtest_input_snapshot(source_row.input_snapshot_hash)
            assert snapshot is not None
            truncated_payload = snapshot.payload[:-1]
            database.execute(
                "UPDATE backtest_input_snapshots SET payload = ?, compressed_bytes = ? "
                "WHERE content_hash = ?",
                (
                    truncated_payload,
                    len(truncated_payload),
                    source_row.input_snapshot_hash,
                ),
            )
        elif tamper_kind == "decision_status_type":
            database.execute(
                "UPDATE backtest_decisions SET status = ? WHERE job_id = ?",
                ("corrupt", source_id),
            )
        elif tamper_kind == "decision_attempts_type":
            database.execute(
                "UPDATE backtest_decisions SET attempts = ? WHERE job_id = ?",
                ("corrupt", source_id),
            )
        elif tamper_kind == "decision_projection":
            database.execute(
                "UPDATE backtest_decisions "
                "SET target_position_pct = target_position_pct + 1 "
                "WHERE job_id = ?",
                (source_id,),
            )
        elif tamper_kind == "config_snapshot_hash_rehashed":
            result = BacktestResultView.model_validate_json(source_row.result_json)
            replacement_hash = "f" * 64
            assert replacement_hash != source_row.input_snapshot_hash
            tampered = result.model_copy(
                update={
                    "config": result.config.model_copy(
                        update={"data_snapshot_hash": replacement_hash}
                    )
                }
            )
            assert source_row.run_spec_json is not None
            spec = BacktestRunSpec.model_validate_json(source_row.run_spec_json)
            tampered = tampered.model_copy(
                update={
                    "provenance": tampered.provenance.model_copy(
                        update={
                            "canonical_result_hash": _canonical_economic_result_hash(
                                spec,
                                tampered,
                                data_snapshot_hash=source_row.input_snapshot_hash,
                            )
                        }
                    )
                }
            )
            database.execute(
                "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
                (tampered.model_dump_json(), source_id),
            )
        elif tamper_kind in {"config_projection", "config_rehashed"}:
            result = BacktestResultView.model_validate_json(source_row.result_json)
            tampered = result.model_copy(
                update={
                    "config": result.config.model_copy(
                        update={"initial_capital": result.config.initial_capital + 1.0}
                    )
                }
            )
            if tamper_kind == "config_rehashed":
                assert source_row.run_spec_json is not None
                spec = BacktestRunSpec.model_validate_json(source_row.run_spec_json)
                tampered = tampered.model_copy(
                    update={
                        "provenance": tampered.provenance.model_copy(
                            update={
                                "canonical_result_hash": (
                                    _canonical_economic_result_hash(
                                        spec,
                                        tampered,
                                        data_snapshot_hash=(
                                            source_row.input_snapshot_hash
                                        ),
                                    )
                                )
                            }
                        )
                    }
                )
            database.execute(
                "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
                (tampered.model_dump_json(), source_id),
            )
        else:
            tampered_payload = json.loads(source_row.result_json)
            tampered_payload["config"]["initial_capital"] = float("nan")
            database.execute(
                "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
                (json.dumps(tampered_payload, allow_nan=True), source_id),
            )
        database.commit()

    # When: callers read the completed resource through its public seam.
    response = client.get(f"/api/agent/backtest/{source_id}")

    # Then: the read and every export fail closed without exposing partial evidence.
    assert response.status_code == 200
    payload = BacktestJobResponse.model_validate(response.json())
    assert payload.status == "failed"
    assert payload.result is None
    assert payload.error is not None
    assert payload.error.code == "storage_corrupt"
    assert payload.decisions == []
    for export_path in (
        "trades.csv",
        "closed-trades.csv",
        "decisions.csv",
        "decisions.json",
    ):
        export = client.get(f"/api/agent/backtest/{source_id}/{export_path}")
        assert export.status_code == 409
        assert export.json()["detail"]["code"] == "export_unavailable"
    service.shutdown()


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    [
        ("provider_adjustment_mode", "raw_prices_v1"),
        ("corporate_actions_mode", "raw_prices"),
        ("data_provider", "other"),
        ("data_provider_version", "tampered"),
        ("data_interval", "5m"),
        ("data_auto_adjust", False),
        ("data_actions", True),
        ("data_end_exclusive", "2099-01-01"),
        ("data_lookback_days", 999),
        ("data_provider_buffer_days", 101),
        ("data_provider_end_semantics", "inclusive"),
        ("data_provider_timezone", "Asia/Shanghai"),
        ("data_timezone_normalization", "none"),
        ("warmup_bars", 999),
        ("risk_free_rate", 0.01),
        ("periods_per_year", 365),
        ("evaluation_bar_count", 999),
        ("sample_first_date", "2025-01-03"),
        ("sample_last_date", "2025-01-09"),
    ],
)
def test_completed_read_binds_every_snapshot_derived_config_field_after_rehash(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    tampered_value: str | int | float | bool,
) -> None:
    # Given: one completed result has one snapshot-derived config field altered and rehashed.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_ReplayableFeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    source = client.post("/api/agent/backtest", json=_request_payload())
    source_id = source.json()["id"]
    assert _poll_until_terminal(client, source_id).status == "completed"
    source_row = store.get_backtest_job(source_id)
    assert source_row is not None
    assert source_row.input_snapshot_hash is not None
    assert source_row.result_json is not None
    assert source_row.run_spec_json is not None
    result = BacktestResultView.model_validate_json(source_row.result_json)
    spec = BacktestRunSpec.model_validate_json(source_row.run_spec_json)
    tampered = result.model_copy(
        update={"config": result.config.model_copy(update={field: tampered_value})}
    )
    tampered = tampered.model_copy(
        update={
            "provenance": tampered.provenance.model_copy(
                update={
                    "canonical_result_hash": _canonical_economic_result_hash(
                        spec,
                        tampered,
                        data_snapshot_hash=source_row.input_snapshot_hash,
                    )
                }
            )
        }
    )
    database = store._system_db()
    database.execute(
        "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
        (tampered.model_dump_json(), source_id),
    )
    database.commit()

    # When: callers read and export the rehashed completed evidence.
    response = client.get(f"/api/agent/backtest/{source_id}")

    # Then: the snapshot/spec binding wins over a self-consistent forged result hash.
    payload = BacktestJobResponse.model_validate(response.json())
    assert payload.status == "failed"
    assert payload.result is None
    assert payload.error is not None
    assert payload.error.code == "storage_corrupt"
    for export_path in (
        "trades.csv",
        "closed-trades.csv",
        "decisions.csv",
        "decisions.json",
    ):
        assert (
            client.get(f"/api/agent/backtest/{source_id}/{export_path}").status_code
            == 409
        )
    service.shutdown()


@pytest.mark.parametrize(
    "include_benchmark",
    [True, False],
    ids=["benchmark-available", "benchmark-unavailable"],
)
def test_active_replay_survives_storage_restart_without_data_or_strategy_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    include_benchmark: bool,
) -> None:
    # Given: a completed frozen source run whose storage survives a process restart.
    data_dir = tmp_path / "context"
    source_store = ContextStore(data_dir)
    source_store.register_strategy(_eligible_strategy())
    market_store = MarketDataStore(tmp_path / "source-market.db")
    dates = pd.bdate_range("2024-12-02", periods=24)
    for ticker, offset in (("AAPL", 100.0), ("SPY", 400.0)):
        if ticker == "SPY" and not include_benchmark:
            continue
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
    source_service = BacktestJobService(
        store=source_store,
        runner=ActiveBacktestJobRunner(
            market_store,
            history_loader=_NoOpHistoryLoader(),
        ),
    )
    monkeypatch.setattr(
        agent_routes, "get_backtest_job_service", lambda: source_service
    )
    source_app = FastAPI()
    source_app.include_router(agent_routes.router, prefix="/api")
    request = {
        **_request_payload(),
        "date_from": dates[20].strftime("%Y-%m-%d"),
        "date_to": dates[23].strftime("%Y-%m-%d"),
        "frequency": "daily",
    }
    with TestClient(source_app, raise_server_exceptions=False) as source_client:
        source = source_client.post("/api/agent/backtest", json=request)
        assert source.status_code == 202
        source_terminal = _poll_until_terminal(source_client, source.json()["id"])
    if not include_benchmark:
        assert source_terminal.status == "failed"
        assert source_terminal.error is not None
        assert source_terminal.error.code == "market_data_unavailable"
        assert source_terminal.error.stage == "data"
        source_service.shutdown()
        source_store.close()
        return
    assert source_terminal.status == "completed"
    assert source_terminal.result is not None
    source_service.shutdown()
    source_store.close()

    rebuilt_store = ContextStore(data_dir)
    strategy_reads: list[str] = []

    def reject_strategy_read(strategy_id: str) -> dict[str, object] | None:
        strategy_reads.append(strategy_id)
        raise AssertionError("replay must not resolve Strategy")

    replay_service = BacktestJobService(
        store=rebuilt_store,
        runner=ActiveBacktestJobRunner(
            MarketDataStore(tmp_path / "replay-market.db"),
            history_loader=_ReplayHistoryMustNotRun(),
        ),
        strategy_resolver=reject_strategy_read,
    )
    monkeypatch.setattr(
        agent_routes, "get_backtest_job_service", lambda: replay_service
    )
    replay_app = FastAPI()
    replay_app.include_router(agent_routes.router, prefix="/api")
    replay_terminals: list[BacktestJobResponse] = []

    # When: the same frozen source is replayed ten times through the public API.
    with TestClient(replay_app, raise_server_exceptions=False) as replay_client:
        for _ in range(10):
            replay = replay_client.post(
                f"/api/agent/backtest/{source_terminal.id}/replay"
            )
            assert replay.status_code == 202
            replay_terminals.append(
                _poll_until_terminal(replay_client, replay.json()["id"])
            )

    # Then: economics are identical while operational identities remain independent.
    assert all(terminal.status == "completed" for terminal in replay_terminals)
    replay_results = []
    for terminal in replay_terminals:
        assert terminal.result is not None
        replay_results.append(terminal.result)
    source_result = source_terminal.result
    assert len({terminal.id for terminal in [source_terminal, *replay_terminals]}) == 11
    assert source_result.fills
    assert source_result.orders
    assert all(
        replay_result.provenance.canonical_result_hash
        == source_result.provenance.canonical_result_hash
        for replay_result in replay_results
    )
    for replay_terminal, replay_result in zip(
        replay_terminals, replay_results, strict=True
    ):
        assert replay_result.outcome == source_result.outcome
        assert replay_result.warnings == source_result.warnings
        assert replay_result.no_trade_reasons == source_result.no_trade_reasons
        assert replay_result.metrics == source_result.metrics
        assert replay_result.equity == source_result.equity
        assert replay_result.end_position == source_result.end_position
        assert replay_terminal.decisions == source_terminal.decisions
        assert [
            fill.model_dump(
                exclude={
                    "order_id",
                    "strategy_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                }
            )
            for fill in replay_result.fills
        ] == [
            fill.model_dump(
                exclude={
                    "order_id",
                    "strategy_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                }
            )
            for fill in source_result.fills
        ]
        assert [
            order.model_dump(exclude={"order_id"}) for order in replay_result.orders
        ] == [order.model_dump(exclude={"order_id"}) for order in source_result.orders]
        assert [
            closed_trade.model_dump(
                exclude={"strategy_id", "account_id", "session_id", "decision_id"}
            )
            for closed_trade in replay_result.closed_trades
        ] == [
            closed_trade.model_dump(
                exclude={"strategy_id", "account_id", "session_id", "decision_id"}
            )
            for closed_trade in source_result.closed_trades
        ]
    run_results = [source_result, *replay_results]
    order_ids = [order.order_id for result in run_results for order in result.orders]
    fill_order_ids = [fill.order_id for result in run_results for fill in result.fills]
    session_ids = {fill.session_id for result in run_results for fill in result.fills}
    assert len(set(order_ids)) == len(order_ids)
    assert len(set(fill_order_ids)) == len(fill_order_ids)
    assert len(session_ids) == len(run_results)
    assert strategy_reads == []
    replay_service.shutdown()
    rebuilt_store.close()


@pytest.mark.parametrize("frequency", ["daily", "weekly", "monthly"])
def test_active_two_year_synthetic_aapl_spy_api_matrix_has_ten_stable_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frequency: str,
) -> None:
    dates = pd.bdate_range("2022-01-03", "2023-12-29")
    market_store = MarketDataStore(tmp_path / f"{frequency}-market.db")
    for ticker, multiplier in (("AAPL", 1.0), ("SPY", 3.0)):
        rows: list[dict[str, float | str]] = []
        for position, trading_date in enumerate(dates):
            phase = position % 80
            close = (
                100.0 + phase * 2.0 if phase <= 40 else 180.0 - (phase - 40) * 2.0
            ) * multiplier
            rows.append(
                {
                    "date": trading_date.strftime("%Y-%m-%d"),
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.5,
                    "close": close,
                    "volume": 1_000.0,
                }
            )
        market_store.upsert_ohlcv(ticker, rows)
    store = ContextStore(tmp_path / f"{frequency}-context")
    store.register_strategy(_eligible_strategy())
    service = BacktestJobService(
        store=store,
        runner=ActiveBacktestJobRunner(
            market_store,
            history_loader=_NoOpHistoryLoader(),
        ),
    )
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")
    request = {
        **_request_payload(),
        "date_from": dates[0].strftime("%Y-%m-%d"),
        "date_to": dates[-1].strftime("%Y-%m-%d"),
        "frequency": frequency,
    }
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            created = client.post("/api/agent/backtest", json=request)
            assert created.status_code == 202
            terminals = [
                _poll_until_terminal(client, created.json()["id"], timeout_seconds=30.0)
            ]
            for _ in range(9):
                replay = client.post(f"/api/agent/backtest/{terminals[0].id}/replay")
                assert replay.status_code == 202
                terminals.append(
                    _poll_until_terminal(
                        client, replay.json()["id"], timeout_seconds=30.0
                    )
                )
    finally:
        service.shutdown()
        store.close()

    assert {terminal.status for terminal in terminals} == {"completed"}
    assert len({terminal.id for terminal in terminals}) == 10
    assert all(terminal.result is not None for terminal in terminals)
    results = [terminal.result for terminal in terminals]
    assert all(result is not None for result in results)
    baseline = results[0]
    assert baseline is not None
    assert baseline.closed_trades
    assert (
        len(
            {
                result.provenance.canonical_result_hash
                for result in results
                if result is not None
            }
        )
        == 1
    )
    candidates = pd.DatetimeIndex(dates[:-1])
    if frequency == "daily":
        expected_dates = candidates
    elif frequency == "weekly":
        expected_dates = candidates[
            [timestamp.weekday() == 4 for timestamp in candidates]
        ]
    else:
        expected_dates = candidates[
            candidates.to_period("M") != dates[1:].to_period("M")
        ]
    expected_signals = [
        timestamp.strftime("%Y-%m-%dT00:00:00Z") for timestamp in expected_dates
    ]
    assert [
        decision.signal_date for decision in terminals[0].decisions
    ] == expected_signals
    for terminal, result in zip(terminals[1:], results[1:], strict=True):
        assert result is not None
        assert terminal.decisions == terminals[0].decisions
        assert result.metrics == baseline.metrics
        assert result.equity == baseline.equity
        assert [
            closed_trade.model_dump(
                exclude={"strategy_id", "account_id", "session_id", "decision_id"}
            )
            for closed_trade in result.closed_trades
        ] == [
            closed_trade.model_dump(
                exclude={"strategy_id", "account_id", "session_id", "decision_id"}
            )
            for closed_trade in baseline.closed_trades
        ]
        assert [order.model_dump(exclude={"order_id"}) for order in result.orders] == [
            order.model_dump(exclude={"order_id"}) for order in baseline.orders
        ]
        assert [
            fill.model_dump(
                exclude={
                    "order_id",
                    "strategy_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                }
            )
            for fill in result.fills
        ] == [
            fill.model_dump(
                exclude={
                    "order_id",
                    "strategy_id",
                    "account_id",
                    "session_id",
                    "decision_id",
                }
            )
            for fill in baseline.fills
        ]
    order_ids = [
        order.order_id
        for result in results
        if result is not None
        for order in result.orders
    ]
    fill_order_ids = [
        fill.order_id
        for result in results
        if result is not None
        for fill in result.fills
    ]
    session_ids = {
        fill.session_id
        for result in results
        if result is not None
        for fill in result.fills
    }
    assert order_ids and fill_order_ids and session_ids
    assert len(set(order_ids)) == len(order_ids)
    assert len(set(fill_order_ids)) == len(fill_order_ids)
    assert len(session_ids) == len(results)


def test_active_completed_hash_recomputes_from_final_persisted_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a deterministic active job with a frozen input snapshot and final sample warnings.
    store = ContextStore(tmp_path / "context")
    store.register_strategy(_eligible_strategy())
    market_store = MarketDataStore(tmp_path / "market.db")
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
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")

    # When: the public API persists the completed job.
    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/agent/backtest",
            json={
                **_request_payload(),
                "date_from": dates[20].strftime("%Y-%m-%d"),
                "date_to": dates[23].strftime("%Y-%m-%d"),
                "frequency": "daily",
            },
        )
        assert created.status_code == 202
        terminal = _poll_until_terminal(client, created.json()["id"])
    persisted = store.get_backtest_job(terminal.id)
    assert persisted is not None
    run_spec_json = persisted.run_spec_json
    result_json = persisted.result_json
    input_snapshot_hash = persisted.input_snapshot_hash
    assert run_spec_json is not None
    assert result_json is not None
    assert input_snapshot_hash is not None
    spec = BacktestRunSpec.model_validate_json(run_spec_json)
    result = BacktestResultView.model_validate_json(result_json)

    # Then: provenance is the hash of the completed result that was persisted.
    assert result.provenance.canonical_result_hash == _canonical_economic_result_hash(
        spec,
        result,
        data_snapshot_hash=input_snapshot_hash,
    )
    service.shutdown()
    store.close()


def test_active_get_rejects_a_valid_but_tampered_completed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed deterministic result whose stored JSON is altered without its hash.
    store = ContextStore(tmp_path / "context")
    store.register_strategy(_eligible_strategy())
    market_store = MarketDataStore(tmp_path / "market.db")
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
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/agent/backtest",
            json={
                **_request_payload(),
                "date_from": dates[20].strftime("%Y-%m-%d"),
                "date_to": dates[23].strftime("%Y-%m-%d"),
                "frequency": "daily",
            },
        )
        assert created.status_code == 202
        terminal = _poll_until_terminal(client, created.json()["id"])
        persisted = store.get_backtest_job(terminal.id)
        assert persisted is not None
        assert persisted.result_json is not None
        result = BacktestResultView.model_validate_json(persisted.result_json)
        assert result.summary.total_return_pct is not None
        tampered = result.model_copy(
            update={
                "summary": result.summary.model_copy(
                    update={"total_return_pct": result.summary.total_return_pct + 1.0}
                )
            }
        )
        with sqlite3.connect(tmp_path / "context" / "system.db") as database:
            database.execute(
                "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
                (tampered.model_dump_json(), terminal.id),
            )
            database.commit()

        # When: callers ask the public GET and exports to trust the altered record.
        response = client.get(f"/api/agent/backtest/{terminal.id}")

        # Then: the stale canonical hash safely rejects the completed result and exports.
        assert response.status_code == 200
        payload = BacktestJobResponse.model_validate(response.json())
        assert payload.status == "failed"
        assert payload.result is None
        assert payload.error is not None
        assert payload.error.code == "storage_corrupt"
        for export_path in (
            "trades.csv",
            "closed-trades.csv",
            "decisions.csv",
            "decisions.json",
        ):
            export = client.get(f"/api/agent/backtest/{terminal.id}/{export_path}")
            assert export.status_code == 409
            assert export.json()["detail"]["code"] == "export_unavailable"
    service.shutdown()
    store.close()


def test_active_get_rejects_completed_result_with_tampered_provenance_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ContextStore(tmp_path / "context")
    store.register_strategy(_eligible_strategy())
    market_store = MarketDataStore(tmp_path / "market.db")
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
    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")

    with TestClient(app, raise_server_exceptions=False) as client:
        created = client.post(
            "/api/agent/backtest",
            json={
                **_request_payload(),
                "date_from": dates[20].strftime("%Y-%m-%d"),
                "date_to": dates[23].strftime("%Y-%m-%d"),
                "frequency": "daily",
            },
        )
        assert created.status_code == 202
        terminal = _poll_until_terminal(client, created.json()["id"])
        persisted = store.get_backtest_job(terminal.id)
        assert persisted is not None
        assert persisted.result_json is not None
        result = BacktestResultView.model_validate_json(persisted.result_json)
        tampered = result.model_copy(
            update={
                "provenance": result.provenance.model_copy(
                    update={"policy_hash": "0" * 64}
                )
            }
        )
        with sqlite3.connect(tmp_path / "context" / "system.db") as database:
            database.execute(
                "UPDATE backtest_jobs SET result_json = ? WHERE id = ?",
                (tampered.model_dump_json(), terminal.id),
            )
            database.commit()

        response = client.get(f"/api/agent/backtest/{terminal.id}")

        assert response.status_code == 200
        payload = BacktestJobResponse.model_validate(response.json())
        assert payload.status == "failed"
        assert payload.result is None
        assert payload.error is not None
        assert payload.error.code == "storage_corrupt"
    service.shutdown()
    store.close()


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
    backtest_id = accepted.json()["id"]
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
    failed_job = _poll_until_terminal(client, failed.json()["id"])
    assert failed_job.status == "failed"
    assert failed_job.error is not None
    assert failed_job.error.code == "execution_failed"
    assert failed_job.error.stage == "execution"
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
        terminal = _poll_until_terminal(client, created.json()["id"])

        # Then: every normal runner exception has a safe, persisted failed terminal envelope.
        assert terminal.status == "failed"
        assert terminal.error is not None
        assert terminal.error.model_dump(exclude_none=True) == {
            "code": "execution_failed",
            "stage": "execution",
            "message": "Backtest execution failed",
        }
        assert terminal.result is None
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
        "/api/agent/backtest/{backtest_id}/replay",
        "/api/agent/backtest/{backtest_id}/trades.csv",
        "/api/agent/backtest/{backtest_id}/closed-trades.csv",
        "/api/agent/backtest/{backtest_id}/decisions.csv",
        "/api/agent/backtest/{backtest_id}/decisions.json",
    }
    assert "/api/backtest" not in paths
    assert client.get("/api/agent/backtest/missing").status_code == 422
    assert client.get(f"/api/agent/backtest/{'g' * 32}").status_code == 422
    assert client.get(f"/api/agent/backtest/{'a' * 31}%2F").status_code in {404, 422}
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
    persisted = store.get_backtest_job(created.id)
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
        ({"type": "agent"}, {}, 422, "strategy_type_unsupported"),
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
    assert response.json()["detail"]["code"] == "provider_capability_unsupported"
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
    completed = service.get(deterministic.id)
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
    failed = _poll_until_terminal(client, created.json()["id"])
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
        client, client.post("/api/agent/backtest", json=payload).json()["id"]
    )
    second = _poll_until_terminal(
        client, client.post("/api/agent/backtest", json=payload).json()["id"]
    )

    assert first.status == second.status == "completed"
    assert first.result is not None and second.result is not None
    assert first.config is not None
    assert (
        first.result.provenance.data_snapshot_hash
        == second.result.provenance.data_snapshot_hash
    )
    assert first.config.warmup_bars == 20
    assert first.config.data_auto_adjust is True
    assert first.config.data_actions is False
    assert first.config.data_end_exclusive == (
        dates[23] + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    assert first.config.data_lookback_days == 39
    assert first.config.data_provider_buffer_days == 100
    assert first.config.data_provider_end_semantics == "exclusive"
    assert (
        first.config.data_timezone_normalization
        == "exchange_session_date_to_UTC_midnight"
    )
    assert first.config.evaluation_bar_count == 4
    assert first.config.sample_first_date == dates[20].strftime("%Y-%m-%d")
    assert first.config.sample_last_date == dates[23].strftime("%Y-%m-%d")
    assert first.progress.decisions_not_ready == 0
    assert first.decisions[0].status == "completed"
    assert len(first.result.equity) == 4
    persisted = store.get_backtest_job(first.id)
    assert persisted is not None
    assert persisted.input_snapshot_hash == first.config.data_snapshot_hash
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
        "library_version": first.config.data_provider_version,
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
    restored = reopened.get(first.id)
    assert restored is not None and restored.result is not None
    assert (
        restored.result.provenance.data_snapshot_hash
        == first.result.provenance.data_snapshot_hash
    )
    reopened.shutdown()


def test_active_61_bar_hold_run_persists_sample_and_no_trade_warnings(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, store, _ = backtest_api
    market_store = MarketDataStore(tmp_path / "sample-warnings-market.db")
    dates = pd.bdate_range("2025-01-02", periods=81)
    for ticker, price in (("AAPL", 100.0), ("SPY", 400.0)):
        market_store.upsert_ohlcv(
            ticker,
            [
                {
                    "date": trading_date.strftime("%Y-%m-%d"),
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price,
                    "volume": 1000,
                }
                for trading_date in dates
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

    backtest_id = client.post(
        "/api/agent/backtest",
        json={
            **_request_payload(),
            "date_from": dates[20].strftime("%Y-%m-%d"),
            "date_to": dates[-1].strftime("%Y-%m-%d"),
            "frequency": "daily",
        },
    ).json()["id"]
    for _ in range(200):
        completed = BacktestJobResponse.model_validate(
            client.get(f"/api/agent/backtest/{backtest_id}").json()
        )
        if completed.status in {"completed", "failed"}:
            break
        sleep(0.01)
    else:
        raise AssertionError("61-bar backtest did not reach a terminal status")

    assert completed.status == "completed"
    assert completed.result is not None
    assert completed.config is not None
    assert completed.result.outcome == "completed_no_trades"
    assert completed.config.evaluation_bar_count == 61
    assert {
        "completed_with_no_trades_not_trusted_performance",
        "insufficient_evaluation_bars_lt_63",
        "insufficient_evaluation_bars_lt_252",
        "insufficient_closed_trades_lt_30",
    }.issubset(completed.result.warnings)
    assert [reason.model_dump() for reason in completed.result.no_trade_reasons] == [
        {"code": "all_hold", "count": 60}
    ]
    assert completed.result.metrics.number_of_fills == 0
    assert all(decision.target_position_pct == 0.0 for decision in completed.decisions)
    service.shutdown()


@pytest.mark.parametrize(
    ("frequency", "expected_decisions", "first_signal", "last_signal"),
    [
        ("daily", 60, "2024-01-02", "2024-03-27"),
        ("weekly", 12, "2024-01-05", "2024-03-22"),
        ("monthly", 2, "2024-01-31", "2024-02-29"),
    ],
)
def test_active_original_2024_nyse_window_has_exact_executable_cadence(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    frequency: str,
    expected_decisions: int,
    first_signal: str,
    last_signal: str,
) -> None:
    client, store, _ = backtest_api
    market_store = MarketDataStore(tmp_path / "original-2024-market.db")
    target_dates = pd.bdate_range("2024-01-02", "2024-03-29")
    nyse_holidays = pd.to_datetime(["2024-01-15", "2024-02-19", "2024-03-29"])
    target_dates = target_dates[~target_dates.isin(nyse_holidays)]
    warmup_dates = pd.bdate_range("2023-12-01", "2023-12-29")
    all_dates = warmup_dates.append(target_dates)
    for ticker, price in (("AAPL", 100.0), ("SPY", 400.0)):
        market_store.upsert_ohlcv(
            ticker,
            [
                {
                    "date": trading_date.strftime("%Y-%m-%d"),
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price,
                    "volume": 1_000.0,
                }
                for trading_date in all_dates
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

    created = client.post(
        "/api/agent/backtest",
        json={
            **_request_payload(),
            "date_from": target_dates[0].strftime("%Y-%m-%d"),
            "date_to": target_dates[-1].strftime("%Y-%m-%d"),
            "frequency": frequency,
        },
    )
    assert created.status_code == 202
    completed = _poll_until_terminal(client, created.json()["id"])

    assert completed.status == "completed"
    assert completed.error is None
    assert completed.config is not None
    assert completed.result is not None
    assert completed.config.evaluation_bar_count == 61
    assert completed.progress.decisions_total == expected_decisions
    assert completed.progress.decisions_eligible == expected_decisions
    assert completed.progress.decisions_not_ready == 0
    assert completed.progress.decisions_completed == expected_decisions
    assert len(completed.decisions) == expected_decisions
    assert [
        completed.decisions[0].signal_date,
        completed.decisions[-1].signal_date,
    ] == [
        f"{first_signal}T00:00:00Z",
        f"{last_signal}T00:00:00Z",
    ]
    assert all(
        decision.status == "completed" and decision.error_code is None
        for decision in completed.decisions
    )
    assert completed.result.outcome == "completed_no_trades"
    assert {
        "completed_with_no_trades_not_trusted_performance",
        "insufficient_evaluation_bars_lt_63",
        "insufficient_evaluation_bars_lt_252",
        "insufficient_closed_trades_lt_30",
    }.issubset(completed.result.warnings)
    service.shutdown()


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


def test_replay_snapshot_rejects_empty_benchmark_as_zero_overlap() -> None:
    # Given: a canonical source snapshot uses UTC session dates and an unavailable benchmark.
    request = BacktestRequest.model_validate(
        {
            **_request_payload(),
            "date_from": "2025-01-02",
            "date_to": "2025-01-02",
        }
    )
    spec = freeze_backtest_run_spec(request, _eligible_strategy())
    columns = pd.Index(["Open", "High", "Low", "Close", "Volume"])
    target = pd.DataFrame(
        [[100.0, 101.0, 99.0, 100.5, 1000.0]],
        columns=columns,
        index=pd.to_datetime(["2025-01-02"], utc=True),
    )
    benchmark = pd.DataFrame(
        columns=columns,
        index=pd.DatetimeIndex([], tz="UTC"),
    )
    provenance = {
        "provider": "yfinance",
        "library_version": "1",
        "ticker": "AAPL",
        "date_from": "2025-01-02",
        "date_to": "2025-01-02",
        "end_exclusive": "2025-01-03",
        "lookback_days": 1,
        "provider_buffer_days": 100,
        "interval": "1d",
        "auto_adjust": True,
        "actions": False,
        "warmup_bars": spec.policy.required_lookback_bars,
        "corporate_actions_mode": "provider_adjusted_prices",
        "provider_end_semantics": "exclusive",
        "provider_timezone": "UTC",
        "timezone_normalization": "exchange_session_date_to_UTC_midnight",
    }
    target.attrs["backtest_data_provenance"] = provenance
    target.attrs["adjustment_modes"] = ("provider_adjusted_prices",)
    benchmark.attrs["backtest_data_provenance"] = {
        **provenance,
        "ticker": "SPY",
    }
    benchmark.attrs["adjustment_modes"] = ()
    content = _canonical_input_snapshot(target, benchmark)
    snapshot = BacktestInputSnapshotRecord(
        content_hash=content.content_hash,
        schema_version=1,
        codec="gzip-json-v1",
        payload=content.payload,
        compressed_bytes=len(content.payload),
        uncompressed_bytes=content.uncompressed_bytes,
        row_count_target=content.row_count_target,
        row_count_benchmark=content.row_count_benchmark,
        created_at="2025-01-02T00:00:00Z",
    )

    # When / Then: replay rejects a frozen total non-overlap before child allocation.
    with pytest.raises(BacktestDataError, match="overlapping benchmark session"):
        _replay_snapshot_frames(snapshot, spec)


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
        ).json()["id"],
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
    completed = _poll_until_terminal(client, created.json()["id"])

    assert completed.status == "completed"
    assert completed.decisions[0].feature_hash == "f" * 64
    assert completed.decisions[0].attempts == 2
    assert completed.decisions[0].action == "BUY"
    assert completed.decisions[0].rationale == "enter target"
    assert set(completed.decisions[0].model_dump()) == {
        "sequence",
        "signal_date",
        "execution_date",
        "status",
        "attempts",
        "target_position_pct",
        "confidence",
        "action",
        "rationale",
        "feature_hash",
        "policy_hash",
        "error_code",
        "error_stage",
    }
    persisted = store.get_backtest_decisions(completed.id)
    assert persisted[0].feature_hash == "f" * 64
    assert persisted[0].attempts == 2
    assert persisted[0].action == "BUY"
    assert persisted[0].rationale == "enter target"
    service.shutdown()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_version", "not-integer"),
        ("status", "not-a-status"),
        ("created_at", b"blob-created-at"),
        ("updated_at", b"blob-updated-at"),
    ],
)
def test_corrupt_backtest_job_scalar_projects_safe_get_and_replay_conflict(
    tmp_path: Path, field: str, value: str | bytes
) -> None:
    # Given: SQLite contains a job scalar that cannot cross the typed storage boundary.
    store = ContextStore(tmp_path / "data")
    store.create_backtest_job("a" * 32, "{}", '{"contract_version":"backtest-run/v1"}')
    database = store._system_db()
    database.execute("PRAGMA ignore_check_constraints = ON")
    database.execute(
        f"UPDATE backtest_jobs SET {field} = ? WHERE id = ?", (value, "a" * 32)
    )
    database.commit()
    database.execute("PRAGMA ignore_check_constraints = OFF")
    service = BacktestJobService(store=store, runner=_CompletedRunner())
    try:
        # When: callers use completed-read and replay service boundaries.
        response = service.get("a" * 32)

        # Then: GET is fail-closed and replay rejects before allocating a child.
        assert response is not None
        assert response.status == "failed"
        assert response.error is not None
        assert response.error.code == "storage_corrupt"
        with pytest.raises(BacktestReplayUnavailableError):
            service.replay("a" * 32)
    finally:
        service.shutdown()
        store.close()


def test_corrupt_backtest_decision_text_projects_safe_api_failure(
    backtest_api: tuple[TestClient, ContextStore, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a completed decision's nullable rationale TEXT is replaced by a BLOB.
    client, store, _ = backtest_api
    service = BacktestJobService(store=store, runner=_FeatureHashRunner())
    monkeypatch.setattr(agent_routes, "get_backtest_job_service", lambda: service)
    created = client.post("/api/agent/backtest", json=_request_payload())
    job_id = created.json()["id"]
    assert _poll_until_terminal(client, job_id).status == "completed"
    database = store._system_db()
    database.execute(
        "UPDATE backtest_decisions SET rationale = ? WHERE job_id = ?",
        (b"blob-rationale", job_id),
    )
    database.commit()

    # When: the corrupted decision is read through the public API.
    response = client.get(f"/api/agent/backtest/{job_id}")

    # Then: storage corruption fails closed without exposing BLOB stringification.
    assert response.status_code == 200
    payload = BacktestJobResponse.model_validate(response.json())
    assert payload.status == "failed"
    assert payload.decisions == []
    assert payload.error is not None
    assert payload.error.code == "storage_corrupt"
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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    persisted = store.get_backtest_job(created.json()["id"])
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
    terminal = _poll_until_terminal(client, created.json()["id"])

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
    failed = _poll_until_terminal(client, created.json()["id"])

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
    index = pd.to_datetime([request.date_from.isoformat()], utc=True)
    target = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.0],
            "Close": [100.5],
            "Volume": [1000.0],
        },
        index=index,
    )
    benchmark = target.copy()
    target.attrs["backtest_data_provenance"] = _frozen_replay_provenance(
        spec, spec.ticker
    )
    target.attrs["adjustment_modes"] = ("unknown",)
    benchmark.attrs["backtest_data_provenance"] = _frozen_replay_provenance(
        spec, spec.benchmark
    )
    benchmark.attrs["adjustment_modes"] = ("unknown",)
    snapshot = _canonical_input_snapshot(target, benchmark)
    canonical = gzip.decompress(snapshot.payload)
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
        assert response.result.snapshot is None
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
    monkeypatch.setattr(main, "recover_interrupted_report_jobs", lambda: 0)
    monkeypatch.setattr(main, "recover_interrupted_insight_generations", lambda: 0)
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


def _poll_until_terminal(
    client: TestClient, backtest_id: str, *, timeout_seconds: float = 5.0
) -> BacktestJobResponse:
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        response = client.get(f"/api/agent/backtest/{backtest_id}")
        assert response.status_code == 200
        payload = BacktestJobResponse.model_validate(response.json())
        if payload.status in {"completed", "failed"}:
            return payload
        sleep(0.01)
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
