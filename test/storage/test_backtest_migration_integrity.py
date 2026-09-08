from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from storage.store import ContextStore


_EXACT_SCHEMA_MIGRATIONS_SQL = (
    "CREATE TABLE schema_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
)
_EXACT_SNAPSHOT_SQL = (
    "CREATE TABLE backtest_input_snapshots ("
    "content_hash TEXT PRIMARY KEY, schema_version INTEGER NOT NULL CHECK (schema_version = 1), "
    "codec TEXT NOT NULL CHECK (codec = 'gzip-json-v1'), payload BLOB NOT NULL, "
    "compressed_bytes INTEGER NOT NULL, uncompressed_bytes INTEGER NOT NULL, "
    "row_count_target INTEGER NOT NULL, row_count_benchmark INTEGER NOT NULL, "
    "created_at TEXT NOT NULL)"
)
_EXACT_JOBS_SQL = (
    "CREATE TABLE backtest_jobs ("
    "id TEXT PRIMARY KEY, request_json TEXT NOT NULL, "
    "contract_version INTEGER NOT NULL DEFAULT 0, run_spec_json TEXT, "
    "input_snapshot_hash TEXT REFERENCES backtest_input_snapshots(content_hash), "
    "progress_json TEXT, status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')), "
    "result_json TEXT, error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, "
    "completed_at TEXT, updated_at TEXT NOT NULL)"
)
_EXACT_DECISIONS_SQL = (
    "CREATE TABLE backtest_decisions ("
    "job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE, "
    "sequence INTEGER NOT NULL, signal_date TEXT NOT NULL, execution_date TEXT, "
    "status TEXT NOT NULL, attempts INTEGER NOT NULL, target_position_pct REAL, "
    "confidence REAL, feature_hash TEXT, policy_hash TEXT NOT NULL, error_code TEXT, "
    "error_stage TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
    "PRIMARY KEY (job_id, sequence))"
)
_EXACT_DECISIONS_INDEX_SQL = (
    "CREATE INDEX idx_backtest_decisions_job ON backtest_decisions(job_id)"
)


def _replace_schema_fragment(sql: str, before: str, after: str) -> str:
    assert before in sql
    return sql.replace(before, after, 1)


def _write_markerless_exact_v1_schema(
    data_dir: Path,
    target: str | None = None,
    before: str = "",
    after: str = "",
) -> None:
    statements = {
        "migrations": _EXACT_SCHEMA_MIGRATIONS_SQL,
        "snapshot": _EXACT_SNAPSHOT_SQL,
        "jobs": _EXACT_JOBS_SQL,
        "decisions": _EXACT_DECISIONS_SQL,
        "index": _EXACT_DECISIONS_INDEX_SQL,
    }
    if target is not None:
        statements[target] = _replace_schema_fragment(statements[target], before, after)
    data_dir.mkdir()
    with sqlite3.connect(data_dir / "system.db") as db:
        db.execute(statements["migrations"])
        db.execute(statements["snapshot"])
        db.execute(statements["jobs"])
        db.execute(statements["decisions"])
        db.execute(statements["index"])


def test_context_store_refuses_malformed_preexisting_v1_tables_without_marker(
    tmp_path: Path,
) -> None:
    # Given: a legacy jobs table plus malformed snapshot and decision tables without the fixed marker.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "system.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            "CREATE TABLE backtest_jobs ("
            "id TEXT PRIMARY KEY, request_json TEXT NOT NULL, "
            "status TEXT NOT NULL, result_json TEXT, error_json TEXT, "
            "created_at TEXT NOT NULL, started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE backtest_input_snapshots (content_hash TEXT PRIMARY KEY)"
        )
        db.execute("CREATE TABLE backtest_decisions (job_id TEXT NOT NULL)")

    store = ContextStore(data_dir)
    try:
        # When: startup attempts the fixed migration against the malformed preexisting schema.
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            store.get_backtest_job("missing")
    finally:
        store.close()

    # Then: migration rolls back and never records a marker for an inconsistent contract.
    with sqlite3.connect(db_path) as db:
        registry = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        assert registry is None


def test_context_store_certifies_exact_markerless_v1_schema(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_markerless_exact_v1_schema(data_dir)

    store = ContextStore(data_dir)
    try:
        assert store.get_backtest_job("missing") is None
    finally:
        store.close()

    with sqlite3.connect(data_dir / "system.db") as db:
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is not None
        )


