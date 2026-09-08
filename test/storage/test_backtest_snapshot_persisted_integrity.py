from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from storage.store import BacktestInputSnapshotContent, ContextStore


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


def _snapshot() -> BacktestInputSnapshotContent:
    return BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(_CANONICAL).hexdigest(),
        payload=gzip.compress(_CANONICAL, mtime=0),
        uncompressed_bytes=len(_CANONICAL),
        row_count_target=0,
        row_count_benchmark=0,
    )


def _bound_store(
    tmp_path: Path, job_id: str
) -> tuple[ContextStore, BacktestInputSnapshotContent]:
    store = ContextStore(tmp_path / "data")
    snapshot = _snapshot()
    store.create_backtest_job(job_id, "{}", '{"contract_version":"backtest-run/v1"}')
    store.bind_backtest_input_snapshot(job_id, snapshot)
    return store, snapshot


@pytest.mark.parametrize(
    "field",
    ["request_json", "run_spec_json", "created_at", "started_at", "updated_at"],
)
def test_context_store_rejects_blob_persisted_job_text(
    tmp_path: Path, field: str
) -> None:
    # Given: a BLOB has crossed a required or nullable backtest job TEXT column.
    store = ContextStore(tmp_path / "data")
    try:
        store.create_backtest_job(
            "job-blob-text", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        database = store._system_db()
        database.execute(
            f"UPDATE backtest_jobs SET {field} = ? WHERE id = ?",
            (b"blob-text", "job-blob-text"),
        )
        database.commit()

        # When / Then: strict row projection rejects it instead of exposing b'...'.
        with pytest.raises(RuntimeError, match="job metadata is invalid"):
            store.get_backtest_job("job-blob-text")
    finally:
        store.close()


@pytest.mark.parametrize("field", ["codec", "created_at"])
def test_context_store_rejects_blob_persisted_snapshot_text(
    tmp_path: Path, field: str
) -> None:
    # Given: a BLOB has crossed snapshot TEXT metadata.
    store, snapshot = _bound_store(tmp_path, f"job-blob-snapshot-{field}")
    try:
        database = store._system_db()
        database.execute("PRAGMA ignore_check_constraints = ON")
        database.execute(
            f"UPDATE backtest_input_snapshots SET {field} = ? WHERE content_hash = ?",
            (b"blob-text", snapshot.content_hash),
        )
        database.commit()
        database.execute("PRAGMA ignore_check_constraints = OFF")

        # When / Then: the snapshot boundary rejects non-TEXT metadata.
        with pytest.raises(RuntimeError, match="snapshot metadata is invalid"):
            store.get_backtest_input_snapshot(snapshot.content_hash)
    finally:
        store.close()


@pytest.mark.parametrize("contract_version", ["not-integer", 1.5, 2])
def test_context_store_rejects_non_v1_persisted_contract_on_bind(
    tmp_path: Path, contract_version: str | float | int
) -> None:
    # Given: an unbound job has non-strict or out-of-domain persisted contract metadata.
    store, snapshot = _bound_store(tmp_path, "job-valid-source")
    try:
        store.create_backtest_job(
            "job-corrupt-contract", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        database = store._system_db()
        database.execute(
            "UPDATE backtest_jobs SET contract_version = ? WHERE id = ?",
            (contract_version, "job-corrupt-contract"),
        )
        database.commit()

        # When / Then: binding rejects corruption as RuntimeError before snapshot writes.
        with pytest.raises(RuntimeError):
            store.bind_backtest_input_snapshot("job-corrupt-contract", snapshot)
    finally:
        store.close()


@pytest.mark.parametrize("contract_version", [1.5, 2])
def test_context_store_rejects_invalid_persisted_job_contract_on_get(
    tmp_path: Path, contract_version: float | int
) -> None:
    # Given: a persisted job contract is fractional or outside the v1 domain.
    store = ContextStore(tmp_path / "data")
    try:
        store.create_backtest_job(
            "job-corrupt-contract", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        database = store._system_db()
        database.execute(
            "UPDATE backtest_jobs SET contract_version = ? WHERE id = ?",
            (contract_version, "job-corrupt-contract"),
        )
        database.commit()

        # When / Then: the public job read rejects the corrupt scalar deterministically.
        with pytest.raises(RuntimeError, match="job metadata is invalid"):
            store.get_backtest_job("job-corrupt-contract")
    finally:
        store.close()


def test_context_store_rejects_persisted_snapshot_with_wrong_compressed_byte_count(
    tmp_path: Path,
) -> None:
    # Given: a bound snapshot whose persisted compressed byte count is corrupted.
    store, snapshot = _bound_store(tmp_path, "job-corrupt-compressed-size")
    try:
        db = store._system_db()
        db.execute(
            "UPDATE backtest_input_snapshots SET compressed_bytes = compressed_bytes + 1 "
            "WHERE content_hash = ?",
            (snapshot.content_hash,),
        )
        db.commit()

        # When: a caller reads the corrupted persisted snapshot.
        with pytest.raises(RuntimeError, match="compressed byte count"):
            store.get_backtest_input_snapshot(snapshot.content_hash)

        # Then: no untrusted record is projected through the public storage boundary.
    finally:
        store.close()


def test_context_store_rejects_persisted_snapshot_with_wrong_uncompressed_byte_count(
    tmp_path: Path,
) -> None:
    # Given: a bound snapshot whose persisted uncompressed byte count is corrupted.
    store, snapshot = _bound_store(tmp_path, "job-corrupt-uncompressed-size")
    try:
        db = store._system_db()
        db.execute(
            "UPDATE backtest_input_snapshots "
            "SET uncompressed_bytes = uncompressed_bytes + 1 WHERE content_hash = ?",
            (snapshot.content_hash,),
        )
        db.commit()

        # When: a caller reads the corrupted persisted snapshot.
        with pytest.raises(RuntimeError, match="uncompressed byte count"):
            store.get_backtest_input_snapshot(snapshot.content_hash)

        # Then: metadata that disagrees with actual output is rejected.
    finally:
        store.close()


@pytest.mark.parametrize(
    ("statement", "job_id"),
    [
        (
            "UPDATE backtest_input_snapshots SET compressed_bytes = 'not-integer' "
            "WHERE content_hash = ?",
            "job-non-integer-compressed-size",
        ),
        (
            "UPDATE backtest_input_snapshots SET uncompressed_bytes = 'not-integer' "
            "WHERE content_hash = ?",
            "job-non-integer-uncompressed-size",
        ),
    ],
    ids=["compressed-bytes", "uncompressed-bytes"],
)
def test_context_store_normalizes_non_integer_persisted_snapshot_metadata(
    tmp_path: Path,
    statement: str,
    job_id: str,
) -> None:
    # Given: a bound snapshot whose persisted size metadata is not an integer.
    store, snapshot = _bound_store(tmp_path, job_id)
    try:
        db = store._system_db()
        db.execute(statement, (snapshot.content_hash,))
        db.commit()

        # When: a caller reads the malformed persisted snapshot row.
        with pytest.raises(RuntimeError, match="snapshot metadata is invalid"):
            store.get_backtest_input_snapshot(snapshot.content_hash)

        # Then: the public storage boundary does not leak int conversion errors.
    finally:
        store.close()


@pytest.mark.parametrize(
    "field",
    ["schema_version", "row_count_target", "row_count_benchmark"],
)
def test_context_store_normalizes_non_integer_snapshot_scalar_metadata(
    tmp_path: Path, field: str
) -> None:
    # Given: a persisted snapshot scalar crosses SQLite's dynamic typing boundary.
    store, snapshot = _bound_store(tmp_path, f"job-non-integer-{field}")
    try:
        db = store._system_db()
        db.execute("PRAGMA ignore_check_constraints = ON")
        db.execute(
            f"UPDATE backtest_input_snapshots SET {field} = 'not-integer' WHERE content_hash = ?",
            (snapshot.content_hash,),
        )
        db.commit()
        db.execute("PRAGMA ignore_check_constraints = OFF")

        # When / Then: callers receive deterministic storage corruption, never ValueError.
        with pytest.raises(RuntimeError, match="snapshot metadata is invalid"):
            store.get_backtest_input_snapshot(snapshot.content_hash)
    finally:
        store.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 1.5),
        ("schema_version", 2),
        ("compressed_bytes", 1.5),
        ("uncompressed_bytes", -1),
        ("row_count_target", 1.5),
        ("row_count_benchmark", -1),
    ],
)
def test_context_store_rejects_fractional_or_out_of_domain_snapshot_integers(
    tmp_path: Path, field: str, value: float | int
) -> None:
    # Given: a persisted snapshot integer is fractional or violates its domain.
    store, snapshot = _bound_store(tmp_path, f"job-invalid-{field}")
    try:
        database = store._system_db()
        database.execute("PRAGMA ignore_check_constraints = ON")
        database.execute(
            f"UPDATE backtest_input_snapshots SET {field} = ? WHERE content_hash = ?",
            (value, snapshot.content_hash),
        )
        database.commit()
        database.execute("PRAGMA ignore_check_constraints = OFF")

        # When / Then: no coercion or truncation crosses the storage boundary.
        with pytest.raises(RuntimeError, match="snapshot metadata is invalid"):
            store.get_backtest_input_snapshot(snapshot.content_hash)
    finally:
        store.close()


