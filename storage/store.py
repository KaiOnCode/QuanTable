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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path("data")


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
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._conns: dict[str, sqlite3.Connection] = {}

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
                session_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                original_action TEXT NOT NULL,
                original_target_position_pct REAL DEFAULT 0.0,
                original_confidence REAL DEFAULT 0.0,
                pm_report TEXT DEFAULT '',
                triggered_rules_json TEXT DEFAULT '[]',
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
        """)

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

    def complete_session(self, strategy_id: str, session_id: str, status: str = "completed") -> None:
        db = self._strategy_db(strategy_id)
        db.execute(
            "UPDATE sessions SET status = ?, completed_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )
        db.commit()

    def record_report(
        self, strategy_id: str, session_id: str, agent_name: str,
        report_type: str, content: str, metadata: dict | None = None,
    ) -> str:
        import uuid
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        rid = str(uuid.uuid4())
        db.execute(
            """INSERT INTO agent_reports (id, session_id, agent_name, report_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid, session_id, agent_name, report_type, content,
             json.dumps(metadata or {}, ensure_ascii=False), _now()),
        )
        db.commit()
        return rid

    def record_decision(self, strategy_id: str, decision: dict) -> str:
        import uuid
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        did = decision.get("id") or str(uuid.uuid4())
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
        self, strategy_id: str, session_id: str, event_type: str,
        actor: str = "", payload: dict | None = None,
    ) -> None:
        import uuid
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        db.execute(
            "INSERT INTO events (id, session_id, event_type, actor, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, event_type, actor,
             json.dumps(payload or {}, ensure_ascii=False), _now()),
        )
        db.commit()

    # ── Queries ─────────────────────────────────────────────

    def get_sessions(self, strategy_id: str, limit: int = 20) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = self._strategy_db(strategy_id).execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_decisions(
        self, strategy_id: str, ticker: str | None = None, limit: int = 20
    ) -> list[dict]:
        self._init_strategy_db(strategy_id)
        if ticker:
            rows = self._strategy_db(strategy_id).execute(
                "SELECT * FROM decisions WHERE ticker = ? ORDER BY created_at DESC LIMIT ?",
                (ticker, limit),
            ).fetchall()
        else:
            rows = self._strategy_db(strategy_id).execute(
                "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_events(self, strategy_id: str, session_id: str) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = self._strategy_db(strategy_id).execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_reports(self, strategy_id: str, session_id: str) -> list[dict]:
        self._init_strategy_db(strategy_id)
        rows = self._strategy_db(strategy_id).execute(
            "SELECT * FROM agent_reports WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Approvals ───────────────────────────────────────────

    def create_approval(self, strategy_id: str, approval: dict) -> str:
        import uuid
        self._init_strategy_db(strategy_id)
        db = self._strategy_db(strategy_id)
        aid = approval.get("id") or str(uuid.uuid4())
        db.execute(
            """INSERT INTO approvals
               (id, session_id, ticker, original_action, original_target_position_pct,
                original_confidence, pm_report, triggered_rules_json, agent_reports_json,
                status, reviewer, reviewer_notes, modified_action, modified_target_position_pct,
                created_at, decided_at, timeout_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                aid,
                approval.get("session_id", ""),
                approval.get("ticker", ""),
                approval.get("original_action", "HOLD"),
                approval.get("original_target_position_pct", 0.0),
                approval.get("original_confidence", 0.0),
                approval.get("pm_report", ""),
                json.dumps(approval.get("triggered_rules", []), ensure_ascii=False),
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
        row = self._strategy_db(strategy_id).execute(
            "SELECT * FROM approvals WHERE id = ?", (approval_id,)
        ).fetchone()
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
            # Support comma-separated statuses e.g. "approved,rejected,modified"
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
        params = [status, reviewer, reviewer_notes, _now()]
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

    # ── Storage management ──────────────────────────────────

    def _get_conn(self, db_name: str) -> sqlite3.Connection:
        import threading
        key = (db_name, threading.current_thread().ident)
        if key not in self._conns:
            path = self.data_dir / db_name
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            self._conns[key] = conn
        return self._conns[key]

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()

    def delete_strategy_data(self, strategy_id: str) -> None:
        """Delete a strategy's database file."""
        path = self.data_dir / f"{strategy_id}.db"
        db_name = f"{strategy_id}.db"
        # Close connections for this db across all threads
        keys_to_remove = [k for k in self._conns if k[0] == db_name]
        for key in keys_to_remove:
            self._conns[key].close()
            del self._conns[key]
        path.unlink(missing_ok=True)


# Singleton
_store: ContextStore | None = None


def get_store(data_dir: str = DEFAULT_DATA_DIR) -> ContextStore:
    global _store
    if _store is None:
        _store = ContextStore(data_dir)
    return _store
