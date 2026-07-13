from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from storage.store import BacktestInputSnapshotContent, ContextStore


_MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
_CANONICAL = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'


def _physically_consistent_noncanonical(kind: str) -> tuple[bytes, int, int]:
    if kind == "whitespace":
        return (
            b'{"benchmark": {"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}',
            0,
            0,
        )
    if kind == "reordered_keys":
        return (
            b'{"schema_version":1,"target":{"columns":[],"rows":[]},"benchmark":{"columns":[],"rows":[]}}',
            0,
            0,
        )
    return (
        b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":["Open","High","Low","Close","Volume"],"rows":[["2024-01-02",100,101,99,100.5,1000]]}}',
        1,
        0,
    )


def _oversized_canonical() -> bytes:
    return json.dumps(
        {
            "benchmark": {"columns": [], "rows": []},
            "data_provenance": {
                "benchmark": {},
                "target": {"library_version": "x" * _MAX_SNAPSHOT_BYTES},
            },
            "schema_version": 1,
            "target": {"columns": [], "rows": []},
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _snapshot(
    canonical: bytes,
    *,
    payload: bytes | None = None,
    uncompressed_bytes: int | None = None,
) -> BacktestInputSnapshotContent:
    return BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0) if payload is None else payload,
        uncompressed_bytes=(
            len(canonical) if uncompressed_bytes is None else uncompressed_bytes
        ),
        row_count_target=0,
        row_count_benchmark=0,
    )


def _create_job(tmp_path: Path, job_id: str) -> ContextStore:
    store = ContextStore(tmp_path / "data")
    store.create_backtest_job(job_id, "{}", '{"contract_version":"backtest-run/v1"}')
    return store


def test_context_store_rejects_snapshot_exceeding_uncompressed_limit_before_binding(
    tmp_path: Path,
) -> None:
    # Given: a valid highly compressible snapshot exceeds 16 MiB.
    canonical = _oversized_canonical()
    snapshot = _snapshot(canonical)
    store = _create_job(tmp_path, "job-oversized")
    try:
        # When: the caller attempts to bind the compressed snapshot.
        with pytest.raises(RuntimeError, match="uncompressed byte count"):
            store.bind_backtest_input_snapshot("job-oversized", snapshot)

        # Then: the rejected content has not been bound or persisted.
        job = store.get_backtest_job("job-oversized")
        assert job is not None
        assert job.input_snapshot_hash is None
        assert store.get_backtest_input_snapshot(snapshot.content_hash) is None
    finally:
        store.close()


@pytest.mark.parametrize(
    "payload",
    [b"not-a-gzip-stream", gzip.compress(b"{}", mtime=0)[:-4]],
    ids=["malformed", "truncated"],
)
def test_context_store_normalizes_invalid_gzip_to_runtime_error_before_binding(
    tmp_path: Path,
    payload: bytes,
) -> None:
    # Given: a v1 job and an invalid gzip snapshot envelope.
    snapshot = _snapshot(b"{}", payload=payload)
    store = _create_job(tmp_path, "job-invalid-gzip")
    try:
        # When: the caller attempts to bind malformed or truncated compressed bytes.
        with pytest.raises(RuntimeError, match="gzip payload"):
            store.bind_backtest_input_snapshot("job-invalid-gzip", snapshot)

        # Then: the public storage boundary remains typed and the job stays unbound.
        job = store.get_backtest_job("job-invalid-gzip")
        assert job is not None
        assert job.input_snapshot_hash is None
    finally:
        store.close()


def test_context_store_rejects_trailing_bytes_after_gzip_member_before_binding(
    tmp_path: Path,
) -> None:
    # Given: a valid canonical snapshot followed by gzip-ignored padding.
    snapshot = _snapshot(_CANONICAL, payload=gzip.compress(_CANONICAL) + b"\x00")
    store = _create_job(tmp_path, "job-trailing-gzip")
    try:
        # When: the caller attempts to bind the non-canonical gzip envelope.
        with pytest.raises(RuntimeError, match="gzip payload"):
            store.bind_backtest_input_snapshot("job-trailing-gzip", snapshot)

        # Then: trailing bytes are rejected without binding the job.
        job = store.get_backtest_job("job-trailing-gzip")
        assert job is not None
        assert job.input_snapshot_hash is None
    finally:
        store.close()


def test_context_store_bounds_actual_gzip_output_before_byte_count_validation(
    tmp_path: Path,
) -> None:
    # Given: compressed content expands beyond 16 MiB while claiming an in-range size.
    canonical = _oversized_canonical()
    snapshot = _snapshot(canonical, uncompressed_bytes=_MAX_SNAPSHOT_BYTES)
    store = _create_job(tmp_path, "job-expansion-limit")
    try:
        # When: the caller binds a gzip bomb with misleading size metadata.
        with pytest.raises(RuntimeError, match="exceeds maximum"):
            store.bind_backtest_input_snapshot("job-expansion-limit", snapshot)

        # Then: decompression stops at the storage ceiling and leaves the job unbound.
        job = store.get_backtest_job("job-expansion-limit")
        assert job is not None
        assert job.input_snapshot_hash is None
    finally:
        store.close()


@pytest.mark.parametrize(
    "kind",
    ["whitespace", "reordered_keys", "numeric_ohlcv"],
)
def test_context_store_rejects_physically_consistent_noncanonical_snapshot_on_bind(
    tmp_path: Path,
    kind: str,
) -> None:
    # Given: gzip, hash, byte counts, and row counts agree with non-canonical JSON bytes.
    raw, target_count, benchmark_count = _physically_consistent_noncanonical(kind)
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(raw).hexdigest(),
        payload=gzip.compress(raw, mtime=0),
        uncompressed_bytes=len(raw),
        row_count_target=target_count,
        row_count_benchmark=benchmark_count,
    )
    job_id = f"job-noncanonical-{kind}"
    store = _create_job(tmp_path, job_id)
    try:
        # When: the caller binds bytes that are self-consistent but not canonical v1 JSON.
        with pytest.raises(RuntimeError, match="canonical JSON"):
            store.bind_backtest_input_snapshot(job_id, snapshot)

        # Then: canonicality is enforced before the job is bound.
        job = store.get_backtest_job(job_id)
        assert job is not None
        assert job.input_snapshot_hash is None
    finally:
        store.close()
