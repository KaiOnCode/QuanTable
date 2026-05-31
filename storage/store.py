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
            CREATE INDEX IF NOT EXISTS idx_sessions_ticker ON sessions(ticker);
            CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
            CREATE INDEX IF NOT EXISTS idx_reports_session ON agent_reports(session_id);
            CREATE INDEX IF NOT EXISTS idx_decisions_session ON decisions(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        """)

    def record_session(
        self, strategy_id: str, session_id: str, ticker: str, status: str = "running"
    ) -> None:
        self._init_strategy_db(strategy_id)
        self._strategy_db(strategy_id).execute(
            "INSERT OR REPLACE INTO sessions (id, ticker, status, started_at) VALUES (?, ?, ?, ?)",
            (session_id, ticker, status, _now()),
        )

    def complete_session(self, strategy_id: str, session_id: str, status: str = "completed") -> None:
        self._strategy_db(strategy_id).execute(
            "UPDATE sessions SET status = ?, completed_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )

    def record_report(
        self, strategy_id: str, session_id: str, agent_name: str,
        report_type: str, content: str, metadata: dict | None = None,
    ) -> str:
        import uuid
        self._init_strategy_db(strategy_id)
        rid = str(uuid.uuid4())
        self._strategy_db(strategy_id).execute(
            """INSERT INTO agent_reports (id, session_id, agent_name, report_type, content, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid, session_id, agent_name, report_type, content,
             json.dumps(metadata or {}, ensure_ascii=False), _now()),
        )
        return rid

    def record_decision(self, strategy_id: str, decision: dict) -> str:
        import uuid
        self._init_strategy_db(strategy_id)
        did = decision.get("id") or str(uuid.uuid4())
        self._strategy_db(strategy_id).execute(
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
        return did

    def record_event(
        self, strategy_id: str, session_id: str, event_type: str,
        actor: str = "", payload: dict | None = None,
    ) -> None:
        import uuid
        self._init_strategy_db(strategy_id)
        self._strategy_db(strategy_id).execute(
            "INSERT INTO events (id, session_id, event_type, actor, payload_json, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, event_type, actor,
             json.dumps(payload or {}, ensure_ascii=False), _now()),
        )

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

    # ── Storage management ──────────────────────────────────

    def _get_conn(self, db_name: str) -> sqlite3.Connection:
        if db_name not in self._conns:
            path = self.data_dir / db_name
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            self._conns[db_name] = conn
        return self._conns[db_name]

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()

    def delete_strategy_data(self, strategy_id: str) -> None:
        """Delete a strategy's database file."""
        path = self.data_dir / f"{strategy_id}.db"
        if strategy_id in self._conns:
            self._conns[strategy_id].close()
            del self._conns[strategy_id]
        path.unlink(missing_ok=True)


# Singleton
_store: ContextStore | None = None


def get_store(data_dir: str = DEFAULT_DATA_DIR) -> ContextStore:
    global _store
    if _store is None:
        _store = ContextStore(data_dir)
    return _store
