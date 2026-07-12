from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Lock

import anyio
import pytest
from fastapi.testclient import TestClient

from reporting.models import ReportStatus, ReportType
from reporting.repository import ReportRepository
from server import main
from server.routes import reports
from storage.store import ContextStore


def test_lifespan_recovers_interrupted_reports_before_read_only_get(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Given: a running report persisted before a process restart.
    store = ContextStore(tmp_path / "data")
    repository = ReportRepository(store, tmp_path / "artifacts")
    running = repository.create(
        report_type=ReportType.STOCK,
        title="Interrupted",
        tickers=("AAPL",),
        source_type="analysis",
        source_ids=("analysis-1",),
        parameters={},
    )
    assert repository.mark_running(running.id)
    monkeypatch.setattr(main, "recover_interrupted_backtest_jobs", lambda: 0)
    monkeypatch.setattr(
        main,
        "recover_interrupted_report_jobs",
        store.recover_interrupted_report_jobs,
        raising=False,
    )
    main.app.dependency_overrides[reports.get_report_repository] = lambda: repository

    # When: the restarted API serves only a read request, without constructing ReportService.
    try:
        with TestClient(main.app) as client:
            response = client.get(f"/api/reports/{running.id}")
    finally:
        main.app.dependency_overrides.clear()

    # Then: startup recovery has already made the interrupted job terminal.
    assert response.status_code == 200
    assert response.json()["status"] == ReportStatus.FAILED
    store.close()


def test_lifespan_releases_cached_job_services_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.routes import agent

    # Given: lifecycle cleanup callbacks that record executor-owner release.
    released: list[str] = []
    monkeypatch.setattr(main, "recover_interrupted_backtest_jobs", lambda: 0)
    monkeypatch.setattr(
        main, "recover_interrupted_report_jobs", lambda: 0, raising=False
    )
    monkeypatch.setattr(
        agent, "shutdown_backtest_job_service", lambda: released.append("backtest")
    )
    monkeypatch.setattr(
        reports,
        "shutdown_report_service",
        lambda: released.append("report"),
    )

    # When: the FastAPI lifespan exits normally.
    with TestClient(main.app):
        pass

    # Then: both cached executor owners are released exactly once.
    assert released == ["backtest", "report"]


def test_lifespan_releases_cached_job_services_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.routes import agent

    # Given: lifecycle cleanup callbacks and a healthy application startup.
    released: list[str] = []
    monkeypatch.setattr(main, "recover_interrupted_backtest_jobs", lambda: 0)
    monkeypatch.setattr(main, "recover_interrupted_report_jobs", lambda: 0)
    monkeypatch.setattr(
        agent, "shutdown_backtest_job_service", lambda: released.append("backtest")
    )
    monkeypatch.setattr(
        reports,
        "shutdown_report_service",
        lambda: released.append("report"),
    )

    async def fail_inside_lifespan() -> None:
        async with main.app.router.lifespan_context(main.app):
            raise RuntimeError("cancel serving")

    # When: the lifespan context itself exits through an exception.
    with pytest.raises(RuntimeError, match="cancel serving"):
        anyio.run(fail_inside_lifespan)

    # Then: executor owners are still released exactly once.
    assert released == ["backtest", "report"]


def test_report_service_has_one_owner_during_concurrent_first_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.routes import reports

    # Given: two simultaneous first callers and an observable service constructor.
    cache_clear = getattr(reports.get_report_service, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    monkeypatch.setattr(reports, "_report_service", None, raising=False)
    arrivals = Barrier(2)
    counter_lock = Lock()
    created: list[object] = []

    class ServiceOwner:
        def close(self) -> None:
            return None

    def create_service(*args: object, **kwargs: object) -> ServiceOwner:
        owner = ServiceOwner()
        with counter_lock:
            created.append(owner)
        try:
            arrivals.wait(timeout=0.2)
        except BrokenBarrierError:
            pass
        return owner

    monkeypatch.setattr(reports, "ReportService", create_service)

    # When: both callers request the cached executor owner concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        owners = tuple(executor.map(lambda _: reports.get_report_service(), range(2)))

    # Then: exactly one service exists and both callers receive it.
    assert len(created) == 1
    assert owners[0] is owners[1]


def test_backtest_service_has_one_owner_during_concurrent_first_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from server.routes import agent

    # Given: two simultaneous first callers and an observable Backtest service factory.
    monkeypatch.setattr(agent, "_backtest_job_service", None)
    arrivals = Barrier(2)
    counter_lock = Lock()
    created: list[object] = []

    class ServiceOwner:
        def shutdown(self) -> None:
            return None

    def create_service(store: object) -> ServiceOwner:
        owner = ServiceOwner()
        with counter_lock:
            created.append(owner)
        try:
            arrivals.wait(timeout=0.2)
        except BrokenBarrierError:
            pass
        return owner

    monkeypatch.setattr(agent, "default_backtest_job_service", create_service)

    # When: both callers request the cached executor owner concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:
        owners = tuple(
            executor.map(lambda _: agent.get_backtest_job_service(), range(2))
        )

    # Then: exactly one service exists and both callers receive it.
    assert len(created) == 1
    assert owners[0] is owners[1]
