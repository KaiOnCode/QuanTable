from __future__ import annotations

import gzip
import hashlib
import sqlite3
from pathlib import Path

import pytest

from storage.store import (
    BacktestDecisionEvidence,
    BacktestInputSnapshotContent,
    ContextStore,
)


def test_context_store_migrates_legacy_backtest_jobs_to_exact_v1_contract(
    tmp_path: Path,
) -> None:
    # Given: a durable pre-v1 database with a completed legacy job.
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
            "(id, request_json, status, result_json, error_json, created_at, started_at, completed_at, updated_at) "
            "VALUES ('legacy-job', '{}', 'completed', '{\"legacy\": true}', NULL, "
            "'2024-01-01T00:00:00+00:00', NULL, '2024-01-01T00:00:00+00:00', "
            "'2024-01-01T00:00:00+00:00')"
        )

    store = ContextStore(data_dir)
    try:
        # When: the store opens the legacy database through its public job read seam.
        legacy = store.get_backtest_job("legacy-job")
        db = store._system_db()

        # Then: the fixed v1 migration is recorded, exact columns exist, and foreign keys are enforced.
        assert legacy is not None
        assert legacy.contract_version == 0
        assert legacy.run_spec_json is None
        assert legacy.input_snapshot_hash is None
        assert legacy.progress_json is None
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()[0]
            == "20260712_backtest_contract_v1"
        )
        assert {
            "contract_version",
            "run_spec_json",
            "input_snapshot_hash",
            "progress_json",
        } <= {
            str(row["name"])
            for row in db.execute("PRAGMA table_info(backtest_jobs)").fetchall()
        }
        assert {
            "content_hash",
            "schema_version",
            "codec",
            "payload",
            "compressed_bytes",
            "uncompressed_bytes",
            "row_count_target",
            "row_count_benchmark",
            "created_at",
        } <= {
            str(row["name"])
            for row in db.execute(
                "PRAGMA table_info(backtest_input_snapshots)"
            ).fetchall()
        }
        assert {
            "job_id",
            "sequence",
            "signal_date",
            "execution_date",
            "status",
            "attempts",
            "target_position_pct",
            "confidence",
            "feature_hash",
            "policy_hash",
            "error_code",
            "error_stage",
            "created_at",
            "updated_at",
        } <= {
            str(row["name"])
            for row in db.execute("PRAGMA table_info(backtest_decisions)").fetchall()
        }
        assert any(
            str(row["table"]) == "backtest_input_snapshots"
            and str(row["from"]) == "input_snapshot_hash"
            for row in db.execute("PRAGMA foreign_key_list(backtest_jobs)").fetchall()
        )
        assert any(
            str(row["table"]) == "backtest_jobs"
            and str(row["from"]) == "job_id"
            and str(row["on_delete"]).upper() == "CASCADE"
            for row in db.execute(
                "PRAGMA foreign_key_list(backtest_decisions)"
            ).fetchall()
        )
    finally:
        store.close()


def test_context_store_binds_snapshot_before_decision_and_cascades_job_evidence(
    tmp_path: Path,
) -> None:
    # Given: a v1 job and one canonical compressed input snapshot.
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
        job = store.create_backtest_job(
            "job-a",
            "{}",
            '{"contract_version":"backtest-run/v1"}',
        )

        # When: the worker binds its snapshot, stores progress, then emits one decision.
        bound = store.bind_backtest_input_snapshot("job-a", snapshot)
        assert store.update_backtest_job_progress("job-a", '{"bars_total":2}')
        assert store.record_backtest_decision(
            BacktestDecisionEvidence(
                job_id="job-a",
                sequence=1,
                signal_date="2025-01-02T00:00:00Z",
                execution_date="2025-01-03T00:00:00Z",
                status="completed",
                attempts=1,
                target_position_pct=50.0,
                confidence=0.9,
                feature_hash=None,
                policy_hash="b" * 64,
                error_code=None,
                error_stage=None,
            )
        )
        with pytest.raises(
            ValueError, match="backtest decision failure metadata is invalid"
        ):
            store.record_backtest_decision(
                BacktestDecisionEvidence(
                    job_id="job-a",
                    sequence=2,
                    signal_date="2025-01-03T00:00:00Z",
                    execution_date=None,
                    status="failed",
                    attempts=1,
                    target_position_pct=None,
                    confidence=None,
                    feature_hash=None,
                    policy_hash="b" * 64,
                    error_code="SECRET_ERROR_CODE",
                    error_stage="SECRET_ERROR_STAGE",
                )
            )

        # Then: the v1 job exposes isolated evidence, rejects invalid FK rows, and leaves retained data after cascade.
        persisted = store.get_backtest_job("job-a")
        assert job.contract_version == 1
        assert bound.content_hash == snapshot.content_hash
        assert persisted is not None
        assert persisted.input_snapshot_hash == snapshot.content_hash
        assert persisted.progress_json == '{"bars_total":2}'
        assert [
            decision.sequence for decision in store.get_backtest_decisions("job-a")
        ] == [1]
        db = store._system_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO backtest_decisions "
                "(job_id, sequence, signal_date, execution_date, status, attempts, target_position_pct, confidence, feature_hash, policy_hash, error_code, error_stage, created_at, updated_at) "
                "VALUES ('missing-job', 1, '2025-01-02T00:00:00Z', NULL, 'failed', 1, NULL, NULL, NULL, 'b', NULL, NULL, '2025-01-02T00:00:00Z', '2025-01-02T00:00:00Z')"
            )
        db.execute("DELETE FROM backtest_jobs WHERE id = ?", ("job-a",))
        db.commit()
        assert store.get_backtest_decisions("job-a") == []
        assert store.get_backtest_input_snapshot(snapshot.content_hash) is not None
    finally:
        store.close()


def test_context_store_rejects_snapshot_without_matching_content_hash(
    tmp_path: Path,
) -> None:
    # Given: a v1 job and a gzip payload with a deliberately incorrect content address.
    store = ContextStore(tmp_path / "data")
    store.create_backtest_job("job-b", "{}", '{"contract_version":"backtest-run/v1"}')
    snapshot = BacktestInputSnapshotContent(
        content_hash="0" * 64,
        payload=gzip.compress(b'{"schema_version":1}', mtime=0),
        uncompressed_bytes=len(b'{"schema_version":1}'),
        row_count_target=0,
        row_count_benchmark=0,
    )
    try:
        # When: the worker tries to bind content that does not match its claimed hash.
        with pytest.raises(RuntimeError, match="content hash"):
            store.bind_backtest_input_snapshot("job-b", snapshot)

        # Then: the job remains unbound and cannot begin a decision sequence.
        job = store.get_backtest_job("job-b")
        assert job is not None
        assert job.input_snapshot_hash is None
        with pytest.raises(RuntimeError, match="bound input snapshot"):
            store.record_backtest_decision(
                BacktestDecisionEvidence(
                    job_id="job-b",
                    sequence=1,
                    signal_date="2025-01-02T00:00:00Z",
                    execution_date=None,
                    status="failed",
                    attempts=1,
                    target_position_pct=None,
                    confidence=None,
                    feature_hash=None,
                    policy_hash="b" * 64,
                    error_code="decision_schema_invalid",
                    error_stage="structured_output",
                )
            )
    finally:
        store.close()
