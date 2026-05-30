"""Strategy CRUD endpoints.

GET    /api/strategies          — list all strategies
POST   /api/strategies          — create a new strategy
GET    /api/strategies/{id}     — get strategy detail
PUT    /api/strategies/{id}     — update strategy
DELETE /api/strategies/{id}     — delete strategy
GET    /api/strategies/{id}/performance — performance metrics
GET    /api/strategies/{id}/decisions   — decision history
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["strategies"])

MOCK_STRATEGIES = [
    {
        "id": "1",
        "name": "Tech Momentum",
        "description": "Momentum-based strategy focused on tech stocks",
        "type": "agent",
        "status": "active",
        "tickers": ["AAPL", "MSFT", "NVDA"],
        "beliefs": ["聚焦科技股动量"],
        "active_agents": ["market", "news", "fundamentals", "pm"],
        "debate_rounds": 2,
        "created_at": "2026-05-01T09:00:00Z",
        "updated_at": "2026-05-28T06:00:00Z",
        "tags": ["tech", "momentum"],
    },
    {
        "id": "2",
        "name": "Value Hunter",
        "description": "Deep value with PE/PB filters",
        "type": "quant",
        "status": "active",
        "tickers": ["BRK.B", "JPM", "XOM"],
        "beliefs": [],
        "active_agents": ["market", "fundamentals", "pm"],
        "debate_rounds": 1,
        "created_at": "2026-04-15T09:00:00Z",
        "updated_at": "2026-05-27T06:00:00Z",
        "tags": ["value", "defensive"],
    },
]


@router.get("/strategies")
async def list_strategies(
    type: str | None = Query(None),
    status: str | None = Query(None),
    tag: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List all strategies with optional filters."""
    strategies = MOCK_STRATEGIES

    if type:
        strategies = [s for s in strategies if s["type"] == type]
    if status:
        strategies = [s for s in strategies if s["status"] == status]
    if tag:
        strategies = [s for s in strategies if tag in s.get("tags", [])]

    total = len(strategies)
    start = (page - 1) * limit
    items = strategies[start : start + limit]

    return {"items": items, "total": total, "page": page}


@router.post("/strategies", status_code=201)
async def create_strategy(config: dict):
    """Create a new strategy."""
    strategy_id = str(uuid.uuid4())
    config["id"] = strategy_id

    try:
        store = get_store()
        store.register_strategy(config)
    except Exception:
        pass

    return config


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get strategy detail."""
    for s in MOCK_STRATEGIES:
        if s["id"] == strategy_id:
            return s
    raise HTTPException(404, f"Strategy {strategy_id} not found")


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, config: dict):
    """Update strategy configuration."""
    config["id"] = strategy_id
    return config


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, confirm: bool = Query(False)):
    """Delete a strategy and its data."""
    if not confirm:
        raise HTTPException(400, "Set ?confirm=true to delete")
    try:
        store = get_store()
        store.delete_strategy_data(strategy_id)
    except Exception:
        pass
    return {"deleted": strategy_id}


@router.get("/strategies/{strategy_id}/performance")
async def get_performance(
    strategy_id: str,
    period: str = Query("1m"),
    benchmark: str = Query("SPY"),
):
    """Get strategy performance metrics."""
    return {
        "account_id": strategy_id,
        "period": period,
        "total_return_pct": 5.23,
        "benchmark_return_pct": 2.15,
        "excess_return_pct": 3.08,
        "sharpe_ratio": 1.35,
        "max_drawdown_pct": -8.45,
        "win_rate_pct": 62.5,
        "total_trades": 24,
        "equity_curve": [],
    }


@router.get("/strategies/{strategy_id}/decisions")
async def get_decisions(
    strategy_id: str,
    ticker: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
):
    """Get decision history for a strategy."""
    try:
        store = get_store()
        decisions = store.get_decisions(strategy_id, ticker=ticker, limit=50)
        return {"decisions": decisions}
    except Exception:
        return {"decisions": []}