def test_context_store_migrates_legacy_base_without_status_check(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    with sqlite3.connect(data_dir / "system.db") as db:
        db.execute(
            "CREATE TABLE backtest_jobs ("
            "id TEXT PRIMARY KEY, request_json TEXT NOT NULL, status TEXT NOT NULL, "
            "result_json TEXT, error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, "
            "completed_at TEXT, updated_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO backtest_jobs "
            "(id, request_json, status, result_json, error_json, created_at, started_at, completed_at, updated_at) "
            "VALUES ('legacy', '{}', 'completed', '{}', NULL, '2025-01-01T00:00:00Z', NULL, "
            "'2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"
        )

    store = ContextStore(data_dir)
    try:
        job = store.get_backtest_job("legacy")
        with pytest.raises(sqlite3.IntegrityError):
            store._system_db().execute(
                "INSERT INTO backtest_jobs "
                "(id, request_json, contract_version, run_spec_json, input_snapshot_hash, progress_json, "
                "status, result_json, error_json, created_at, started_at, completed_at, updated_at) "
                "VALUES ('invalid-v1', '{}', 1, '{}', NULL, NULL, 'arbitrary', NULL, NULL, "
                "'2025-01-01T00:00:00Z', NULL, NULL, '2025-01-01T00:00:00Z')"
            )
    finally:
        store.close()

    assert job is not None
    assert job.contract_version == 0


@pytest.mark.parametrize(
    ("seed_sql", "seed_params"),
    [
        pytest.param(
            "INSERT INTO backtest_jobs "
            "(id, request_json, contract_version, run_spec_json, input_snapshot_hash, progress_json, "
            "status, result_json, error_json, created_at, started_at, completed_at, updated_at) "
            "VALUES (?, '{}', 1, '{}', ?, NULL, 'pending', NULL, NULL, '2025-01-01T00:00:00Z', "
            "NULL, NULL, '2025-01-01T00:00:00Z')",
            ("dangling-job", "missing-snapshot"),
            id="jobs-snapshot",
        ),
        pytest.param(
            "INSERT INTO backtest_decisions "
            "(job_id, sequence, signal_date, execution_date, status, attempts, target_position_pct, "
            "confidence, feature_hash, policy_hash, error_code, error_stage, created_at, updated_at) "
            "VALUES (?, 1, '2025-01-01T00:00:00Z', NULL, 'failed', 1, NULL, NULL, NULL, 'a', "
            "NULL, NULL, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')",
            ("missing-job",),
            id="decisions-job",
        ),
    ],
)
def test_context_store_refuses_markerless_v1_schema_with_existing_fk_violation(
    tmp_path: Path,
    seed_sql: str,
    seed_params: tuple[str, ...],
) -> None:
    data_dir = tmp_path / "data"
    _write_markerless_exact_v1_schema(data_dir)
    with sqlite3.connect(data_dir / "system.db") as db:
        db.execute(seed_sql, seed_params)

    store = ContextStore(data_dir)
    try:
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            store.get_backtest_job("missing")
    finally:
        store.close()

    with sqlite3.connect(data_dir / "system.db") as db:
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is None
        )


def test_context_store_refuses_same_column_decisions_table_without_cascade_fk(
    tmp_path: Path,
) -> None:
    # Given: a marker-less database retains every decision column but loses its required FK contract.
    data_dir = tmp_path / "data"
    store = ContextStore(data_dir)
    store.create_backtest_job("job", "{}", '{"contract_version":"backtest-run/v1"}')
    db = store._system_db()
    db.execute(
        "DELETE FROM schema_migrations WHERE name = ?",
        ("20260712_backtest_contract_v1",),
    )
    db.execute("DROP TABLE backtest_decisions")
    db.execute(
        "CREATE TABLE backtest_decisions ("
        "job_id TEXT NOT NULL, sequence INTEGER NOT NULL, signal_date TEXT NOT NULL, "
        "execution_date TEXT, status TEXT NOT NULL, attempts INTEGER NOT NULL, "
        "target_position_pct REAL, confidence REAL, feature_hash TEXT, policy_hash TEXT NOT NULL, "
        "error_code TEXT, error_stage TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (job_id, sequence))"
    )
    db.commit()
    store.close()

    reopened = ContextStore(data_dir)
    try:
        # When: startup sees matching names but no cascading decision foreign key.
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            reopened.get_backtest_job("job")
    finally:
        reopened.close()

    # Then: the migration registry remains absent rather than certifying the malformed table.
    with sqlite3.connect(data_dir / "system.db") as db:
        registry = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        assert registry is not None
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is None
        )