def test_context_store_rejects_non_blob_snapshot_payload_before_bytes_conversion(
    tmp_path: Path,
) -> None:
    # Given: an INTEGER has replaced the persisted snapshot BLOB.
    store, snapshot = _bound_store(tmp_path, "job-integer-payload")
    try:
        database = store._system_db()
        database.execute(
            "UPDATE backtest_input_snapshots SET payload = 8 WHERE content_hash = ?",
            (snapshot.content_hash,),
        )
        database.commit()

        # When / Then: the boundary rejects it without allocating bytes from the integer.
        with pytest.raises(RuntimeError, match="snapshot metadata is invalid"):
            store.get_backtest_input_snapshot(snapshot.content_hash)
    finally:
        store.close()


def test_context_store_rejects_persisted_snapshot_with_wrong_content_hash(
    tmp_path: Path,
) -> None:
    # Given: persisted bytes and counts agree but violate the content address.
    store, snapshot = _bound_store(tmp_path, "job-corrupt-content-hash")
    try:
        tampered = _CANONICAL.replace(b'"target"', b'"targeX"')
        tampered_gzip = gzip.compress(tampered, mtime=0)
        db = store._system_db()
        db.execute(
            "UPDATE backtest_input_snapshots SET payload = ?, compressed_bytes = ?, "
            "uncompressed_bytes = ? WHERE content_hash = ?",
            (tampered_gzip, len(tampered_gzip), len(tampered), snapshot.content_hash),
        )
        db.commit()

        # When: a caller reads the tampered persisted snapshot.
        with pytest.raises(RuntimeError, match="content hash"):
            store.get_backtest_input_snapshot(snapshot.content_hash)

        # Then: bytes that do not match their address are not returned.
    finally:
        store.close()


