from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

import pytest

from storage.store import (
    BacktestDecisionEvidence,
    BacktestInputSnapshotContent,
    ContextStore,
)


def test_context_store_keeps_same_sequence_decisions_isolated_by_job_id(
    tmp_path: Path,
) -> None:
    # Given: two v1 jobs share the same frozen snapshot but have independent decision streams.
    store = ContextStore(tmp_path / "data")
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        for job_id in ("job-c", "job-d"):
            store.create_backtest_job(
                job_id, "{}", '{"contract_version":"backtest-run/v1"}'
            )
            store.bind_backtest_input_snapshot(job_id, snapshot)

        # When: both jobs persist their first decision sequence number.
        assert store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-c",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date=None,
                status="completed",
                attempts=1,
                target_position_pct=25.0,
                confidence=0.7,
                action="BUY",
                rationale="enter target",
                feature_hash=None,
                policy_hash="c" * 64,
                error_code=None,
                error_stage=None,
            )
        )
        assert store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-d",
                sequence=1,
                signal_date="2025-01-03T00:00:00Z",
                execution_date=None,
                status="failed",
                attempts=2,
                target_position_pct=None,
                confidence=None,
                action=None,
                rationale=None,
                feature_hash=None,
                policy_hash="d" * 64,
                error_code="decision_schema_invalid",
                error_stage="structured_output",
            )
        )

        store.close()
        store = ContextStore(tmp_path / "data")

        # Then: restart reads each job's action and rationale from its isolated row.
        job_c = store.get_backtest_decisions("job-c")
        job_d = store.get_backtest_decisions("job-d")
        assert [(item.job_id, item.sequence, item.status) for item in job_c] == [
            ("job-c", 1, "completed")
        ]
        assert (job_c[0].action, job_c[0].rationale) == ("BUY", "enter target")
        assert [(item.job_id, item.sequence, item.status) for item in job_d] == [
            ("job-d", 1, "failed")
        ]
    finally:
        store.close()


def test_context_store_raises_runtime_error_for_corrupt_persisted_decision_status(
    tmp_path: Path,
) -> None:
    # Given: a bound job whose otherwise valid decision row has a corrupt status.
    store = ContextStore(tmp_path / "data")
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        store.create_backtest_job(
            "job-corrupt-status", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        store.bind_backtest_input_snapshot("job-corrupt-status", snapshot)
        store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-corrupt-status",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date=None,
                status="completed",
                attempts=1,
                target_position_pct=25.0,
                confidence=0.7,
                action="BUY",
                rationale="enter target",
                feature_hash=None,
                policy_hash="c" * 64,
                error_code=None,
                error_stage=None,
            )
        )
        db = store._system_db()
        db.execute(
            "UPDATE backtest_decisions SET status = 'corrupt' "
            "WHERE job_id = 'job-corrupt-status' AND sequence = 1"
        )
        db.commit()

        # When: a caller reads decisions through the public ContextStore boundary.
        with pytest.raises(
            RuntimeError, match="invalid persisted backtest decision status"
        ):
            store.get_backtest_decisions("job-corrupt-status")

        # Then: corrupt persisted status remains a deterministic RuntimeError boundary.
    finally:
        store.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [("sequence", 1.5), ("sequence", 0), ("attempts", "not-integer"), ("attempts", 0)],
)
def test_context_store_rejects_invalid_persisted_decision_integers(
    tmp_path: Path, field: str, value: str | float | int
) -> None:
    # Given: a valid decision row is corrupted at an integer field.
    store = ContextStore(tmp_path / "data")
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        store.create_backtest_job(
            "job-corrupt-integer", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        store.bind_backtest_input_snapshot("job-corrupt-integer", snapshot)
        store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-corrupt-integer",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date=None,
                status="completed",
                attempts=1,
                target_position_pct=25.0,
                confidence=0.7,
                feature_hash=None,
                policy_hash="c" * 64,
                error_code=None,
                error_stage=None,
                action="BUY",
                rationale="enter target",
            )
        )
        database = store._system_db()
        database.execute(
            f"UPDATE backtest_decisions SET {field} = ? WHERE job_id = ?",
            (value, "job-corrupt-integer"),
        )
        database.commit()

        # When / Then: the read rejects truncation and invalid decision domains.
        with pytest.raises(RuntimeError, match="decision metadata is invalid"):
            store.get_backtest_decisions("job-corrupt-integer")
    finally:
        store.close()


@pytest.mark.parametrize(
    "field",
    ["signal_date", "execution_date", "rationale", "feature_hash", "policy_hash"],
)
def test_context_store_rejects_blob_persisted_decision_text(
    tmp_path: Path, field: str
) -> None:
    # Given: a BLOB has crossed a required or nullable decision TEXT column.
    store = ContextStore(tmp_path / "data")
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        store.create_backtest_job(
            "job-blob-decision", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        store.bind_backtest_input_snapshot("job-blob-decision", snapshot)
        store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-blob-decision",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date="2025-01-03T00:00:00Z",
                status="completed",
                attempts=1,
                target_position_pct=25.0,
                confidence=0.7,
                action="BUY",
                rationale="enter target",
                feature_hash="f" * 64,
                policy_hash="c" * 64,
                error_code=None,
                error_stage=None,
            )
        )
        database = store._system_db()
        database.execute(
            f"UPDATE backtest_decisions SET {field} = ? WHERE job_id = ?",
            (b"blob-text", "job-blob-decision"),
        )
        database.commit()

        # When / Then: strict projection rejects the BLOB instead of stringifying it.
        with pytest.raises(RuntimeError, match="decision metadata is invalid"):
            store.get_backtest_decisions("job-blob-decision")
    finally:
        store.close()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_position_pct", "NaN"),
        ("confidence", b"0.5"),
        ("target_position_pct", -1.0),
        ("confidence", 1.5),
        ("confidence", float("inf")),
    ],
)
def test_context_store_rejects_invalid_persisted_decision_reals(
    tmp_path: Path, field: str, value: str | bytes | float
) -> None:
    # Given: decision REAL metadata has a coercible wrong type or invalid value.
    store = ContextStore(tmp_path / "data")
    canonical = b'{"benchmark":{"columns":[],"rows":[]},"schema_version":1,"target":{"columns":[],"rows":[]}}'
    snapshot = BacktestInputSnapshotContent(
        content_hash=hashlib.sha256(canonical).hexdigest(),
        payload=gzip.compress(canonical, mtime=0),
        uncompressed_bytes=len(canonical),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        store.create_backtest_job(
            "job-invalid-real", "{}", '{"contract_version":"backtest-run/v1"}'
        )
        store.bind_backtest_input_snapshot("job-invalid-real", snapshot)
        store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-invalid-real",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date=None,
                status="completed",
                attempts=1,
                target_position_pct=25.0,
                confidence=0.7,
                action="BUY",
                rationale="enter target",
                feature_hash=None,
                policy_hash="c" * 64,
                error_code=None,
                error_stage=None,
            )
        )
        database = store._system_db()
        database.execute(
            f"UPDATE backtest_decisions SET {field} = ? WHERE job_id = ?",
            (value, "job-invalid-real"),
        )
        database.commit()

        # When / Then: no string/BLOB coercion or nonfinite/out-of-domain REAL escapes.
        with pytest.raises(RuntimeError, match="decision metadata is invalid"):
            store.get_backtest_decisions("job-invalid-real")
    finally:
        store.close()
