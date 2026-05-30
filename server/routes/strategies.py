from __future__ import annotations

import uuid
import json

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["strategies"])


@router.get("/strategies")
async def list_strategies(
    type: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    store = get_store()
    strategies = store.list_strategies(type=type, status=status, limit=limit)
    return {"items": strategies, "total": len(strategies), "page": page}


@router.post("/strategies", status_code=201)
async def create_strategy(config: dict):
    config["id"] = config.get("id") or str(uuid.uuid4())
    store = get_store()
    store.register_strategy(config)
    return config


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    store = get_store()
    s = store.get_strategy(strategy_id)
    if s is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    return s


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, config: dict):
    config["id"] = strategy_id
    store = get_store()
    store.register_strategy(config)
    return config


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(400, "Set ?confirm=true to delete")
    store = get_store()
    if not store.delete_strategy(strategy_id):
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    store.delete_strategy_data(strategy_id)
    return {"deleted": strategy_id}


@router.get("/strategies/{strategy_id}/performance")
async def get_performance(
    strategy_id: str,
    period: str = Query("1m"),
    benchmark: str = Query("SPY"),
):
    store = get_store()
    decisions = store.get_decisions(strategy_id, limit=200)
    return {
        "account_id": strategy_id,
        "period": period,
        "total_return_pct": 0.0,
        "benchmark_return_pct": 0.0,
        "excess_return_pct": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "total_trades": len(decisions),
        "equity_curve": [],
    }


@router.get("/strategies/{strategy_id}/decisions")
async def get_decisions(
    strategy_id: str,
    ticker: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    store = get_store()
    decisions = store.get_decisions(strategy_id, ticker=ticker, limit=50)
    return {"decisions": decisions}
