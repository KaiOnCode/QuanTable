from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from storage.store import BacktestInputSnapshotContent, ContextStore


def test_context_store_releases_write_transaction_after_conflicting_snapshot(
    tmp_path: Path,
) -> None:
    # Given: one v1 job has bound a content-addressed snapshot and another job is ready.
    store = ContextStore(tmp_path / "data")
    first_payload = b'{"schema_version":1,"value":"first"}'
    second_payload = b'{"schema_version":1,"value":"second"}'
    first_snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(first_payload).hexdigest(),
        payload=gzip.compress(first_payload, mtime=0),
        uncompressed_bytes=len(first_payload),
        row_count_target=0,
        row_count_benchmark=0,
    )
    second_snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(second_payload).hexdigest(),
        payload=gzip.compress(second_payload, mtime=0),
        uncompressed_bytes=len(second_payload),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        for job_id in ("job-a", "job-b"):
            store.create_backtest_job(
                job_id, "{}", '{"contract_version":"backtest-run/v1"}'
            )
        store.bind_backtest_input_snapshot("job-a", first_snapshot)

        # When: a conflicting snapshot is rejected for the already-bound job.
        with pytest.raises(RuntimeError, match="different frozen snapshot"):
            store.bind_backtest_input_snapshot("job-a", second_snapshot)

        # Then: the failed binding has rolled back, so another job can bind immediately.
        bound = store.bind_backtest_input_snapshot("job-b", second_snapshot)
        assert bound.content_hash == second_snapshot.content_hash
    finally:
        store.close()


def test_context_store_refuses_v1_completion_without_bound_snapshot(
    tmp_path: Path,
) -> None:
    # Given: a running v1 job has a frozen run spec but no normalized input snapshot.
    store = ContextStore(tmp_path / "data")
    try:
        store.create_backtest_job(
            "job-unbound", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        assert store.mark_backtest_job_running("job-unbound")

        # When: a caller attempts to complete the job through the persistence owner.
        completed = store.complete_backtest_job("job-unbound", "{}")

        # Then: the v1 invariant keeps the job running until a snapshot is bound.
        assert completed is False
        job = store.get_backtest_job("job-unbound")
        assert job is not None
        assert job.status == "running"
    finally:
        store.close()
