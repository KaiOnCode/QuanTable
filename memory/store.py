"""SQLite-backed memory store for OWM-scored trading memories."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from memory.models import MemoryRecord, MemoryLayer
from memory.owm import compute_owm_score, compute_recency, compute_context_similarity


class MemoryStore:
    """SQLite-backed store for MemoryRecord objects with OWM scoring."""

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn_instance: sqlite3.Connection | None = None
        self._init_db()

    def close(self):
        """Close the database connection (call on shutdown)."""
        if self._conn_instance:
            self._conn_instance.close()
            self._conn_instance = None

    # ── public API ──────────────────────────────────────────────

    def remember(self, record: MemoryRecord) -> str:
        """Store a memory record, computing its OWM score automatically.

        Returns the record id.
        """
        # Compute recency and OWM score
        recency = compute_recency(record.created_at)
        record.owm_score = compute_owm_score(
            outcome_quality=record.outcome_quality,
            context_similarity=0.5,  # neutral for new records
            recency=recency,
            confidence=record.confidence,
        )

        with self._conn() as db:
            db.execute(
                """INSERT INTO memories
                   (id, strategy_id, session_id, ticker,
                    outcome_quality, confidence, owm_score,
                    episodic, semantic, procedural, affective,
                    trade_record_json, tags_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.strategy_id,
                    record.session_id,
                    record.ticker,
                    record.outcome_quality,
                    record.confidence,
                    record.owm_score,
                    record.episodic,
                    record.semantic,
                    record.procedural,
                    record.affective,
                    json.dumps(record.trade_record, ensure_ascii=False),
                    json.dumps(record.tags, ensure_ascii=False),
                    record.created_at,
                ),
            )
        return record.id

    def recall(
        self,
        ticker: str | None = None,
        strategy_id: str | None = None,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[MemoryRecord]:
        """Retrieve memories, ordered by OWM score descending."""
        conditions = ["1=1"]
        params: list = []

        if ticker:
            conditions.append("ticker = ?")
            params.append(ticker)
        if strategy_id:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)
        if min_score > 0:
            conditions.append("owm_score >= ?")
            params.append(min_score)

        where = " AND ".join(conditions)

        with self._conn() as db:
            rows = db.execute(
                f"SELECT * FROM memories WHERE {where} "
                f"ORDER BY owm_score DESC LIMIT ?",
                (*params, limit),
            ).fetchall()

        return [self._row_to_record(r) for r in rows]

    def recall_by_context(
        self,
        context: dict,
        strategy_id: str | None = None,
        limit: int = 10,
    ) -> list[MemoryRecord]:
        """Recall memories re-scored against a given market context."""
        raw = self.recall(
            ticker=context.get("ticker"),
            strategy_id=strategy_id,
            limit=limit * 2,
        )
        # Re-score with context similarity
        for r in raw:
            past_ctx = {
                "ticker": r.ticker,
                "tags": r.tags,
            }
            sim = compute_context_similarity(context, past_ctx)
            recency = compute_recency(r.created_at)
            r.owm_score = compute_owm_score(
                outcome_quality=r.outcome_quality,
                context_similarity=sim,
                recency=recency,
                confidence=r.confidence,
            )

        raw.sort(key=lambda r: r.owm_score, reverse=True)
        return raw[:limit]

    def get(self, memory_id: str) -> MemoryRecord | None:
        """Get a single memory by id."""
        with self._conn() as db:
            row = db.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def delete(self, memory_id: str) -> bool:
        """Delete a memory. Returns True if it existed."""
        with self._conn() as db:
            cur = db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def count(self, strategy_id: str | None = None) -> int:
        """Count memories, optionally filtered by strategy."""
        if strategy_id:
            with self._conn() as db:
                row = db.execute(
                    "SELECT COUNT(*) FROM memories WHERE strategy_id = ?",
                    (strategy_id,),
                ).fetchone()
        else:
            with self._conn() as db:
                row = db.execute("SELECT COUNT(*) FROM memories").fetchone()
        return row[0] if row else 0

    # ── internals ──────────────────────────────────────────────

    def _conn(self):
        # For in-memory databases, reuse the same connection since
        # each sqlite3.connect(':memory:') creates an independent database.
        # For file databases, create a new connection each time (thread-safe).
        if str(self.db_path) == ":memory:":
            if self._conn_instance is None:
                self._conn_instance = sqlite3.connect(":memory:")
                self._conn_instance.row_factory = sqlite3.Row
            return self._conn_instance
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._conn() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    strategy_id TEXT NOT NULL,
                    session_id TEXT DEFAULT '',
                    ticker TEXT NOT NULL,
                    outcome_quality REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.5,
                    owm_score REAL DEFAULT 0.0,
                    episodic TEXT DEFAULT '',
                    semantic TEXT DEFAULT '',
                    procedural TEXT DEFAULT '',
                    affective TEXT DEFAULT '',
                    trade_record_json TEXT DEFAULT '{}',
                    tags_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
            """)
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_strategy "
                "ON memories(strategy_id)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_ticker "
                "ON memories(ticker)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_owm "
                "ON memories(owm_score DESC)"
            )

    @staticmethod
    def _row_to_record(row: tuple) -> MemoryRecord:
        cols = [
            "id", "strategy_id", "session_id", "ticker",
            "outcome_quality", "confidence", "owm_score",
            "episodic", "semantic", "procedural", "affective",
            "trade_record_json", "tags_json", "created_at",
        ]
        d = dict(zip(cols, row))
        return MemoryRecord(
            id=d["id"],
            strategy_id=d["strategy_id"],
            session_id=d["session_id"] or "",
            ticker=d["ticker"],
            outcome_quality=d["outcome_quality"] or 0.0,
            confidence=d["confidence"] or 0.5,
            owm_score=d["owm_score"] or 0.0,
            episodic=d["episodic"] or "",
            semantic=d["semantic"] or "",
            procedural=d["procedural"] or "",
            affective=d["affective"] or "",
            trade_record=json.loads(d["trade_record_json"] or "{}"),
            tags=json.loads(d["tags_json"] or "[]"),
            created_at=d["created_at"],
        )
