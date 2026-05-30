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
    from memory.store import MemoryStore
    store = MemoryStore("data/memory.db")
    records = store.recall(ticker=ticker, strategy_id=strategy_id, limit=limit, min_score=min_score)
    return {"memories": [r.model_dump() for r in records], "total": len(records)}


@router.get("/strategies/{strategy_id}/memory/{memory_id}")
async def get_memory(strategy_id: str, memory_id: str):
    from memory.store import MemoryStore
    store = MemoryStore("data/memory.db")
    record = store.get(memory_id)
    if record is None:
        raise HTTPException(404, f"Memory {memory_id} not found")
    return record.model_dump()


@router.get("/strategies/{strategy_id}/reflections")
async def list_reflections(
    strategy_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
):
    return {"reflections": [], "total": 0}