def test_context_store_refuses_decision_fk_with_wrong_backtest_jobs_target(
    tmp_path: Path,
) -> None:
    # Given: all decision columns and cascade semantics exist, but the FK targets request_json instead of id.
    data_dir = tmp_path / "data"
    store = ContextStore(data_dir)
    store.create_backtest_job("job", "{}", '{"contract_version":"backtest-run/v1"}')
    db = store._system_db()
    db.execute(
        "DELETE FROM schema_migrations WHERE name = ?",
        ("20260712_backtest_contract_v1",),
    )
    db.execute("DROP TABLE backtest_decisions")
    db.execute(
        "CREATE TABLE backtest_decisions ("
        "job_id TEXT NOT NULL REFERENCES backtest_jobs(request_json) ON DELETE CASCADE, "
        "sequence INTEGER NOT NULL, signal_date TEXT NOT NULL, execution_date TEXT, "
        "status TEXT NOT NULL, attempts INTEGER NOT NULL, target_position_pct REAL, "
        "confidence REAL, feature_hash TEXT, policy_hash TEXT NOT NULL, error_code TEXT, "
        "error_stage TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (job_id, sequence))"
    )
    db.commit()
    store.close()

    reopened = ContextStore(data_dir)
    try:
        # When: migration checks a same-shape decision table with the wrong FK destination.
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            reopened.get_backtest_job("job")
    finally:
        reopened.close()

    # Then: the marker remains absent because the only valid target is backtest_jobs.id.
    with sqlite3.connect(data_dir / "system.db") as db:
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is None
        )


def test_context_store_refuses_jobs_snapshot_fk_with_wrong_target(
    tmp_path: Path,
) -> None:
    # Given: every v1 column exists, but the jobs FK targets snapshot.codec instead of content_hash.
    data_dir = tmp_path / "data"
    store = ContextStore(data_dir)
    store.create_backtest_job("job", "{}", '{"contract_version":"backtest-run/v1"}')
    db = store._system_db()
    db.execute(
        "DELETE FROM schema_migrations WHERE name = ?",
        ("20260712_backtest_contract_v1",),
    )
    db.execute("DROP TABLE backtest_decisions")
    db.execute("ALTER TABLE backtest_jobs RENAME TO backtest_jobs_before_wrong_fk")
    db.execute(
        "CREATE TABLE backtest_jobs ("
        "id TEXT PRIMARY KEY, request_json TEXT NOT NULL, contract_version INTEGER NOT NULL DEFAULT 0, "
        "run_spec_json TEXT, input_snapshot_hash TEXT REFERENCES backtest_input_snapshots(codec), "
        "progress_json TEXT, status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')), "
        "result_json TEXT, error_json TEXT, created_at TEXT NOT NULL, started_at TEXT, "
        "completed_at TEXT, updated_at TEXT NOT NULL)"
    )
    db.execute("DROP TABLE backtest_jobs_before_wrong_fk")
    db.execute(
        "CREATE TABLE backtest_decisions ("
        "job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE, "
        "sequence INTEGER NOT NULL, signal_date TEXT NOT NULL, execution_date TEXT, "
        "status TEXT NOT NULL, attempts INTEGER NOT NULL, target_position_pct REAL, "
        "confidence REAL, feature_hash TEXT, policy_hash TEXT NOT NULL, error_code TEXT, "
        "error_stage TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
        "PRIMARY KEY (job_id, sequence))"
    )
    db.commit()
    store.close()

    reopened = ContextStore(data_dir)
    try:
        # When: startup sees the exact schema shape but the wrong snapshot FK destination.
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            reopened.get_backtest_job("job")
    finally:
        reopened.close()

    # Then: no migration marker certifies a jobs table whose snapshot FK is misdirected.
    with sqlite3.connect(data_dir / "system.db") as db:
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is None
        )


