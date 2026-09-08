from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from storage.store import BacktestJobRecord, ContextStore


def test_backtest_jobs_migration_is_safe_for_concurrent_initializers(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "system.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE backtest_jobs ("
            "id TEXT PRIMARY KEY, "
            "request_json TEXT NOT NULL, "
            "status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')), "
            "result_json TEXT, "
            "error_json TEXT, "
            "created_at TEXT NOT NULL, "
            "started_at TEXT, "
            "completed_at TEXT, "
            "updated_at TEXT NOT NULL"
            ")"
        )
        db.execute(
            "INSERT INTO backtest_jobs "
            "(id, request_json, status, result_json, error_json, "
            "created_at, started_at, completed_at, updated_at) "
            "VALUES ('legacy-job', '{}', 'pending', NULL, NULL, "
            "'2024-01-01T00:00:00+00:00', NULL, NULL, "
            "'2024-01-01T00:00:00+00:00')"
        )

    initializer_count = 16
    arrivals = Barrier(initializer_count)

    def initialize_and_read() -> BacktestJobRecord:
        store = ContextStore(data_dir)
        try:
            store._system_db()
            arrivals.wait(timeout=5)
            store._init_backtest_jobs_db()
            job = store.get_backtest_job("legacy-job")
            if job is None:
                raise AssertionError("legacy job disappeared during migration")
            return job
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=initializer_count) as executor:
        jobs = tuple(
            executor.map(lambda _: initialize_and_read(), range(initializer_count))
        )

    assert len(jobs) == initializer_count
    assert all(job.id == "legacy-job" for job in jobs)
    assert all(job.contract_version == 0 for job in jobs)
    assert all(job.run_spec_json is None for job in jobs)
    assert all(job.input_snapshot_hash is None for job in jobs)
    assert all(job.progress_json is None for job in jobs)
    assert all(job.status == "pending" for job in jobs)
    with sqlite3.connect(db_path) as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()[0]
            == 1
        )