def test_context_store_rolls_back_binding_when_same_hash_snapshot_is_corrupt(
    tmp_path: Path,
) -> None:
    # Given: an existing content address is corrupt and a second job is unbound.
    store, snapshot = _bound_store(tmp_path, "job-existing-snapshot")
    try:
        store.create_backtest_job(
            "job-stale-binding", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        db = store._system_db()
        db.execute(
            "UPDATE backtest_input_snapshots SET compressed_bytes = compressed_bytes + 1 "
            "WHERE content_hash = ?",
            (snapshot.content_hash,),
        )
        db.commit()

        # When: the second job attempts to bind valid content at the corrupt address.
        with pytest.raises(RuntimeError, match="compressed byte count"):
            store.bind_backtest_input_snapshot("job-stale-binding", snapshot)

        # Then: validation precedes commit, so the second job remains unbound.
        job = store.get_backtest_job("job-stale-binding")
        assert job is not None
        assert job.input_snapshot_hash is None
    finally:
        store.close()


@pytest.mark.parametrize(
    "kind",
    ["whitespace", "reordered_keys", "numeric_ohlcv"],
)
def test_context_store_rejects_physically_consistent_noncanonical_snapshot_on_read(
    tmp_path: Path,
    kind: str,
) -> None:
    # Given: a raw database row whose envelope and address agree with non-canonical JSON.
    store = ContextStore(tmp_path / "data")
    store._init_backtest_jobs_db()
    raw, target_count, benchmark_count = _physically_consistent_noncanonical(kind)
    content_hash = hashlib.sha256(raw).hexdigest()
    compressed = gzip.compress(raw, mtime=0)
    database = store._system_db()
    database.execute(
        """INSERT INTO backtest_input_snapshots
           (content_hash, schema_version, codec, payload, compressed_bytes,
            uncompressed_bytes, row_count_target, row_count_benchmark, created_at)
           VALUES (?, 1, 'gzip-json-v1', ?, ?, ?, ?, ?, '2026-07-14T00:00:00Z')""",
        (
            content_hash,
            compressed,
            len(compressed),
            len(raw),
            target_count,
            benchmark_count,
        ),
    )
    database.commit()
    try:
        # When: the public raw-DB read boundary decodes the self-consistent row.
        with pytest.raises(RuntimeError, match="canonical JSON"):
            store.get_backtest_input_snapshot(content_hash)

        # Then: no non-canonical snapshot record crosses the storage boundary.
    finally:
        store.close()
