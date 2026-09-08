"""SQLite-backed ContextStore with per-strategy database isolation.

Database layout (from docs/architecture.md §12):
    data/system.db       — strategy registry, global config, beliefs
    data/insights.db     — daily briefs, news archives
    data/memory.db       — OWM memory (handled by memory/store.py)
    data/knowledge.db    — rules, findings, failures, hypotheses
    data/{strategy_id}.db — per-strategy: account, positions, orders,
                             trades, decisions, events
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
import math
from pathlib import Path
from typing import Final, Literal, Mapping

from storage.backtest_snapshot import (
    CanonicalSnapshotEnvelope,
    decode_canonical_snapshot,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BACKTEST_CONTRACT_MIGRATION: Final = "20260712_backtest_contract_v1"
_MAX_BACKTEST_INPUT_SNAPSHOT_BYTES: Final = 16 * 1024 * 1024
_BACKTEST_DECISION_ERROR_CODES: Final = frozenset(
    {
        "agent_failed",
        "backtest_failed",
        "decision_context_invalid",
        "decision_policy_invalid",
        "decision_transient_exhausted",
        "provider_failed",
        "decision_schema_invalid",
    }
)
_BACKTEST_DECISION_ERROR_STAGES: Final = frozenset(
    {
        "agent_execution",
        "context",
        "policy",
        "provider",
        "transient",
        "structured_output",
        "tool_call",
        "tool_payload",
    }
)
type _SqliteColumnContract = tuple[str, bool, str | None, int]

_BACKTEST_JOB_COLUMN_CONTRACT: Final = {
    "id": ("TEXT", False, None, 1),
    "request_json": ("TEXT", True, None, 0),
    "contract_version": ("INTEGER", True, "0", 0),
    "run_spec_json": ("TEXT", False, None, 0),
    "input_snapshot_hash": ("TEXT", False, None, 0),
    "progress_json": ("TEXT", False, None, 0),
    "status": ("TEXT", True, None, 0),
    "result_json": ("TEXT", False, None, 0),
    "error_json": ("TEXT", False, None, 0),
    "created_at": ("TEXT", True, None, 0),
    "started_at": ("TEXT", False, None, 0),
    "completed_at": ("TEXT", False, None, 0),
    "updated_at": ("TEXT", True, None, 0),
}
_BACKTEST_INPUT_SNAPSHOT_COLUMN_CONTRACT: Final = {
    "content_hash": ("TEXT", False, None, 1),
    "schema_version": ("INTEGER", True, None, 0),
    "codec": ("TEXT", True, None, 0),
    "payload": ("BLOB", True, None, 0),
    "compressed_bytes": ("INTEGER", True, None, 0),
    "uncompressed_bytes": ("INTEGER", True, None, 0),
    "row_count_target": ("INTEGER", True, None, 0),
    "row_count_benchmark": ("INTEGER", True, None, 0),
    "created_at": ("TEXT", True, None, 0),
}
_BACKTEST_DECISION_COLUMN_CONTRACT: Final = {
    "job_id": ("TEXT", True, None, 1),
    "sequence": ("INTEGER", True, None, 2),
    "signal_date": ("TEXT", True, None, 0),
    "execution_date": ("TEXT", False, None, 0),
    "status": ("TEXT", True, None, 0),
    "attempts": ("INTEGER", True, None, 0),
    "target_position_pct": ("REAL", False, None, 0),
    "confidence": ("REAL", False, None, 0),
    "action": ("TEXT", False, None, 0),
    "rationale": ("TEXT", False, None, 0),
    "feature_hash": ("TEXT", False, None, 0),
    "policy_hash": ("TEXT", True, None, 0),
    "error_code": ("TEXT", False, None, 0),
    "error_stage": ("TEXT", False, None, 0),
    "created_at": ("TEXT", True, None, 0),
    "updated_at": ("TEXT", True, None, 0),
}
_BACKTEST_MIGRATION_COLUMN_CONTRACT: Final = {
    "name": ("TEXT", False, None, 1),
    "applied_at": ("TEXT", True, None, 0),
}

type BacktestJobStatus = Literal["pending", "running", "completed", "failed"]
type BacktestDecisionStatus = Literal[
    "not_ready", "completed", "failed", "unfilled_end_of_window"
]
type BacktestDecisionAction = Literal["BUY", "SELL", "HOLD"]
type ScanRunStatus = Literal["running", "completed", "failed"]
type ReportJobStatus = Literal["pending", "running", "completed", "failed"]
type InsightGenerationStatus = Literal["pending", "running", "completed", "failed"]


class BacktestMigrationContractError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("backtest migration schema is inconsistent")


@dataclass(frozen=True, slots=True)
class BacktestJobRecord:
    id: str
    request_json: str
    contract_version: int
    run_spec_json: str | None
    input_snapshot_hash: str | None
    progress_json: str | None
    status: BacktestJobStatus
    result_json: str | None
    error_json: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class BacktestInputSnapshotContent:
    content_hash: str
    payload: bytes
    uncompressed_bytes: int
    row_count_target: int
    row_count_benchmark: int


@dataclass(frozen=True, slots=True)
class BacktestInputSnapshotRecord:
    content_hash: str
    schema_version: int
    codec: str
    payload: bytes
    compressed_bytes: int
    uncompressed_bytes: int
    row_count_target: int
    row_count_benchmark: int
    created_at: str


@dataclass(frozen=True, slots=True)
class BacktestDecisionEvidence:
    job_id: str
    sequence: int
    signal_date: str
    execution_date: str | None
    status: BacktestDecisionStatus
    attempts: int
    target_position_pct: float | None
    confidence: float | None
    feature_hash: str | None
    policy_hash: str
    error_code: str | None
    error_stage: str | None
    action: BacktestDecisionAction | None = None
    rationale: str | None = None


@dataclass(frozen=True, slots=True)
class BacktestDecisionRecord:
    job_id: str
    sequence: int
    signal_date: str
    execution_date: str | None
    status: BacktestDecisionStatus
    attempts: int
    target_position_pct: float | None
    confidence: float | None
    action: BacktestDecisionAction | None
    rationale: str | None
    feature_hash: str | None
    policy_hash: str
    error_code: str | None
    error_stage: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ScanRunRecord:
    id: str
    input_json: str
    compiled_conditions_json: str | None
    result_json: str | None
    error_json: str | None
    status: ScanRunStatus
    mode: str
    strategy_id: str | None
    created_at: str
    completed_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class ReportJobRecord:
    id: str
    report_type: str
    title: str
    tickers_json: str
    source_type: str
    source_ids_json: str
    parameters_json: str
    status: ReportJobStatus
    artifact_name: str | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class InsightGenerationRecord:
    id: str
    hours: int
    status: InsightGenerationStatus
    progress_json: str
    result_insight_id: str | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ContextStore:
    """Unified SQLite persistence layer.

    Usage:
        store = ContextStore()
        store.record_session(strategy_id, session_id, ticker, data)
        events = store.get_events(session_id)
    """

    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._conns: dict[tuple[str, int | None], sqlite3.Connection] = {}

    # ── Strategy registry (system.db) ──────────────────────

    def _system_db(self) -> sqlite3.Connection:
        return self._get_conn("system.db")

    def register_strategy(self, strategy: dict) -> None:
        db = self._system_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT DEFAULT 'agent',
                status TEXT DEFAULT 'draft',
                config_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        db.execute(
            """INSERT OR REPLACE INTO strategies
               (id, name, type, status, config_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                strategy.get("id", ""),
                strategy.get("name", ""),
                strategy.get("type", "agent"),
                strategy.get("status", "draft"),
                json.dumps(strategy, ensure_ascii=False),
                strategy.get("created_at", _now()),
                _now(),
            ),
        )
        db.commit()

    def get_strategy(self, strategy_id: str) -> dict | None:
        db = self._system_db()
        db.execute(
            "CREATE TABLE IF NOT EXISTS strategies (id TEXT PRIMARY KEY, name TEXT, type TEXT, status TEXT, config_json TEXT, created_at TEXT, updated_at TEXT)"
        )
        row = db.execute(
            "SELECT config_json FROM strategies WHERE id = ?", (strategy_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_strategies(
        self,
        type: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """List all strategies, optionally filtered by type and/or status."""
        db = self._system_db()
        db.execute(
            "CREATE TABLE IF NOT EXISTS strategies (id TEXT PRIMARY KEY, name TEXT, type TEXT, status TEXT, config_json TEXT, created_at TEXT, updated_at TEXT)"
        )
        query = "SELECT config_json FROM strategies WHERE 1=1"
        params: list[str] = []
        if type:
            query += " AND type = ?"
            params.append(type)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC"
        rows = db.execute(query, params).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_watchlist_tickers(self) -> list[str]:
        """Return normalized tickers persisted by existing watchlists."""
        db = self._system_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS watchlists (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tickers_json TEXT DEFAULT '[]',
                notes_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        db.commit()
        rows = db.execute("SELECT tickers_json FROM watchlists").fetchall()
        tickers: set[str] = set()
        for row in rows:
            try:
                decoded = json.loads(str(row["tickers_json"] or "[]"))
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, list):
                tickers.update(
                    ticker.strip().upper()
                    for ticker in decoded
                    if isinstance(ticker, str) and ticker.strip()
                )
        return sorted(tickers)

    def update_strategy(self, strategy_id: str, updates: dict) -> dict | None:
        """Merge updates into an existing strategy's config_json. Returns updated config."""
        existing = self.get_strategy(strategy_id)
        if existing is None:
            return None

        # Deep merge: updates override existing keys
        merged = {**existing, **updates}
        # Ensure id doesn't change
        merged["id"] = strategy_id
        merged["updated_at"] = _now()

        db = self._system_db()
        db.execute(
            """UPDATE strategies
               SET name = ?, type = ?, status = ?, config_json = ?, updated_at = ?
               WHERE id = ?""",
            (
                merged.get("name", ""),
                merged.get("type", "agent"),
                merged.get("status", "draft"),
                json.dumps(merged, ensure_ascii=False),
                merged["updated_at"],
                strategy_id,
            ),
        )
        db.commit()
        return merged

    # ── Strategy-level data ({strategy_id}.db) ──────────────

    def _strategy_db(self, strategy_id: str) -> sqlite3.Connection:
        return self._get_conn(f"{strategy_id}.db")

    def _init_strategy_db(self, strategy_id: str) -> None:
        db = self._strategy_db(strategy_id)
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                status TEXT DEFAULT 'running',
                started_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_reports (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                report_type TEXT NOT NULL,
                content TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT NOT NULL,
                direction TEXT,
                confidence REAL DEFAULT 0.0,
                target_position_pct REAL DEFAULT 0.0,
                report TEXT DEFAULT '',
                winning_belief TEXT,
                cross_review_consensus INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT DEFAULT '',
                payload_json TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                strategy_id TEXT DEFAULT '',
                account_id TEXT DEFAULT '',
                decision_id TEXT DEFAULT '',
                session_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                original_action TEXT NOT NULL,
                original_target_position_pct REAL DEFAULT 0.0,
                original_confidence REAL DEFAULT 0.0,
                pm_report TEXT DEFAULT '',
                triggered_rules_json TEXT DEFAULT '[]',
                approval_reason TEXT DEFAULT '',
                agent_reports_json TEXT DEFAULT '[]',
                status TEXT DEFAULT 'pending',
                reviewer TEXT DEFAULT '',
                reviewer_notes TEXT DEFAULT '',
                modified_action TEXT DEFAULT '',
                modified_target_position_pct REAL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                timeout_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_ticker ON sessions(ticker);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_reports_session ON agent_reports(session_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
            CREATE INDEX IF NOT EXISTS idx_approvals_session ON approvals(session_id);
            CREATE INDEX IF NOT EXISTS idx_approvals_decision ON approvals(decision_id);
        """)
        for col in (
            "strategy_id TEXT DEFAULT ''",
            "account_id TEXT DEFAULT ''",
            "decision_id TEXT DEFAULT ''",
            "approval_reason TEXT DEFAULT ''",
        ):
            try:
                db.execute(f"ALTER TABLE approvals ADD COLUMN {col}")
            except Exception:
                pass
        db.commit()

    def record_session(
        self, strategy_id: str, session_id: str, ticker: str, status: str = "running"
    ) -> None:
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        db.execute(
            "INSERT OR REPLACE INTO sessions (id, ticker, status, started_at) VALUES (?, ?, ?, ?)",
            (session_id, ticker, status, _now()),
        )
        db.commit()

    def complete_session(
        self, strategy_id: str, session_id: str, status: str = "completed"
    ) -> None:
        db = self._strategy_db(strategy_id)
        db.execute(
            "UPDATE sessions SET status = ?, completed_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )
        db.commit()

    def record_report(
        self,
        strategy_id: str,
        session_id: str,
        agent_name: str,
        report_type: str,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        import uuid

        self._init_strategy_db(strategy_id)
        rid = str(uuid.uuid4())
        db = self._strategy_db(strategy_id)
        db.execute(
            """INSERT INTO agent_reports (id, session_id, agent_name, report_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                rid,
                session_id,
                agent_name,
                report_type,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                _now(),
            ),
        )
        db.commit()
        return rid

    def record_decision(self, strategy_id: str, decision: dict) -> str:
        import uuid

        self._init_strategy_db(strategy_id)
        did = decision.get("id") or str(uuid.uuid4())
        db = self._strategy_db(strategy_id)
        db.execute(
            """INSERT OR REPLACE INTO decisions
               (id, session_id, ticker, action, direction, confidence, target_position_pct, report, winning_belief, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                did,
                decision.get("session_id", ""),
                decision.get("ticker", ""),
                decision.get("action", "HOLD"),
                decision.get("direction", "Neutral"),
                decision.get("confidence", 0.0),
                decision.get("target_position_pct", 0.0),
                decision.get("report", ""),
                decision.get("winning_belief"),
                decision.get("created_at", _now()),
            ),
        )
        db.commit()
        return did

    def record_event(
        self,
        strategy_id: str,
        session_id: str,
        event_type: str,
        actor: str = "",
        payload: dict | None = None,
    ) -> None:
        import uuid

        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        db.execute(
            "INSERT INTO events (id, session_id, event_type, actor, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                session_id,
                event_type,
                actor,
                json.dumps(payload or {}, ensure_ascii=False),
                _now(),
            ),
        )
        db.commit()

    # ── Queries ─────────────────────────────────────────────

    def get_sessions(self, strategy_id: str, limit: int = 20) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = (
            self._strategy_db(strategy_id)
            .execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_decisions(
        self, strategy_id: str, ticker: str | None = None, limit: int = 20
    ) -> list[dict]:
        self._init_strategy_db(strategy_id)
        if ticker:
            rows = (
                self._strategy_db(strategy_id)
                .execute(
                    "SELECT * FROM decisions WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
                    (ticker, limit),
                )
                .fetchall()
            )
        else:
            rows = (
                self._strategy_db(strategy_id)
                .execute(
                    "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
                )
                .fetchall()
            )
        return [dict(r) for r in rows]

    def get_events(self, strategy_id: str, session_id: str) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = (
            self._strategy_db(strategy_id)
            .execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
                (session_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def get_reports(self, strategy_id: str, session_id: str) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = (
            self._strategy_db(strategy_id)
            .execute(
                "SELECT * FROM agent_reports WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    # ── MonitorTasks ────────────────────────────────────────

    def _init_monitor_db(self) -> None:
        """Ensure monitor tables exist in system.db and insights.db."""
        db = self._system_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS monitor_tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'keyword',
                targets_json TEXT DEFAULT '{}',
                sources_json TEXT DEFAULT '[]',
                schedule_json TEXT DEFAULT '{}',
                agent_json TEXT DEFAULT '{}',
                output_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_run_at TEXT
            )
        """)
        # Migrations: add columns that may not exist in older DBs
        for col in (
            "cron_expression TEXT DEFAULT ''",
            "expanded_keywords_json TEXT DEFAULT '[]'",
            "expanded_tickers_json TEXT DEFAULT '[]'",
            "report_language TEXT DEFAULT 'zh'",
            "run_status TEXT DEFAULT 'idle'",
            "current_run_id TEXT",
            "last_run_started_at TEXT",
            "last_run_finished_at TEXT",
            "last_run_error TEXT DEFAULT ''",
        ):
            try:
                db.execute(f"ALTER TABLE monitor_tasks ADD COLUMN {col}")
            except Exception:
                pass
        db.commit()

        # monitoring_reports go in insights.db
        idb = self._get_conn("insights.db")
        idb.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_reports (
                id TEXT PRIMARY KEY,
                monitor_id TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                key_findings_json TEXT DEFAULT '[]',
                sentiment TEXT DEFAULT 'neutral',
                related_tickers_json TEXT DEFAULT '[]',
                alerts_json TEXT DEFAULT '[]',
                raw_data_json TEXT DEFAULT '{}',
                generated_at TEXT NOT NULL
            )
        """)
        for col in (
            "title TEXT DEFAULT ''",
            "report_type TEXT DEFAULT 'scheduled'",
            "source_news_ids TEXT DEFAULT '[]'",
            "context_report_ids TEXT DEFAULT '[]'",
            "summary_text TEXT DEFAULT ''",
            "content_text TEXT DEFAULT ''",
        ):
            try:
                idb.execute(f"ALTER TABLE monitoring_reports ADD COLUMN {col}")
            except Exception:
                pass

        # New: per-monitor collected news
        idb.execute("""
            CREATE TABLE IF NOT EXISTS monitor_news (
                id TEXT PRIMARY KEY,
                monitor_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                url TEXT NOT NULL,
                source_name TEXT DEFAULT '',
                published_at TEXT,
                relevance_score REAL DEFAULT 1.0,
                fetched_at TEXT NOT NULL,
                UNIQUE(monitor_id, url)
            )
        """)
        idb.execute(
            "CREATE INDEX IF NOT EXISTS idx_monitor_news_monitor ON monitor_news(monitor_id)"
        )
        idb.execute(
            "CREATE INDEX IF NOT EXISTS idx_monitor_news_fetched ON monitor_news(fetched_at)"
        )
        idb.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_monitor ON monitoring_reports(monitor_id)"
        )
        idb.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_generated ON monitoring_reports(generated_at)"
        )

        # Daily briefs
        idb.execute("""
            CREATE TABLE IF NOT EXISTS daily_briefs (
                id TEXT PRIMARY KEY,
                type TEXT DEFAULT 'morning_brief',
                title TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                content TEXT DEFAULT '',
                sections_json TEXT DEFAULT '[]',
                key_events_json TEXT DEFAULT '[]',
                tickers_covered_json TEXT DEFAULT '[]',
                market_data_json TEXT DEFAULT '{}',
                news_sources_json TEXT DEFAULT '[]',
                generated_at TEXT NOT NULL
            )
        """)
        idb.execute(
            "CREATE INDEX IF NOT EXISTS idx_briefs_generated ON daily_briefs(generated_at)"
        )
        idb.commit()

    def register_monitor(self, config: dict) -> str:
        import uuid

        self._init_monitor_db()
        mid = config.get("id") or str(uuid.uuid4())
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT OR REPLACE INTO monitor_tasks
               (id, name, description, mode, targets_json, sources_json,
                schedule_json, agent_json, output_json,
                cron_expression, expanded_keywords_json, expanded_tickers_json,
                report_language, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                mid,
                config.get("name", ""),
                config.get("description", ""),
                config.get("mode", "keyword"),
                json.dumps(config.get("targets", {})),
                json.dumps(config.get("sources", ["news", "prices"])),
                json.dumps(config.get("schedule", {})),
                json.dumps(config.get("agent", {})),
                json.dumps(config.get("output", {})),
                config.get("cron_expression", ""),
                json.dumps(config.get("expanded_keywords", [])),
                json.dumps(config.get("expanded_tickers", [])),
                config.get("report_language", "zh"),
                config.get("status", "active"),
                config.get("created_at", now),
                now,
            ),
        )
        db.commit()
        return mid

    def list_monitors(self, status: str | None = None) -> list[dict]:
        self._init_monitor_db()
        db = self._system_db()
        if status:
            rows = db.execute(
                "SELECT * FROM monitor_tasks WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM monitor_tasks ORDER BY updated_at DESC"
            ).fetchall()
        return [_monitor_row_to_dict(r) for r in rows]

    def get_monitor(self, monitor_id: str) -> dict | None:
        self._init_monitor_db()
        db = self._system_db()
        row = db.execute(
            "SELECT * FROM monitor_tasks WHERE id = ?", (monitor_id,)
        ).fetchone()
        return _monitor_row_to_dict(row) if row else None

    def update_monitor(self, monitor_id: str, updates: dict) -> dict | None:
        existing = self.get_monitor(monitor_id)
        if existing is None:
            return None
        merged = {**existing, **updates, "id": monitor_id, "updated_at": _now()}
        db = self._system_db()
        db.execute(
            """UPDATE monitor_tasks SET name=?, description=?, mode=?,
               targets_json=?, sources_json=?, schedule_json=?, agent_json=?,
               output_json=?, cron_expression=?, expanded_keywords_json=?,
               expanded_tickers_json=?, report_language=?,
               status=?, updated_at=?, last_run_at=?
               WHERE id=?""",
            (
                merged["name"],
                merged.get("description", ""),
                merged["mode"],
                json.dumps(merged.get("targets", {})),
                json.dumps(merged.get("sources", [])),
                json.dumps(merged.get("schedule", {})),
                json.dumps(merged.get("agent", {})),
                json.dumps(merged.get("output", {})),
                merged.get("cron_expression", ""),
                json.dumps(merged.get("expanded_keywords", [])),
                json.dumps(merged.get("expanded_tickers", [])),
                merged.get("report_language", "zh"),
                merged.get("status", "active"),
                merged["updated_at"],
                merged.get("last_run_at"),
                monitor_id,
            ),
        )
        db.commit()
        return merged

    def delete_monitor(self, monitor_id: str) -> bool:
        self._init_monitor_db()
        db = self._system_db()
        db.execute("DELETE FROM monitor_tasks WHERE id = ?", (monitor_id,))
        db.commit()
        return True

    def touch_monitor_run(self, monitor_id: str) -> None:
        db = self._system_db()
        db.execute(
            "UPDATE monitor_tasks SET last_run_at = ? WHERE id = ?",
            (_now(), monitor_id),
        )
        db.commit()

    def start_monitor_run(self, monitor_id: str, run_id: str) -> dict | None:
        self._init_monitor_db()
        now = _now()
        db = self._system_db()
        cursor = db.execute(
            """UPDATE monitor_tasks
               SET run_status = 'running',
                   current_run_id = ?,
                   last_run_started_at = ?,
                   last_run_error = '',
                   updated_at = ?
               WHERE id = ?""",
            (run_id, now, now, monitor_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_monitor(monitor_id)

    def finish_monitor_run(self, monitor_id: str, run_id: str) -> dict | None:
        self._init_monitor_db()
        now = _now()
        db = self._system_db()
        cursor = db.execute(
            """UPDATE monitor_tasks
               SET run_status = 'idle',
                   current_run_id = NULL,
                   last_run_finished_at = ?,
                   last_run_at = ?,
                   last_run_error = '',
                   updated_at = ?
               WHERE id = ? AND current_run_id = ?""",
            (now, now, now, monitor_id, run_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_monitor(monitor_id)

    def fail_monitor_run(self, monitor_id: str, run_id: str, error: str) -> dict | None:
        self._init_monitor_db()
        now = _now()
        db = self._system_db()
        cursor = db.execute(
            """UPDATE monitor_tasks
               SET run_status = 'failed',
                   current_run_id = NULL,
                   last_run_finished_at = ?,
                   last_run_error = ?,
                   updated_at = ?
               WHERE id = ? AND current_run_id = ?""",
            (now, error[:500], now, monitor_id, run_id),
        )
        db.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_monitor(monitor_id)

    # ── Monitoring Reports ──────────────────────────────────

    def save_monitoring_report(self, report: dict) -> str:
        import uuid

        self._init_monitor_db()
        rid = report.get("id") or str(uuid.uuid4())
        now = _now()
        idb = self._get_conn("insights.db")
        idb.execute(
            """INSERT INTO monitoring_reports
               (id, monitor_id, session_id, summary, key_findings_json,
                sentiment, related_tickers_json, alerts_json, raw_data_json,
                title, report_type, source_news_ids, context_report_ids,
                summary_text, content_text, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid,
                report.get("monitor_id", ""),
                report.get("session_id", ""),
                report.get("summary", ""),
                json.dumps(report.get("key_findings", [])),
                report.get("sentiment", "neutral"),
                json.dumps(report.get("related_tickers", [])),
                json.dumps(report.get("alerts", [])),
                json.dumps(report.get("raw_data", {})),
                report.get("title", ""),
                report.get("report_type", "scheduled"),
                json.dumps(report.get("source_news_ids", [])),
                json.dumps(report.get("context_report_ids", [])),
                report.get("summary_text", ""),
                report.get("content_text", ""),
                report.get("generated_at", now),
            ),
        )
        idb.commit()
        return rid

    def list_monitoring_reports(self, monitor_id: str, limit: int = 20) -> list[dict]:
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        rows = idb.execute(
            "SELECT * FROM monitoring_reports WHERE monitor_id = ? ORDER BY generated_at DESC LIMIT ?",
            (monitor_id, limit),
        ).fetchall()
        return [_report_row_to_dict(r) for r in rows]

    # ── Monitor News ─────────────────────────────────────────

    def save_monitor_news(self, monitor_id: str, articles: list[dict]) -> int:
        """Insert or ignore news articles for a monitor. Returns count of new articles."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        count = 0
        now = _now()
        import uuid

        for a in articles:
            try:
                cursor = idb.execute(
                    """INSERT OR IGNORE INTO monitor_news
                       (id, monitor_id, title, summary, url, source_name, published_at, relevance_score, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        monitor_id,
                        a.get("title", ""),
                        a.get("summary", ""),
                        a.get("url", ""),
                        a.get("source_name", ""),
                        a.get("published_at"),
                        a.get("relevance_score", 1.0),
                        now,
                    ),
                )
                if cursor.rowcount > 0:
                    count += 1
            except Exception:
                continue
        idb.commit()
        return count

    def list_monitor_news(self, monitor_id: str, limit: int = 100) -> list[dict]:
        """Get collected news for a monitor, newest first."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        rows = idb.execute(
            "SELECT * FROM monitor_news WHERE monitor_id = ? ORDER BY fetched_at DESC LIMIT ?",
            (monitor_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Daily Briefs ──────────────────────────────────────────

    def save_daily_brief(self, brief: dict) -> str:
        """Save a generated daily brief. Returns the brief ID."""
        import uuid as _uuid

        self._init_monitor_db()
        rid = brief.get("id") or str(_uuid.uuid4())
        now = _now()
        idb = self._get_conn("insights.db")
        idb.execute(
            """INSERT INTO daily_briefs
               (id, type, title, summary, content, sections_json,
                key_events_json, tickers_covered_json, market_data_json,
                news_sources_json, generated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid,
                brief.get("type", "morning_brief"),
                brief.get("title", ""),
                brief.get("summary", ""),
                brief.get("content", ""),
                _json_dumps_finite(brief.get("sections", [])),
                _json_dumps_finite(brief.get("key_events", [])),
                _json_dumps_finite(brief.get("tickers_covered", [])),
                _json_dumps_finite(brief.get("market_data", {})),
                _json_dumps_finite(brief.get("news_sources", [])),
                brief.get("generated_at", now),
            ),
        )
        idb.commit()
        return rid

    def list_daily_briefs(self, limit: int = 20) -> list[dict]:
        """List recent daily briefs, newest first."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        rows = idb.execute(
            "SELECT * FROM daily_briefs ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_brief_row_to_dict(r) for r in rows]

    def get_daily_brief(self, brief_id: str) -> dict | None:
        """Get a single daily brief by ID."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        row = idb.execute(
            "SELECT * FROM daily_briefs WHERE id = ?", (brief_id,)
        ).fetchone()
        return _brief_row_to_dict(row) if row else None

    def delete_daily_brief(self, brief_id: str) -> bool:
        """Delete a daily brief by ID. Returns True if deleted."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        cur = idb.execute("DELETE FROM daily_briefs WHERE id = ?", (brief_id,))
        idb.commit()
        return cur.rowcount > 0

    def get_latest_brief(self) -> dict | None:
        """Get the most recent daily brief."""
        self._init_monitor_db()
        idb = self._get_conn("insights.db")
        row = idb.execute(
            "SELECT * FROM daily_briefs ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        return _brief_row_to_dict(row) if row else None

    # ── Approvals ───────────────────────────────────────────

    def create_approval(self, strategy_id: str, approval: dict) -> str:
        import uuid

        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        aid = approval.get("id") or str(uuid.uuid4())
        db.execute(
            """INSERT INTO approvals
               (id, strategy_id, account_id, decision_id, session_id, ticker,
                original_action, original_target_position_pct, original_confidence,
                pm_report, triggered_rules_json, approval_reason, agent_reports_json,
                status, reviewer, reviewer_notes, modified_action,
                modified_target_position_pct, created_at, decided_at, timeout_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                aid,
                strategy_id,
                approval.get("account_id", ""),
                approval.get("decision_id", ""),
                approval.get("session_id", ""),
                approval.get("ticker", ""),
                approval.get("original_action", "HOLD"),
                approval.get("original_target_position_pct", 0.0),
                approval.get("original_confidence", 0.0),
                approval.get("pm_report", ""),
                json.dumps(approval.get("triggered_rules", []), ensure_ascii=False),
                approval.get("approval_reason", ""),
                json.dumps(approval.get("agent_reports", []), ensure_ascii=False),
                approval.get("status", "pending"),
                approval.get("reviewer", ""),
                approval.get("reviewer_notes", ""),
                approval.get("modified_action", ""),
                approval.get("modified_target_position_pct"),
                approval.get("created_at", _now()),
                approval.get("decided_at"),
                approval.get("timeout_at"),
            ),
        )
        db.commit()
        return aid

    def get_approval(self, strategy_id: str, approval_id: str) -> dict | None:
        self._init_strategy_db(strategy_id)
        row = (
            self._strategy_db(strategy_id)
            .execute("SELECT * FROM approvals WHERE id = ?", (approval_id,))
            .fetchone()
        )
        return dict(row) if row else None

    def list_approvals(
        self,
        strategy_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        if status:
            statuses = [s.strip() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                rows = db.execute(
                    "SELECT * FROM approvals WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (statuses[0], limit),
                ).fetchall()
            else:
                placeholders = ",".join("?" * len(statuses))
                rows = db.execute(
                    f"SELECT * FROM approvals WHERE status IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
                    (*statuses, limit),
                ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM approvals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_approval_status(
        self,
        strategy_id: str,
        approval_id: str,
        status: str,
        reviewer: str = "",
        reviewer_notes: str = "",
        modified_action: str | None = None,
        modified_target_position_pct: float | None = None,
    ) -> bool:
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        fields = ["status = ?", "reviewer = ?", "reviewer_notes = ?", "decided_at = ?"]
        params: list[object] = [status, reviewer, reviewer_notes, _now()]
        if modified_action is not None:
            fields.append("modified_action = ?")
            params.append(modified_action)
        if modified_target_position_pct is not None:
            fields.append("modified_target_position_pct = ?")
            params.append(modified_target_position_pct)
        params.append(approval_id)
        sql = f"UPDATE approvals SET {', '.join(fields)} WHERE id = ?"
        cursor = db.execute(sql, params)
        db.commit()
        return cursor.rowcount > 0

    def create_backtest_job(
        self, job_id: str, request_json: str, run_spec_json: str
    ) -> BacktestJobRecord:
        self._init_backtest_jobs_db()
        if not run_spec_json:
            raise RuntimeError("v1 backtest jobs require a frozen run spec")
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT INTO backtest_jobs
               (id, request_json, contract_version, run_spec_json, input_snapshot_hash,
                progress_json, status, result_json, error_json,
                created_at, started_at, completed_at, updated_at)
               VALUES (?, ?, 1, ?, NULL, NULL, 'pending', NULL, NULL, ?, NULL, NULL, ?)""",
            (job_id, request_json, run_spec_json, now, now),
        )
        db.commit()
        job = self.get_backtest_job(job_id)
        if job is None:
            raise RuntimeError("backtest job was not persisted")
        return job

    def bind_backtest_input_snapshot(
        self, job_id: str, snapshot: BacktestInputSnapshotContent
    ) -> BacktestInputSnapshotRecord:
        self._init_backtest_jobs_db()
        canonical_payload = _decode_backtest_input_snapshot_payload(
            snapshot.payload,
            compressed_bytes=len(snapshot.payload),
            uncompressed_bytes=snapshot.uncompressed_bytes,
            content_hash=snapshot.content_hash,
        )
        _validate_backtest_snapshot_payload(
            canonical_payload,
            row_count_target=snapshot.row_count_target,
            row_count_benchmark=snapshot.row_count_benchmark,
        )
        db = self._system_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            job = db.execute(
                "SELECT contract_version, input_snapshot_hash FROM backtest_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise RuntimeError(
                    "v1 backtest job is unavailable for snapshot binding"
                )
            contract_version = _strict_persisted_int(
                job["contract_version"], message="backtest job metadata is invalid"
            )
            if contract_version != 1:
                raise RuntimeError(
                    "v1 backtest job is unavailable for snapshot binding"
                )
            current_hash = _strict_persisted_nullable_text(
                job["input_snapshot_hash"], message="backtest job metadata is invalid"
            )
            if current_hash is not None and current_hash != snapshot.content_hash:
                raise RuntimeError(
                    "backtest job already has a different frozen snapshot"
                )
            now = _now()
            db.execute(
                """INSERT OR IGNORE INTO backtest_input_snapshots
                   (content_hash, schema_version, codec, payload, compressed_bytes,
                    uncompressed_bytes, row_count_target, row_count_benchmark, created_at)
                   VALUES (?, 1, 'gzip-json-v1', ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.content_hash,
                    snapshot.payload,
                    len(snapshot.payload),
                    snapshot.uncompressed_bytes,
                    snapshot.row_count_target,
                    snapshot.row_count_benchmark,
                    now,
                ),
            )
            persisted_snapshot = db.execute(
                "SELECT content_hash, schema_version, codec, payload, compressed_bytes, "
                "uncompressed_bytes, row_count_target, row_count_benchmark, created_at "
                "FROM backtest_input_snapshots WHERE content_hash = ?",
                (snapshot.content_hash,),
            ).fetchone()
            if persisted_snapshot is None:
                raise RuntimeError("bound backtest input snapshot is unavailable")
            _backtest_input_snapshot_from_row(persisted_snapshot)
            db.execute(
                """UPDATE backtest_jobs
                   SET input_snapshot_hash = ?, updated_at = ?
                   WHERE id = ? AND input_snapshot_hash IS NULL""",
                (snapshot.content_hash, now, job_id),
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise
        bound_snapshot = self.get_backtest_input_snapshot(snapshot.content_hash)
        if bound_snapshot is None:
            raise RuntimeError("bound backtest input snapshot is unavailable")
        return bound_snapshot

    def get_backtest_input_snapshot(
        self, content_hash: str
    ) -> BacktestInputSnapshotRecord | None:
        self._init_backtest_jobs_db()
        row = (
            self._system_db()
            .execute(
                """SELECT content_hash, schema_version, codec, payload, compressed_bytes,
                          uncompressed_bytes, row_count_target, row_count_benchmark, created_at
                   FROM backtest_input_snapshots WHERE content_hash = ?""",
                (content_hash,),
            )
            .fetchone()
        )
        return _backtest_input_snapshot_from_row(row) if row is not None else None

    def update_backtest_job_progress(self, job_id: str, progress_json: str) -> bool:
        self._init_backtest_jobs_db()
        cursor = self._system_db().execute(
            """UPDATE backtest_jobs
               SET progress_json = ?, updated_at = ?
               WHERE id = ? AND contract_version = 1""",
            (progress_json, _now(), job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def record_backtest_decision(self, evidence: BacktestDecisionEvidence) -> bool:
        if (
            evidence.error_code is not None
            and evidence.error_code not in _BACKTEST_DECISION_ERROR_CODES
        ) or (
            evidence.error_stage is not None
            and evidence.error_stage not in _BACKTEST_DECISION_ERROR_STAGES
        ):
            raise ValueError("backtest decision failure metadata is invalid")
        self._init_backtest_jobs_db()
        db = self._system_db()
        bound_job = db.execute(
            "SELECT input_snapshot_hash FROM backtest_jobs WHERE id = ? AND contract_version = 1",
            (evidence.job_id,),
        ).fetchone()
        if bound_job is None:
            raise RuntimeError("backtest decisions require a bound input snapshot")
        bound_snapshot_hash = _strict_persisted_nullable_text(
            bound_job["input_snapshot_hash"],
            message="backtest job metadata is invalid",
        )
        if bound_snapshot_hash is None:
            raise RuntimeError("backtest decisions require a bound input snapshot")
        now = _now()
        cursor = db.execute(
            """INSERT INTO backtest_decisions
               (job_id, sequence, signal_date, execution_date, status, attempts,
                target_position_pct, confidence, action, rationale, feature_hash,
                policy_hash, error_code, error_stage, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(job_id, sequence) DO UPDATE SET
                 signal_date = excluded.signal_date,
                 execution_date = excluded.execution_date,
                 status = excluded.status,
                 attempts = excluded.attempts,
                 target_position_pct = excluded.target_position_pct,
                 confidence = excluded.confidence,
                 action = excluded.action,
                 rationale = excluded.rationale,
                 feature_hash = excluded.feature_hash,
                 policy_hash = excluded.policy_hash,
                 error_code = excluded.error_code,
                 error_stage = excluded.error_stage,
                 updated_at = excluded.updated_at""",
            (
                evidence.job_id,
                evidence.sequence,
                evidence.signal_date,
                evidence.execution_date,
                evidence.status,
                evidence.attempts,
                evidence.target_position_pct,
                evidence.confidence,
                evidence.action,
                evidence.rationale,
                evidence.feature_hash,
                evidence.policy_hash,
                evidence.error_code,
                evidence.error_stage,
                now,
                now,
            ),
        )
        db.commit()
        return cursor.rowcount == 1

    def get_backtest_decisions(self, job_id: str) -> list[BacktestDecisionRecord]:
        self._init_backtest_jobs_db()
        rows = (
            self._system_db()
            .execute(
                """SELECT job_id, sequence, signal_date, execution_date, status, attempts,
                      target_position_pct, confidence, action, rationale, feature_hash, policy_hash,
                      error_code, error_stage, created_at, updated_at
               FROM backtest_decisions WHERE job_id = ? ORDER BY sequence""",
                (job_id,),
            )
            .fetchall()
        )
        return [_backtest_decision_from_row(row) for row in rows]

    def update_backtest_decision_execution(
        self, job_id: str, sequence: int, execution_date: str
    ) -> bool:
        self._init_backtest_jobs_db()
        db = self._system_db()
        cursor = db.execute(
            """UPDATE backtest_decisions
               SET execution_date = ?, updated_at = ?
               WHERE job_id = ? AND sequence = ? AND status = 'completed'""",
            (execution_date, _now(), job_id, sequence),
        )
        db.commit()
        return cursor.rowcount == 1

    def get_backtest_job(self, job_id: str) -> BacktestJobRecord | None:
        self._init_backtest_jobs_db()
        row = (
            self._system_db()
            .execute(
                """SELECT id, request_json, contract_version, run_spec_json,
                      input_snapshot_hash, progress_json, status, result_json, error_json,
                      created_at, started_at, completed_at, updated_at
               FROM backtest_jobs WHERE id = ?""",
                (job_id,),
            )
            .fetchone()
        )
        return _backtest_job_from_row(row) if row is not None else None

    def mark_backtest_job_running(self, job_id: str) -> bool:
        self._init_backtest_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE backtest_jobs
               SET status = 'running', started_at = ?, updated_at = ?
               WHERE id = ? AND status = 'pending'""",
            (now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def complete_backtest_job(self, job_id: str, result_json: str) -> bool:
        self._init_backtest_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE backtest_jobs
               SET status = 'completed', result_json = ?, error_json = NULL,
                   completed_at = ?, updated_at = ?
               WHERE id = ? AND status = 'running'
                 AND (contract_version = 0 OR input_snapshot_hash IS NOT NULL)""",
            (result_json, now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def fail_backtest_job(self, job_id: str, error_json: str) -> bool:
        self._init_backtest_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE backtest_jobs
               SET status = 'failed', error_json = ?, completed_at = ?, updated_at = ?
               WHERE id = ? AND status IN ('pending', 'running')""",
            (error_json, now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def recover_interrupted_backtest_jobs(self) -> int:
        self._init_backtest_jobs_db()
        now = _now()
        error_json = json.dumps(
            {
                "code": "interrupted",
                "message": "Backtest interrupted by server restart",
            }
        )
        cursor = self._system_db().execute(
            """UPDATE backtest_jobs
               SET status = 'failed', error_json = ?, completed_at = ?, updated_at = ?
               WHERE status IN ('pending', 'running')""",
            (error_json, now, now),
        )
        self._system_db().commit()
        return cursor.rowcount

    def _init_backtest_jobs_db(self) -> None:
        db = self._system_db()
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute(
                """CREATE TABLE IF NOT EXISTS backtest_jobs (
                    id TEXT PRIMARY KEY,
                    request_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )"""
            )
            migration = db.execute(
                "SELECT name FROM schema_migrations WHERE name = ?",
                (BACKTEST_CONTRACT_MIGRATION,),
            ).fetchone()
            columns = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(backtest_jobs)").fetchall()
            }
            is_legacy_jobs_schema = {
                "contract_version",
                "input_snapshot_hash",
                "progress_json",
            }.isdisjoint(columns)
            if migration is None:
                db.execute(
                    """CREATE TABLE IF NOT EXISTS backtest_input_snapshots (
                        content_hash TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL CHECK (schema_version = 1),
                        codec TEXT NOT NULL CHECK (codec = 'gzip-json-v1'),
                        payload BLOB NOT NULL,
                        compressed_bytes INTEGER NOT NULL,
                        uncompressed_bytes INTEGER NOT NULL,
                        row_count_target INTEGER NOT NULL,
                        row_count_benchmark INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )"""
                )
                if is_legacy_jobs_schema:
                    _rebuild_legacy_backtest_jobs_with_v1_contract(db, columns)
                    columns = {
                        str(row["name"])
                        for row in db.execute(
                            "PRAGMA table_info(backtest_jobs)"
                        ).fetchall()
                    }
                if "contract_version" not in columns:
                    db.execute(
                        "ALTER TABLE backtest_jobs ADD COLUMN contract_version INTEGER NOT NULL DEFAULT 0"
                    )
                if "run_spec_json" not in columns:
                    db.execute(
                        "ALTER TABLE backtest_jobs ADD COLUMN run_spec_json TEXT"
                    )
                if "input_snapshot_hash" not in columns:
                    db.execute(
                        "ALTER TABLE backtest_jobs ADD COLUMN input_snapshot_hash TEXT REFERENCES backtest_input_snapshots(content_hash)"
                    )
                if "progress_json" not in columns:
                    db.execute(
                        "ALTER TABLE backtest_jobs ADD COLUMN progress_json TEXT"
                    )
                db.execute(
                    """CREATE TABLE IF NOT EXISTS backtest_decisions (
                        job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
                        sequence INTEGER NOT NULL,
                        signal_date TEXT NOT NULL,
                        execution_date TEXT,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL,
                        target_position_pct REAL,
                        confidence REAL,
                        action TEXT,
                        rationale TEXT,
                        feature_hash TEXT,
                        policy_hash TEXT NOT NULL,
                        error_code TEXT,
                        error_stage TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (job_id, sequence)
                    )"""
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_backtest_decisions_job ON backtest_decisions(job_id)"
                )
                db.execute(
                    "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
                    (BACKTEST_CONTRACT_MIGRATION, _now()),
                )
            decision_columns = {
                str(row["name"])
                for row in db.execute(
                    "PRAGMA table_info(backtest_decisions)"
                ).fetchall()
            }
            if "action" not in decision_columns:
                db.execute("ALTER TABLE backtest_decisions ADD COLUMN action TEXT")
            if "rationale" not in decision_columns:
                db.execute("ALTER TABLE backtest_decisions ADD COLUMN rationale TEXT")
            if not _backtest_v1_schema_is_consistent(db):
                raise BacktestMigrationContractError()
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_backtest_jobs_status ON backtest_jobs(status)"
            )
            db.commit()
        except BaseException:
            db.rollback()
            raise

    def create_scan_run(
        self,
        run_id: str,
        input_json: str,
        mode: str,
        strategy_id: str | None = None,
    ) -> ScanRunRecord:
        self._init_scan_runs_db()
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT INTO scan_runs
               (id, input_json, compiled_conditions_json, result_json, error_json,
                status, mode, strategy_id, created_at, completed_at, updated_at)
               VALUES (?, ?, NULL, NULL, NULL, 'running', ?, ?, ?, NULL, ?)""",
            (run_id, input_json, mode, strategy_id, now, now),
        )
        db.commit()
        run = self.get_scan_run(run_id)
        if run is None:
            raise RuntimeError("scan run was not persisted")
        return run

    def complete_scan_run(
        self, run_id: str, compiled_conditions_json: str, result_json: str
    ) -> bool:
        self._init_scan_runs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE scan_runs
               SET status = 'completed', compiled_conditions_json = ?, result_json = ?,
                   error_json = NULL, completed_at = ?, updated_at = ?
               WHERE id = ? AND status = 'running'""",
            (compiled_conditions_json, result_json, now, now, run_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def fail_scan_run(
        self,
        run_id: str,
        error_json: str,
        compiled_conditions_json: str | None = None,
    ) -> bool:
        self._init_scan_runs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE scan_runs
               SET status = 'failed', compiled_conditions_json = COALESCE(?, compiled_conditions_json),
                   error_json = ?, completed_at = ?, updated_at = ?
               WHERE id = ? AND status = 'running'""",
            (compiled_conditions_json, error_json, now, now, run_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def get_scan_run(self, run_id: str) -> ScanRunRecord | None:
        self._init_scan_runs_db()
        row = (
            self._system_db()
            .execute(
                """SELECT id, input_json, compiled_conditions_json, result_json, error_json,
                          status, mode, strategy_id, created_at, completed_at, updated_at
                   FROM scan_runs WHERE id = ?""",
                (run_id,),
            )
            .fetchone()
        )
        return _scan_run_from_row(row) if row is not None else None

    def list_scan_runs(
        self, status: ScanRunStatus | None = None, limit: int = 50
    ) -> list[ScanRunRecord]:
        self._init_scan_runs_db()
        if status is None:
            rows = (
                self._system_db()
                .execute(
                    """SELECT id, input_json, compiled_conditions_json, result_json, error_json,
                          status, mode, strategy_id, created_at, completed_at, updated_at
                   FROM scan_runs ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                )
                .fetchall()
            )
        else:
            rows = (
                self._system_db()
                .execute(
                    """SELECT id, input_json, compiled_conditions_json, result_json, error_json,
                          status, mode, strategy_id, created_at, completed_at, updated_at
                   FROM scan_runs WHERE status = ? ORDER BY created_at DESC LIMIT ?""",
                    (status, limit),
                )
                .fetchall()
            )
        return [_scan_run_from_row(row) for row in rows]

    def _init_scan_runs_db(self) -> None:
        db = self._system_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS scan_runs (
                id TEXT PRIMARY KEY,
                input_json TEXT NOT NULL,
                compiled_conditions_json TEXT,
                result_json TEXT,
                error_json TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                mode TEXT NOT NULL,
                strategy_id TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_runs_created_at ON scan_runs(created_at DESC)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_runs_status ON scan_runs(status)"
        )
        db.commit()

    def create_insight_generation(
        self, generation_id: str, hours: int
    ) -> InsightGenerationRecord:
        self._init_insight_generations_db()
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT OR IGNORE INTO insight_generations
               (id, hours, status, progress_json, result_insight_id, error,
                created_at, started_at, completed_at, updated_at)
               VALUES (?, ?, 'pending', '{}', NULL, NULL, ?, NULL, NULL, ?)""",
            (generation_id, hours, now, now),
        )
        db.commit()
        generation = self.get_insight_generation(generation_id)
        if generation is None:
            raise RuntimeError("insight generation was not persisted")
        return generation

    def get_insight_generation(
        self, generation_id: str
    ) -> InsightGenerationRecord | None:
        self._init_insight_generations_db()
        row = (
            self._system_db()
            .execute("SELECT * FROM insight_generations WHERE id = ?", (generation_id,))
            .fetchone()
        )
        return _insight_generation_from_row(row) if row is not None else None

    def mark_insight_generation_running(self, generation_id: str) -> bool:
        self._init_insight_generations_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE insight_generations
               SET status = 'running', started_at = ?, updated_at = ?
               WHERE id = ? AND status = 'pending'""",
            (now, now, generation_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def update_insight_generation_progress(
        self, generation_id: str, progress_json: str
    ) -> bool:
        self._init_insight_generations_db()
        cursor = self._system_db().execute(
            """UPDATE insight_generations SET progress_json = ?, updated_at = ?
               WHERE id = ? AND status = 'running'""",
            (progress_json, _now(), generation_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def complete_insight_generation(
        self, generation_id: str, insight_id: str
    ) -> bool:
        self._init_insight_generations_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE insight_generations
               SET status = 'completed', result_insight_id = ?, error = NULL,
                   completed_at = ?, updated_at = ?
               WHERE id = ? AND status = 'running'""",
            (insight_id, now, now, generation_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def fail_insight_generation(self, generation_id: str, error: str) -> bool:
        self._init_insight_generations_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE insight_generations
               SET status = 'failed', result_insight_id = NULL, error = ?,
                   completed_at = ?, updated_at = ?
               WHERE id = ? AND status IN ('pending', 'running')""",
            (error, now, now, generation_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def recover_interrupted_insight_generations(self) -> int:
        self._init_insight_generations_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE insight_generations
               SET status = 'failed', result_insight_id = NULL,
                   error = 'Insight generation interrupted by server restart',
                   completed_at = ?, updated_at = ?
               WHERE status IN ('pending', 'running')""",
            (now, now),
        )
        self._system_db().commit()
        return cursor.rowcount

    def _init_insight_generations_db(self) -> None:
        db = self._system_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS insight_generations (
                id TEXT PRIMARY KEY,
                hours INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                progress_json TEXT NOT NULL DEFAULT '{}',
                result_insight_id TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_insight_generations_status ON insight_generations(status)"
        )
        db.commit()

    def create_report_job(
        self,
        job_id: str,
        report_type: str,
        title: str,
        tickers_json: str,
        source_type: str,
        source_ids_json: str,
        parameters_json: str,
    ) -> ReportJobRecord:
        self._init_report_jobs_db()
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT INTO report_jobs
               (id, report_type, title, tickers_json, source_type, source_ids_json,
                parameters_json, status, artifact_name, error, created_at,
                started_at, completed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, ?, NULL, NULL, ?)""",
            (
                job_id,
                report_type,
                title,
                tickers_json,
                source_type,
                source_ids_json,
                parameters_json,
                now,
                now,
            ),
        )
        db.commit()
        job = self.get_report_job(job_id)
        if job is None:
            raise RuntimeError("report job was not persisted")
        return job

    def get_report_job(self, job_id: str) -> ReportJobRecord | None:
        self._init_report_jobs_db()
        row = (
            self._system_db()
            .execute("SELECT * FROM report_jobs WHERE id = ?", (job_id,))
            .fetchone()
        )
        return _report_job_from_row(row) if row is not None else None

    def list_report_jobs(self, limit: int = 50) -> list[ReportJobRecord]:
        self._init_report_jobs_db()
        rows = (
            self._system_db()
            .execute(
                "SELECT * FROM report_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            .fetchall()
        )
        return [_report_job_from_row(row) for row in rows]

    def mark_report_job_running(self, job_id: str) -> bool:
        self._init_report_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE report_jobs SET status='running', started_at=?, updated_at=?
               WHERE id=? AND status='pending'""",
            (now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def complete_report_job(self, job_id: str, artifact_name: str) -> bool:
        self._init_report_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE report_jobs SET status='completed', artifact_name=?, error=NULL,
               completed_at=?, updated_at=? WHERE id=? AND status='running'""",
            (artifact_name, now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def fail_report_job(self, job_id: str, error: str) -> bool:
        self._init_report_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE report_jobs SET status='failed', artifact_name=NULL, error=?,
               completed_at=?, updated_at=?
               WHERE id=? AND status IN ('pending', 'running')""",
            (error, now, now, job_id),
        )
        self._system_db().commit()
        return cursor.rowcount == 1

    def recover_interrupted_report_jobs(self) -> int:
        self._init_report_jobs_db()
        now = _now()
        cursor = self._system_db().execute(
            """UPDATE report_jobs SET status='failed', artifact_name=NULL,
               error='Report interrupted by server restart', completed_at=?, updated_at=?
               WHERE status IN ('pending', 'running')""",
            (now, now),
        )
        self._system_db().commit()
        return cursor.rowcount

    def _init_report_jobs_db(self) -> None:
        db = self._system_db()
        db.execute(
            """CREATE TABLE IF NOT EXISTS report_jobs (
                id TEXT PRIMARY KEY,
                report_type TEXT NOT NULL CHECK (report_type IN ('stock', 'sector')),
                title TEXT NOT NULL,
                tickers_json TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ids_json TEXT NOT NULL,
                parameters_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
                artifact_name TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                completed_at TEXT,
                updated_at TEXT NOT NULL
            )"""
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_report_jobs_created_at ON report_jobs(created_at DESC)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_report_jobs_status ON report_jobs(status)"
        )
        db.commit()

    # ── Storage management ──────────────────────────────────

    def _get_conn(self, db_name: str) -> sqlite3.Connection:
        import threading

        key = (db_name, threading.current_thread().ident)
        if key not in self._conns:
            path = self.data_dir / db_name
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or int(foreign_keys[0]) != 1:
                raise RuntimeError("SQLite foreign_keys pragma could not be enabled")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._conns[key] = conn
        return self._conns[key]

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
        # Reset singleton so next get_store() creates a fresh instance
        global _store
        _store = None

    def delete_strategy_data(self, strategy_id: str) -> None:
        """Delete a strategy's database file."""
        path = self.data_dir / f"{strategy_id}.db"
        db_name = f"{strategy_id}.db"
        keys_to_remove = [key for key in self._conns if key[0] == db_name]
        for key in keys_to_remove:
            self._conns[key].close()
            del self._conns[key]
        path.unlink(missing_ok=True)


def _monitor_row_to_dict(row) -> dict:
    d = dict(row)
    for k in (
        "targets_json",
        "sources_json",
        "schedule_json",
        "agent_json",
        "output_json",
        "expanded_keywords_json",
        "expanded_tickers_json",
    ):
        try:
            d[k.replace("_json", "")] = json.loads(d.pop(k, "{}"))
        except Exception:
            d[k.replace("_json", "")] = []
    return d


def _strict_persisted_int(value: object, *, message: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise RuntimeError(message)


def _strict_persisted_text(value: object, *, message: str) -> str:
    if isinstance(value, str):
        return value
    raise RuntimeError(message)


def _strict_persisted_nullable_text(value: object, *, message: str) -> str | None:
    if value is None:
        return None
    return _strict_persisted_text(value, message=message)


def _strict_persisted_nullable_real(value: object, *, message: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RuntimeError(message)
    normalized = float(value)
    if not math.isfinite(normalized):
        raise RuntimeError(message)
    return normalized


def _backtest_job_from_row(row: sqlite3.Row) -> BacktestJobRecord:
    metadata_error = "backtest job metadata is invalid"
    status = _strict_persisted_text(row["status"], message=metadata_error)
    match status:
        case "pending":
            normalized_status: BacktestJobStatus = "pending"
        case "running":
            normalized_status = "running"
        case "completed":
            normalized_status = "completed"
        case "failed":
            normalized_status = "failed"
        case _:
            raise RuntimeError("invalid persisted backtest job status")
    contract_version = _strict_persisted_int(
        row["contract_version"], message=metadata_error
    )
    if contract_version not in {0, 1}:
        raise RuntimeError(metadata_error)
    return BacktestJobRecord(
        id=_strict_persisted_text(row["id"], message=metadata_error),
        request_json=_strict_persisted_text(
            row["request_json"], message=metadata_error
        ),
        contract_version=contract_version,
        run_spec_json=_strict_persisted_nullable_text(
            row["run_spec_json"], message=metadata_error
        ),
        input_snapshot_hash=_strict_persisted_nullable_text(
            row["input_snapshot_hash"], message=metadata_error
        ),
        progress_json=_strict_persisted_nullable_text(
            row["progress_json"], message=metadata_error
        ),
        status=normalized_status,
        result_json=_strict_persisted_nullable_text(
            row["result_json"], message=metadata_error
        ),
        error_json=_strict_persisted_nullable_text(
            row["error_json"], message=metadata_error
        ),
        created_at=_strict_persisted_text(row["created_at"], message=metadata_error),
        started_at=_strict_persisted_nullable_text(
            row["started_at"], message=metadata_error
        ),
        completed_at=_strict_persisted_nullable_text(
            row["completed_at"], message=metadata_error
        ),
        updated_at=_strict_persisted_text(row["updated_at"], message=metadata_error),
    )


def _validate_backtest_snapshot_payload(
    canonical_payload: bytes,
    *,
    row_count_target: int,
    row_count_benchmark: int,
) -> None:
    try:
        payload = json.loads(canonical_payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("backtest input snapshot JSON is invalid") from error
    if not isinstance(payload, dict) or set(payload) not in (
        {"benchmark", "schema_version", "target"},
        {"benchmark", "data_provenance", "schema_version", "target"},
    ):
        raise RuntimeError("backtest input snapshot schema is invalid")
    if payload.get("schema_version") != 1:
        raise RuntimeError("backtest input snapshot schema is invalid")
    for name, expected_rows in (
        ("target", row_count_target),
        ("benchmark", row_count_benchmark),
    ):
        frame = payload.get(name)
        if (
            not isinstance(frame, dict)
            or set(frame) != {"columns", "rows"}
            or not isinstance(frame.get("columns"), list)
            or not isinstance(frame.get("rows"), list)
            or len(frame["rows"]) != expected_rows
        ):
            raise RuntimeError("backtest input snapshot frame is invalid")
        columns = frame["columns"]
        rows = frame["rows"]
        canonical_columns = ["Open", "High", "Low", "Close", "Volume"]
        if columns not in ([], canonical_columns) or (rows and not columns):
            raise RuntimeError("backtest input snapshot frame is invalid")
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns) + 1:
                raise RuntimeError("backtest input snapshot row is invalid")
            try:
                date.fromisoformat(str(row[0]))
                values = [float(value) for value in row[1:]]
            except (TypeError, ValueError) as error:
                raise RuntimeError("backtest input snapshot row is invalid") from error
            if any(not math.isfinite(value) for value in values):
                raise RuntimeError("backtest input snapshot row is invalid")
            open_price, high, low, close, volume = values
            if (
                min(open_price, high, low, close) <= 0
                or high < max(open_price, close, low)
                or low > min(open_price, close, high)
                or volume < 0
            ):
                raise RuntimeError("backtest input snapshot row is invalid")
    provenance = payload.get("data_provenance")
    if provenance is not None:
        allowed_keys = {
            "actions",
            "auto_adjust",
            "corporate_actions_mode",
            "date_from",
            "date_to",
            "end_exclusive",
            "interval",
            "library_version",
            "lookback_days",
            "provider",
            "provider_buffer_days",
            "provider_end_semantics",
            "provider_timezone",
            "row_adjustment_modes",
            "ticker",
            "timezone_normalization",
            "warmup_bars",
        }
        if not isinstance(provenance, dict) or set(provenance) != {
            "target",
            "benchmark",
        }:
            raise RuntimeError("backtest input snapshot provenance is invalid")
        for value in provenance.values():
            if not isinstance(value, dict) or not set(value).issubset(allowed_keys):
                raise RuntimeError("backtest input snapshot provenance is invalid")
            for key, item in value.items():
                if key == "row_adjustment_modes":
                    if (
                        not isinstance(item, list)
                        or len(item) != 1
                        or item[0]
                        not in {"unknown", "raw_prices", "provider_adjusted_prices"}
                    ):
                        raise RuntimeError(
                            "backtest input snapshot provenance is invalid"
                        )
                elif not isinstance(item, str | int | bool):
                    raise RuntimeError("backtest input snapshot provenance is invalid")
            if value.get("provider") not in {None, "yfinance"}:
                raise RuntimeError("backtest input snapshot provenance is invalid")
            if value.get("interval") not in {None, "1d"}:
                raise RuntimeError("backtest input snapshot provenance is invalid")
            if value.get("auto_adjust") not in {None, True}:
                raise RuntimeError("backtest input snapshot provenance is invalid")
            if value.get("actions") not in {None, False}:
                raise RuntimeError("backtest input snapshot provenance is invalid")


def _decode_backtest_input_snapshot_payload(
    payload: bytes,
    *,
    compressed_bytes: int,
    uncompressed_bytes: int,
    content_hash: str,
) -> bytes:
    return decode_canonical_snapshot(
        CanonicalSnapshotEnvelope(
            payload=payload,
            compressed_bytes=compressed_bytes,
            uncompressed_bytes=uncompressed_bytes,
            content_hash=content_hash,
            maximum_uncompressed_bytes=_MAX_BACKTEST_INPUT_SNAPSHOT_BYTES,
        )
    )


def _backtest_input_snapshot_from_row(
    row: sqlite3.Row,
) -> BacktestInputSnapshotRecord:
    metadata_error = "backtest input snapshot metadata is invalid"
    payload = row["payload"]
    if not isinstance(payload, bytes):
        raise RuntimeError(metadata_error)
    compressed_bytes = _strict_persisted_int(
        row["compressed_bytes"], message=metadata_error
    )
    uncompressed_bytes = _strict_persisted_int(
        row["uncompressed_bytes"], message=metadata_error
    )
    schema_version = _strict_persisted_int(
        row["schema_version"], message=metadata_error
    )
    row_count_target = _strict_persisted_int(
        row["row_count_target"], message=metadata_error
    )
    row_count_benchmark = _strict_persisted_int(
        row["row_count_benchmark"], message=metadata_error
    )
    content_hash = _strict_persisted_text(row["content_hash"], message=metadata_error)
    codec = _strict_persisted_text(row["codec"], message=metadata_error)
    created_at = _strict_persisted_text(row["created_at"], message=metadata_error)
    if (
        schema_version != 1
        or codec != "gzip-json-v1"
        or compressed_bytes < 0
        or uncompressed_bytes < 0
        or row_count_target < 0
        or row_count_benchmark < 0
    ):
        raise RuntimeError(metadata_error)
    _decode_backtest_input_snapshot_payload(
        payload,
        compressed_bytes=compressed_bytes,
        uncompressed_bytes=uncompressed_bytes,
        content_hash=content_hash,
    )
    return BacktestInputSnapshotRecord(
        content_hash=content_hash,
        schema_version=schema_version,
        codec=codec,
        payload=payload,
        compressed_bytes=compressed_bytes,
        uncompressed_bytes=uncompressed_bytes,
        row_count_target=row_count_target,
        row_count_benchmark=row_count_benchmark,
        created_at=created_at,
    )


def _backtest_decision_from_row(row: sqlite3.Row) -> BacktestDecisionRecord:
    metadata_error = "backtest decision metadata is invalid"
    sequence = _strict_persisted_int(row["sequence"], message=metadata_error)
    attempts = _strict_persisted_int(row["attempts"], message=metadata_error)
    if sequence <= 0 or attempts <= 0:
        raise RuntimeError(metadata_error)
    target_position_pct = _strict_persisted_nullable_real(
        row["target_position_pct"], message=metadata_error
    )
    confidence = _strict_persisted_nullable_real(
        row["confidence"], message=metadata_error
    )
    if target_position_pct is not None and not 0 <= target_position_pct <= 100:
        raise RuntimeError(metadata_error)
    if confidence is not None and not 0 <= confidence <= 1:
        raise RuntimeError(metadata_error)
    job_id = _strict_persisted_text(row["job_id"], message=metadata_error)
    signal_date = _strict_persisted_text(row["signal_date"], message=metadata_error)
    execution_date = _strict_persisted_nullable_text(
        row["execution_date"], message=metadata_error
    )
    rationale = _strict_persisted_nullable_text(
        row["rationale"], message=metadata_error
    )
    feature_hash = _strict_persisted_nullable_text(
        row["feature_hash"], message=metadata_error
    )
    policy_hash = _strict_persisted_text(row["policy_hash"], message=metadata_error)
    error_code = _strict_persisted_nullable_text(
        row["error_code"], message=metadata_error
    )
    error_stage = _strict_persisted_nullable_text(
        row["error_stage"], message=metadata_error
    )
    if (
        error_code is not None and error_code not in _BACKTEST_DECISION_ERROR_CODES
    ) or (
        error_stage is not None and error_stage not in _BACKTEST_DECISION_ERROR_STAGES
    ):
        raise RuntimeError(metadata_error)
    return BacktestDecisionRecord(
        job_id=job_id,
        sequence=sequence,
        signal_date=signal_date,
        execution_date=execution_date,
        status=_backtest_decision_status_from_row(row),
        attempts=attempts,
        target_position_pct=target_position_pct,
        confidence=confidence,
        action=_backtest_decision_action_from_row(row, message=metadata_error),
        rationale=rationale,
        feature_hash=feature_hash,
        policy_hash=policy_hash,
        error_code=error_code,
        error_stage=error_stage,
        created_at=_strict_persisted_text(row["created_at"], message=metadata_error),
        updated_at=_strict_persisted_text(row["updated_at"], message=metadata_error),
    )


def _backtest_decision_status_from_row(row: sqlite3.Row) -> BacktestDecisionStatus:
    status = _strict_persisted_text(
        row["status"], message="backtest decision metadata is invalid"
    )
    match status:
        case "not_ready":
            return "not_ready"
        case "completed":
            return "completed"
        case "failed":
            return "failed"
        case "unfilled_end_of_window":
            return "unfilled_end_of_window"
        case _:
            raise RuntimeError("invalid persisted backtest decision status")


def _backtest_decision_action_from_row(
    row: sqlite3.Row,
    *,
    message: str,
) -> BacktestDecisionAction | None:
    action = _strict_persisted_nullable_text(row["action"], message=message)
    match action:
        case None:
            return None
        case "BUY":
            return "BUY"
        case "SELL":
            return "SELL"
        case "HOLD":
            return "HOLD"
        case _:
            raise RuntimeError("invalid persisted backtest decision action")


def _backtest_v1_schema_is_consistent(db: sqlite3.Connection) -> bool:
    jobs_info = db.execute("PRAGMA table_info(backtest_jobs)").fetchall()
    snapshot_info = db.execute("PRAGMA table_info(backtest_input_snapshots)").fetchall()
    decision_info = db.execute("PRAGMA table_info(backtest_decisions)").fetchall()
    migration_info = db.execute("PRAGMA table_info(schema_migrations)").fetchall()
    jobs_fk = db.execute("PRAGMA foreign_key_list(backtest_jobs)").fetchall()
    snapshot_fk = db.execute(
        "PRAGMA foreign_key_list(backtest_input_snapshots)"
    ).fetchall()
    decision_fk = db.execute("PRAGMA foreign_key_list(backtest_decisions)").fetchall()
    migration_fk = db.execute("PRAGMA foreign_key_list(schema_migrations)").fetchall()
    jobs_fk_is_clean = _sqlite_foreign_key_check_is_clean(db, "backtest_jobs")
    decision_fk_is_clean = _sqlite_foreign_key_check_is_clean(
        db,
        "backtest_decisions",
    )
    decision_index = _sqlite_named_index_matches(
        db,
        "backtest_decisions",
        "idx_backtest_decisions_job",
        ("job_id",),
    )
    return (
        _sqlite_columns_match_contract(
            jobs_info,
            _BACKTEST_JOB_COLUMN_CONTRACT,
            allow_extra_columns=True,
        )
        and _sqlite_columns_match_contract(
            snapshot_info,
            _BACKTEST_INPUT_SNAPSHOT_COLUMN_CONTRACT,
        )
        and _sqlite_columns_match_contract(
            decision_info,
            _BACKTEST_DECISION_COLUMN_CONTRACT,
        )
        and _sqlite_columns_match_contract(
            migration_info,
            _BACKTEST_MIGRATION_COLUMN_CONTRACT,
        )
        and not snapshot_fk
        and not migration_fk
        and jobs_fk_is_clean
        and decision_fk_is_clean
        and _sqlite_snapshot_checks_match_contract(db)
        and _sqlite_jobs_status_check_matches_contract(db)
        and _sqlite_foreign_keys_are_immediate(db)
        and len(jobs_fk) == 1
        and int(jobs_fk[0]["id"]) == 0
        and int(jobs_fk[0]["seq"]) == 0
        and str(jobs_fk[0]["table"]) == "backtest_input_snapshots"
        and str(jobs_fk[0]["from"]) == "input_snapshot_hash"
        and str(jobs_fk[0]["to"]) == "content_hash"
        and str(jobs_fk[0]["on_update"]).upper() == "NO ACTION"
        and str(jobs_fk[0]["on_delete"]).upper() == "NO ACTION"
        and str(jobs_fk[0]["match"]).upper() == "NONE"
        and len(decision_fk) == 1
        and int(decision_fk[0]["id"]) == 0
        and int(decision_fk[0]["seq"]) == 0
        and str(decision_fk[0]["table"]) == "backtest_jobs"
        and str(decision_fk[0]["from"]) == "job_id"
        and str(decision_fk[0]["to"]) == "id"
        and str(decision_fk[0]["on_update"]).upper() == "NO ACTION"
        and str(decision_fk[0]["on_delete"]).upper() == "CASCADE"
        and str(decision_fk[0]["match"]).upper() == "NONE"
        and decision_index
    )


def _sqlite_snapshot_checks_match_contract(db: sqlite3.Connection) -> bool:
    statement = """INSERT INTO backtest_input_snapshots
        (content_hash, schema_version, codec, payload, compressed_bytes,
         uncompressed_bytes, row_count_target, row_count_benchmark, created_at)
        VALUES (lower(hex(randomblob(16))), ?, ?, X'', 0, 0, 0, 0, '1970-01-01T00:00:00Z')"""
    db.execute("SAVEPOINT backtest_snapshot_check_contract")
    try:
        db.execute(statement, (1, "gzip-json-v1"))
        return (
            _sqlite_rejects_integrity_error(
                db,
                statement,
                (2, "gzip-json-v1"),
            )
            and _sqlite_rejects_integrity_error(
                db,
                statement,
                (1, "other"),
            )
            and _sqlite_rejects_integrity_error(
                db,
                statement,
                (1, "invalid-codec"),
            )
        )
    except sqlite3.DatabaseError:
        return False
    finally:
        db.execute("ROLLBACK TO backtest_snapshot_check_contract")
        db.execute("RELEASE backtest_snapshot_check_contract")


def _rebuild_legacy_backtest_jobs_with_v1_contract(
    db: sqlite3.Connection,
    columns: set[str],
) -> None:
    legacy_columns = {
        "id",
        "request_json",
        "status",
        "result_json",
        "error_json",
        "created_at",
        "started_at",
        "completed_at",
        "updated_at",
    }
    supported_columns = legacy_columns | {"run_spec_json"}
    if not legacy_columns <= columns or not columns <= supported_columns:
        raise BacktestMigrationContractError()
    if _sqlite_table_exists(db, "backtest_decisions") or _sqlite_table_exists(
        db,
        "backtest_jobs_legacy_v1_source",
    ):
        raise BacktestMigrationContractError()
    run_spec_expression = "run_spec_json" if "run_spec_json" in columns else "NULL"
    db.execute("ALTER TABLE backtest_jobs RENAME TO backtest_jobs_legacy_v1_source")
    db.execute(
        """CREATE TABLE backtest_jobs (
            id TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            contract_version INTEGER NOT NULL DEFAULT 0,
            run_spec_json TEXT,
            input_snapshot_hash TEXT REFERENCES backtest_input_snapshots(content_hash),
            progress_json TEXT,
            status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
            result_json TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT NOT NULL
        )"""
    )
    try:
        db.execute(
            f"""INSERT INTO backtest_jobs
                (id, request_json, contract_version, run_spec_json, input_snapshot_hash,
                 progress_json, status, result_json, error_json, created_at, started_at,
                 completed_at, updated_at)
                SELECT id, request_json, 0, {run_spec_expression}, NULL, NULL, status,
                       result_json, error_json, created_at, started_at, completed_at, updated_at
                FROM backtest_jobs_legacy_v1_source"""
        )
    except sqlite3.DatabaseError as exc:
        raise BacktestMigrationContractError() from exc
    db.execute("DROP TABLE backtest_jobs_legacy_v1_source")


def _sqlite_table_exists(db: sqlite3.Connection, table_name: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _sqlite_jobs_status_check_matches_contract(db: sqlite3.Connection) -> bool:
    statement = """INSERT INTO backtest_jobs
        (id, request_json, contract_version, run_spec_json, input_snapshot_hash,
         progress_json, status, result_json, error_json, created_at, started_at,
         completed_at, updated_at)
        VALUES (lower(hex(randomblob(16))), '{}', 1, '{}', NULL, NULL, ?, NULL,
                NULL, '1970-01-01T00:00:00Z', NULL, NULL, '1970-01-01T00:00:00Z')"""
    invalid_statement = statement.replace("?", "lower(hex(randomblob(16)))", 1)
    db.execute("SAVEPOINT backtest_jobs_status_check_contract")
    try:
        for valid_status in ("pending", "running", "completed", "failed"):
            db.execute(statement, (valid_status,))
        return _sqlite_rejects_integrity_error(db, invalid_statement)
    except sqlite3.DatabaseError:
        return False
    finally:
        db.execute("ROLLBACK TO backtest_jobs_status_check_contract")
        db.execute("RELEASE backtest_jobs_status_check_contract")


def _sqlite_foreign_keys_are_immediate(db: sqlite3.Connection) -> bool:
    job_statement = """INSERT INTO backtest_jobs
        (id, request_json, contract_version, run_spec_json, input_snapshot_hash,
         progress_json, status, result_json, error_json, created_at, started_at,
         completed_at, updated_at)
        VALUES (lower(hex(randomblob(16))), '{}', 1, '{}', lower(hex(randomblob(16))),
                NULL, 'pending', NULL, NULL, '1970-01-01T00:00:00Z', NULL, NULL,
                '1970-01-01T00:00:00Z')"""
    decision_statement = """INSERT INTO backtest_decisions
        (job_id, sequence, signal_date, execution_date, status, attempts,
         target_position_pct, confidence, feature_hash, policy_hash, error_code,
         error_stage, created_at, updated_at)
        VALUES (lower(hex(randomblob(16))), 1, '1970-01-01T00:00:00Z', NULL,
                'failed', 1, NULL, NULL, NULL, 'a', NULL, NULL,
                '1970-01-01T00:00:00Z', '1970-01-01T00:00:00Z')"""
    db.execute("SAVEPOINT backtest_foreign_key_contract")
    try:
        return _sqlite_rejects_integrity_error(
            db,
            job_statement,
        ) and _sqlite_rejects_integrity_error(
            db,
            decision_statement,
        )
    except sqlite3.DatabaseError:
        return False
    finally:
        db.execute("ROLLBACK TO backtest_foreign_key_contract")
        db.execute("RELEASE backtest_foreign_key_contract")


def _sqlite_foreign_key_check_is_clean(
    db: sqlite3.Connection,
    table_name: str,
) -> bool:
    try:
        return not db.execute(f"PRAGMA foreign_key_check({table_name})").fetchall()
    except sqlite3.DatabaseError:
        return False


def _sqlite_rejects_integrity_error(
    db: sqlite3.Connection,
    statement: str,
    params: tuple[object, ...] = (),
) -> bool:
    try:
        db.execute(statement, params)
    except sqlite3.IntegrityError:
        return True
    return False


def _sqlite_columns_match_contract(
    rows: list[sqlite3.Row],
    contract: Mapping[str, _SqliteColumnContract],
    *,
    allow_extra_columns: bool = False,
) -> bool:
    columns = {str(row["name"]): row for row in rows}
    if not set(contract) <= set(columns):
        return False
    if not allow_extra_columns and set(columns) != set(contract):
        return False
    return all(
        str(columns[name]["type"]).upper() == expected_type
        and int(columns[name]["notnull"]) == int(expected_not_null)
        and (
            str(columns[name]["dflt_value"])
            if columns[name]["dflt_value"] is not None
            else None
        )
        == expected_default
        and int(columns[name]["pk"]) == expected_pk
        for name, (
            expected_type,
            expected_not_null,
            expected_default,
            expected_pk,
        ) in contract.items()
    )


def _sqlite_named_index_matches(
    db: sqlite3.Connection,
    table_name: str,
    index_name: str,
    expected_columns: tuple[str, ...],
) -> bool:
    indexes = db.execute(f"PRAGMA index_list({table_name})").fetchall()
    matching_indexes = [row for row in indexes if str(row["name"]) == index_name]
    if len(matching_indexes) != 1:
        return False
    index = matching_indexes[0]
    if (
        int(index["unique"]) != 0
        or str(index["origin"]).lower() != "c"
        or int(index["partial"]) != 0
    ):
        return False
    columns = sorted(
        db.execute(f"PRAGMA index_info({index_name})").fetchall(),
        key=lambda row: int(row["seqno"]),
    )
    return tuple(str(row["name"]) for row in columns) == expected_columns


def _scan_run_from_row(row: sqlite3.Row) -> ScanRunRecord:
    status = str(row["status"])
    match status:
        case "running":
            normalized_status: ScanRunStatus = "running"
        case "completed":
            normalized_status = "completed"
        case "failed":
            normalized_status = "failed"
        case _:
            raise RuntimeError("invalid persisted scan run status")
    return ScanRunRecord(
        id=str(row["id"]),
        input_json=str(row["input_json"]),
        compiled_conditions_json=(
            str(row["compiled_conditions_json"])
            if row["compiled_conditions_json"]
            else None
        ),
        result_json=str(row["result_json"]) if row["result_json"] else None,
        error_json=str(row["error_json"]) if row["error_json"] else None,
        status=normalized_status,
        mode=str(row["mode"]),
        strategy_id=str(row["strategy_id"]) if row["strategy_id"] else None,
        created_at=str(row["created_at"]),
        completed_at=str(row["completed_at"]) if row["completed_at"] else None,
        updated_at=str(row["updated_at"]),
    )


def _report_job_from_row(row: sqlite3.Row) -> ReportJobRecord:
    status = str(row["status"])
    match status:
        case "pending":
            normalized_status: ReportJobStatus = "pending"
        case "running":
            normalized_status = "running"
        case "completed":
            normalized_status = "completed"
        case "failed":
            normalized_status = "failed"
        case _:
            raise RuntimeError("invalid persisted report job status")
    return ReportJobRecord(
        id=str(row["id"]),
        report_type=str(row["report_type"]),
        title=str(row["title"]),
        tickers_json=str(row["tickers_json"]),
        source_type=str(row["source_type"]),
        source_ids_json=str(row["source_ids_json"]),
        parameters_json=str(row["parameters_json"]),
        status=normalized_status,
        artifact_name=str(row["artifact_name"]) if row["artifact_name"] else None,
        error=str(row["error"]) if row["error"] else None,
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        completed_at=(str(row["completed_at"]) if row["completed_at"] else None),
        updated_at=str(row["updated_at"]),
    )


def _insight_generation_from_row(row: sqlite3.Row) -> InsightGenerationRecord:
    status = str(row["status"])
    match status:
        case "pending":
            normalized_status: InsightGenerationStatus = "pending"
        case "running":
            normalized_status = "running"
        case "completed":
            normalized_status = "completed"
        case "failed":
            normalized_status = "failed"
        case _:
            raise RuntimeError("invalid persisted insight generation status")
    return InsightGenerationRecord(
        id=str(row["id"]),
        hours=int(row["hours"]),
        status=normalized_status,
        progress_json=str(row["progress_json"]),
        result_insight_id=(
            str(row["result_insight_id"]) if row["result_insight_id"] else None
        ),
        error=str(row["error"]) if row["error"] else None,
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] else None,
        completed_at=(str(row["completed_at"]) if row["completed_at"] else None),
        updated_at=str(row["updated_at"]),
    )


def _report_row_to_dict(row) -> dict:
    d = dict(row)
    for k in (
        "key_findings_json",
        "related_tickers_json",
        "alerts_json",
        "raw_data_json",
        "source_news_ids",
        "context_report_ids",
    ):
        try:
            d[k.replace("_json", "")] = json.loads(d.pop(k, "[]"))
        except Exception:
            d[k.replace("_json", "")] = []
    return d


def _brief_row_to_dict(row) -> dict:
    d = dict(row)
    for k in (
        "sections_json",
        "key_events_json",
        "tickers_covered_json",
        "market_data_json",
        "news_sources_json",
    ):
        try:
            d[k.replace("_json", "")] = json.loads(
                d.pop(k, "{}"), parse_constant=_non_finite_json_constant
            )
        except Exception:
            d[k.replace("_json", "")] = (
                [] if k.endswith("s_json") or k.endswith("d_json") else {}
            )
    return d


def _non_finite_json_constant(_: str) -> None:
    return None


def _json_dumps_finite(value) -> str:
    normalized = json.loads(
        json.dumps(value, ensure_ascii=False),
        parse_constant=_non_finite_json_constant,
    )
    return json.dumps(normalized, ensure_ascii=False, allow_nan=False)


# Singleton
_store: ContextStore | None = None


def get_store(data_dir: str | Path = DEFAULT_DATA_DIR) -> ContextStore:
    global _store
    if _store is None:
        _store = ContextStore(data_dir)
    return _store


def recover_interrupted_backtest_jobs() -> int:
    return get_store().recover_interrupted_backtest_jobs()


def recover_interrupted_report_jobs() -> int:
    return get_store().recover_interrupted_report_jobs()


def recover_interrupted_insight_generations() -> int:
    return get_store().recover_interrupted_insight_generations()
