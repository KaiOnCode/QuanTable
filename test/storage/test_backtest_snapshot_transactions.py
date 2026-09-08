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
    first_payload = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":["Open","High","Low","Close","Volume"],"rows":[["2025-01-02","99","101","98","100","1000"]]}}'
    second_payload = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":["Open","High","Low","Close","Volume"],"rows":[["2025-01-02","100","102","99","101","1000"]]}}'
    first_snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(first_payload).hexdigest(),
        payload=gzip.compress(first_payload, mtime=0),
        uncompressed_bytes=len(first_payload),
        row_count_target=1,
        row_count_benchmark=0,
    )
    second_snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(second_payload).hexdigest(),
        payload=gzip.compress(second_payload, mtime=0),
        uncompressed_bytes=len(second_payload),
        row_count_target=1,
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


def test_context_store_rejects_unknown_snapshot_provenance_fields(
    tmp_path: Path,
) -> None:
    store = ContextStore(tmp_path / "data")
    payload = b'{"benchmark":{"columns":[],"rows":[]},"data_provenance":{"benchmark":{"provider":"yfinance"},"target":{"api_key":"SECRET"}},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(payload).hexdigest(),
        payload=gzip.compress(payload, mtime=0),
        uncompressed_bytes=len(payload),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        store.create_backtest_job(
            "job-secret", "{}", '{"contract_version":"backtest-run/v1"}'
        )

        with pytest.raises(RuntimeError, match="provenance is invalid"):
            store.bind_backtest_input_snapshot("job-secret", snapshot)

        assert b"SECRET" not in b"".join(
            bytes(row[0])
            for row in store._system_db()
            .execute("SELECT payload FROM backtest_input_snapshots")
            .fetchall()
        )
    finally:
        store.close()
