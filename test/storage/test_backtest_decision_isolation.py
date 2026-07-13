from __future__ import annotations

import gzip
import hashlib
from pathlib import Path

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
                feature_hash=None,
                policy_hash="d" * 64,
                error_code="decision_schema_invalid",
                error_stage="structured_output",
            )
        )

        # Then: each job reads only its own row even where sequence values match.
        job_c = store.get_backtest_decisions("job-c")
        job_d = store.get_backtest_decisions("job-d")
        assert [(item.job_id, item.sequence, item.status) for item in job_c] == [
            ("job-c", 1, "completed")
        ]
        assert [(item.job_id, item.sequence, item.status) for item in job_d] == [
            ("job-d", 1, "failed")
        ]
    finally:
        store.close()
