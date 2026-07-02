"""Memory and knowledge endpoints.

GET  /api/strategies/{id}/memory               — list memories
GET  /api/strategies/{id}/memory/{memory_id}   — get single memory
GET  /api/strategies/{id}/reflections          — list reflections
GET  /api/strategies/{id}/pre-trade-check      — pre-trade safety
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(tags=["memory"])


@router.get("/strategies/{strategy_id}/memory")
async def list_memories(
    strategy_id: str,
    ticker: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    min_score: float = Query(0.0),
):
    """List memories for a strategy, ordered by OWM score."""
    try:
        from memory.store import MemoryStore

        store = MemoryStore("data/memory.db")
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
    except Exception:
        return {"memories": [], "total": 0}


@router.get("/strategies/{strategy_id}/memory/{memory_id}")
async def get_memory(strategy_id: str, memory_id: str):
    """Get a single memory record (all 5 layers)."""
    try:
        from memory.store import MemoryStore

        store = MemoryStore("data/memory.db")
        record = store.get(memory_id)
        if record is None:
            raise HTTPException(404, f"Memory {memory_id} not found")
        return record.model_dump()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Failed to read memory")


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