@pytest.mark.parametrize(
    ("target", "before", "after"),
    [
        pytest.param(
            "jobs",
            "contract_version INTEGER NOT NULL DEFAULT 0",
            "contract_version TEXT NOT NULL DEFAULT '0'",
            id="jobs-contract-version-type",
        ),
        pytest.param(
            "jobs",
            "contract_version INTEGER NOT NULL DEFAULT 0",
            "contract_version INTEGER DEFAULT 0",
            id="jobs-contract-version-not-null",
        ),
        pytest.param(
            "jobs",
            "contract_version INTEGER NOT NULL DEFAULT 0",
            "contract_version INTEGER NOT NULL DEFAULT 1",
            id="jobs-contract-version-default",
        ),
        pytest.param(
            "jobs",
            "run_spec_json TEXT",
            "run_spec_json BLOB",
            id="jobs-run-spec-type",
        ),
        pytest.param(
            "jobs",
            "input_snapshot_hash TEXT REFERENCES",
            "input_snapshot_hash BLOB REFERENCES",
            id="jobs-snapshot-hash-type",
        ),
        pytest.param(
            "jobs",
            "progress_json TEXT",
            "progress_json BLOB",
            id="jobs-progress-type",
        ),
        pytest.param(
            "jobs",
            "CHECK (status IN ('pending', 'running', 'completed', 'failed'))",
            "",
            id="jobs-status-check",
        ),
        pytest.param(
            "jobs",
            "CHECK (status IN ('pending', 'running', 'completed', 'failed'))",
            "CHECK (status = 'pending')",
            id="jobs-status-check-restricted-domain",
        ),
        pytest.param(
            "jobs",
            "REFERENCES backtest_input_snapshots(content_hash)",
            "REFERENCES backtest_input_snapshots(content_hash) DEFERRABLE INITIALLY DEFERRED",
            id="jobs-foreign-key-deferred",
        ),
        pytest.param(
            "jobs",
            "id TEXT PRIMARY KEY",
            "id TEXT",
            id="jobs-id-primary-key",
        ),
        pytest.param(
            "snapshot",
            "content_hash TEXT PRIMARY KEY",
            "content_hash BLOB PRIMARY KEY",
            id="snapshot-content-hash-type",
        ),
        pytest.param(
            "snapshot",
            "schema_version INTEGER NOT NULL",
            "schema_version TEXT NOT NULL",
            id="snapshot-schema-version-type",
        ),
        pytest.param(
            "snapshot",
            "schema_version INTEGER NOT NULL",
            "schema_version INTEGER",
            id="snapshot-schema-version-not-null",
        ),
        pytest.param(
            "snapshot",
            "CHECK (schema_version = 1)",
            "CHECK (schema_version IN (1, 2))",
            id="snapshot-schema-version-check",
        ),
        pytest.param(
            "snapshot",
            "CHECK (schema_version = 1)",
            "CHECK ('check(schema_version=1)' IS NOT NULL)",
            id="snapshot-schema-version-check-tautology",
        ),
        pytest.param(
            "snapshot",
            "codec TEXT NOT NULL",
            "codec BLOB NOT NULL",
            id="snapshot-codec-type",
        ),
        pytest.param(
            "snapshot",
            "CHECK (codec = 'gzip-json-v1')",
            "CHECK (codec IN ('gzip-json-v1', 'other'))",
            id="snapshot-codec-check",
        ),
        pytest.param(
            "snapshot",
            "CHECK (codec = 'gzip-json-v1')",
            "CHECK (\"check(codec='gzip-json-v1')\" IS NOT NULL)",
            id="snapshot-codec-check-tautology",
        ),
        pytest.param(
            "snapshot",
            "payload BLOB NOT NULL",
            "payload TEXT NOT NULL",
            id="snapshot-payload-type",
        ),
        pytest.param(
            "snapshot",
            "compressed_bytes INTEGER NOT NULL",
            "compressed_bytes TEXT NOT NULL",
            id="snapshot-compressed-bytes-type",
        ),
        pytest.param(
            "snapshot",
            "uncompressed_bytes INTEGER NOT NULL",
            "uncompressed_bytes TEXT NOT NULL",
            id="snapshot-uncompressed-bytes-type",
        ),
        pytest.param(
            "snapshot",
            "row_count_target INTEGER NOT NULL",
            "row_count_target TEXT NOT NULL",
            id="snapshot-target-count-type",
        ),
        pytest.param(
            "snapshot",
            "row_count_benchmark INTEGER NOT NULL",
            "row_count_benchmark TEXT NOT NULL",
            id="snapshot-benchmark-count-type",
        ),
        pytest.param(
            "snapshot",
            "created_at TEXT NOT NULL",
            "created_at BLOB NOT NULL",
            id="snapshot-created-at-type",
        ),
        pytest.param(
            "decisions",
            "job_id TEXT NOT NULL",
            "job_id BLOB NOT NULL",
            id="decisions-job-id-type",
        ),
        pytest.param(
            "decisions",
            "job_id TEXT NOT NULL",
            "job_id TEXT",
            id="decisions-job-id-not-null",
        ),
        pytest.param(
            "decisions",
            "sequence INTEGER NOT NULL",
            "sequence TEXT NOT NULL",
            id="decisions-sequence-type",
        ),
        pytest.param(
            "decisions",
            "signal_date TEXT NOT NULL",
            "signal_date BLOB NOT NULL",
            id="decisions-signal-date-type",
        ),
        pytest.param(
            "decisions",
            "execution_date TEXT",
            "execution_date BLOB",
            id="decisions-execution-date-type",
        ),
        pytest.param(
            "decisions",
            "status TEXT NOT NULL",
            "status BLOB NOT NULL",
            id="decisions-status-type",
        ),
        pytest.param(
            "decisions",
            "attempts INTEGER NOT NULL",
            "attempts TEXT NOT NULL",
            id="decisions-attempts-type",
        ),
        pytest.param(
            "decisions",
            "target_position_pct REAL",
            "target_position_pct TEXT",
            id="decisions-target-position-type",
        ),
        pytest.param(
            "decisions",
            "confidence REAL",
            "confidence TEXT",
            id="decisions-confidence-type",
        ),
        pytest.param(
            "decisions",
            "feature_hash TEXT",
            "feature_hash BLOB",
            id="decisions-feature-hash-type",
        ),
        pytest.param(
            "decisions",
            "policy_hash TEXT NOT NULL",
            "policy_hash BLOB NOT NULL",
            id="decisions-policy-hash-type",
        ),
        pytest.param(
            "decisions",
            "error_code TEXT",
            "error_code BLOB",
            id="decisions-error-code-type",
        ),
        pytest.param(
            "decisions",
            "error_stage TEXT",
            "error_stage BLOB",
            id="decisions-error-stage-type",
        ),
        pytest.param(
            "decisions",
            "created_at TEXT NOT NULL",
            "created_at BLOB NOT NULL",
            id="decisions-created-at-type",
        ),
        pytest.param(
            "decisions",
            "updated_at TEXT NOT NULL",
            "updated_at BLOB NOT NULL",
            id="decisions-updated-at-type",
        ),
        pytest.param(
            "decisions",
            "PRIMARY KEY (job_id, sequence)",
            "PRIMARY KEY (sequence, job_id)",
            id="decisions-primary-key-order",
        ),
        pytest.param(
            "decisions",
            "REFERENCES backtest_jobs(id) ON DELETE CASCADE",
            "REFERENCES backtest_jobs(request_json) ON DELETE CASCADE",
            id="decisions-foreign-key-target",
        ),
        pytest.param(
            "decisions",
            "REFERENCES backtest_jobs(id) ON DELETE CASCADE",
            "REFERENCES backtest_jobs(id)",
            id="decisions-foreign-key-cascade",
        ),
        pytest.param(
            "decisions",
            "REFERENCES backtest_jobs(id) ON DELETE CASCADE",
            "REFERENCES backtest_jobs(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED",
            id="decisions-foreign-key-deferred",
        ),
        pytest.param(
            "migrations",
            "name TEXT PRIMARY KEY",
            "name BLOB PRIMARY KEY",
            id="migrations-name-type",
        ),
        pytest.param(
            "migrations",
            "applied_at TEXT NOT NULL",
            "applied_at BLOB NOT NULL",
            id="migrations-applied-at-type",
        ),
        pytest.param(
            "index",
            "CREATE INDEX idx_backtest_decisions_job ON backtest_decisions(job_id)",
            "CREATE INDEX idx_backtest_decisions_job ON backtest_decisions(sequence)",
            id="decisions-index-columns",
        ),
    ],
)
def test_context_store_refuses_each_malformed_exact_v1_schema_contract(
    tmp_path: Path,
    target: str,
    before: str,
    after: str,
) -> None:
    # Given: a marker-less V1 database whose only difference is one contract violation.
    data_dir = tmp_path / "data"
    _write_markerless_exact_v1_schema(data_dir, target, before, after)

    store = ContextStore(data_dir)
    try:
        # When: the public startup seam validates the persisted migration contract.
        with pytest.raises(RuntimeError, match="backtest migration schema"):
            store.get_backtest_job("missing")
    finally:
        store.close()

    # Then: no malformed DDL variant can be certified by the migration marker.
    with sqlite3.connect(data_dir / "system.db") as db:
        assert (
            db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                ("20260712_backtest_contract_v1",),
            ).fetchone()
            is None
        )
