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
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

type BacktestJobStatus = Literal["pending", "running", "completed", "failed"]


@dataclass(frozen=True, slots=True)
class BacktestJobRecord:
    id: str
    request_json: str
    status: BacktestJobStatus
    result_json: str | None
    error_json: str | None
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
                json.dumps(brief.get("sections", [])),
                json.dumps(brief.get("key_events", [])),
                json.dumps(brief.get("tickers_covered", [])),
                json.dumps(brief.get("market_data", {})),
                json.dumps(brief.get("news_sources", [])),
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

    def create_backtest_job(self, job_id: str, request_json: str) -> BacktestJobRecord:
        self._init_backtest_jobs_db()
        now = _now()
        db = self._system_db()
        db.execute(
            """INSERT INTO backtest_jobs
               (id, request_json, status, result_json, error_json,
                created_at, started_at, completed_at, updated_at)
               VALUES (?, ?, 'pending', NULL, NULL, ?, NULL, NULL, ?)""",
            (job_id, request_json, now, now),
        )
        db.commit()
        job = self.get_backtest_job(job_id)
        if job is None:
            raise RuntimeError("backtest job was not persisted")
        return job

    def get_backtest_job(self, job_id: str) -> BacktestJobRecord | None:
        self._init_backtest_jobs_db()
        row = (
            self._system_db()
            .execute(
                """SELECT id, request_json, status, result_json, error_json,
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
               WHERE id = ? AND status = 'running'""",
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
            "CREATE INDEX IF NOT EXISTS idx_backtest_jobs_status ON backtest_jobs(status)"
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


def _backtest_job_from_row(row: sqlite3.Row) -> BacktestJobRecord:
    status = str(row["status"])
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
    return BacktestJobRecord(
        id=str(row["id"]),
        request_json=str(row["request_json"]),
        status=normalized_status,
        result_json=(str(row["result_json"]) if row["result_json"] else None),
        error_json=(str(row["error_json"]) if row["error_json"] else None),
        created_at=str(row["created_at"]),
        started_at=(str(row["started_at"]) if row["started_at"] else None),
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
            d[k.replace("_json", "")] = json.loads(d.pop(k, "{}"))
        except Exception:
            d[k.replace("_json", "")] = (
                [] if k.endswith("s_json") or k.endswith("d_json") else {}
            )
    return d


# Singleton
_store: ContextStore | None = None


def get_store(data_dir: str | Path = DEFAULT_DATA_DIR) -> ContextStore:
    global _store
    if _store is None:
        _store = ContextStore(data_dir)
    return _store


def recover_interrupted_backtest_jobs() -> int:
    return get_store().recover_interrupted_backtest_jobs()
