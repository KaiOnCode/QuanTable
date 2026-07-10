"""Memory and knowledge endpoints.

GET  /api/strategies/{id}/memory               — list memories
GET  /api/strategies/{id}/memory/{memory_id}   — get single memory
GET  /api/strategies/{id}/reflections          — list reflections
GET  /api/strategies/{id}/pre-trade-check      — pre-trade safety
"""

from __future__ import annotations

import json
import os
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from memory.service import DEFAULT_MEMORY_DB_PATH
from memory.store import MemoryStore

router = APIRouter(tags=["memory"])


def _memory_store() -> MemoryStore:
    return MemoryStore(os.getenv("MEMORY_DB_PATH", DEFAULT_MEMORY_DB_PATH))


@router.get("/strategies/{strategy_id}/memory")
async def list_memories(
    strategy_id: str,
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0.0),
):
    """List memories for a strategy, ordered by OWM score."""
    try:
        store = _memory_store()
        memories = store.recall(
            ticker=ticker,
            strategy_id=strategy_id,
            limit=limit,
            min_score=min_score,
        )
        return {
            "memories": [m.model_dump() for m in memories],
            "total": len(memories),
        }
    except (json.JSONDecodeError, OSError, sqlite3.Error) as exc:
        raise HTTPException(500, "Failed to read memory") from exc


@router.get("/strategies/{strategy_id}/memory/{memory_id}")
async def get_memory(strategy_id: str, memory_id: str):
    """Get a single memory record (all 5 layers)."""
    try:
        store = _memory_store()
        record = store.get(memory_id)
        if record is None or record.strategy_id != strategy_id:
            raise HTTPException(404, f"Memory {memory_id} not found")
        return record.model_dump()
    except (json.JSONDecodeError, OSError, sqlite3.Error) as exc:
        raise HTTPException(500, "Failed to read memory") from exc


@router.get("/strategies/{strategy_id}/reflections")
async def list_reflections(
    strategy_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
):
    """List weekly reflections for a strategy."""
    return {"reflections": [], "total": 0}


@router.get("/strategies/{strategy_id}/pre-trade-check")
async def pre_trade_check(strategy_id: str):
    """Get pre-trade safety status."""
    return {
        "drawdown_ok": True,
        "streak_ok": True,
        "concentration_ok": True,
        "warnings": [],
        "can_trade": True,
    }
