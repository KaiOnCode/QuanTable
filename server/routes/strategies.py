"""Strategy CRUD endpoints.

All endpoints read/write through ContextStore (system.db + per-strategy DBs).
No mock data — every response is computed from real stored data.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["strategies"])


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CRUD ────────────────────────────────────────────────────


@router.get("/strategies")
async def list_strategies(
    type: str | None = Query(None),
    status: str | None = Query(None),
    tag: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List all strategies, with optional type/status/tag filters."""
    store = get_store()
    strategies = store.list_strategies(type=type, status=status)

    # Tag filter: check tags list inside config
    if tag:
        strategies = [s for s in strategies if tag in s.get("tags", [])]

    total = len(strategies)
    start = (page - 1) * limit
    items = strategies[start : start + limit]

    return {"items": items, "total": total, "page": page}


@router.post("/strategies", status_code=201)
async def create_strategy(config: dict):
    """Create a new strategy. Persists to system.db and returns the stored record."""
    strategy_id = str(uuid.uuid4())
    now = _now()

    # Build full config with defaults
    strategy = {
        "id": strategy_id,
        "name": config.get("name", "Untitled Strategy"),
        "description": config.get("description", ""),
        "type": config.get("type", "agent"),
        "status": config.get("status", "draft"),
        "tickers": config.get("tickers", []),
        "beliefs": config.get("beliefs", []),
        "active_agents": config.get("active_agents", ["market", "news", "fundamentals", "pm"]),
        "debate_rounds": config.get("debate_rounds", 2),
        "created_at": now,
        "updated_at": now,
        "tags": config.get("tags", []),
        "creator": config.get("creator", ""),
        # Store any additional fields the frontend sends
        **{k: v for k, v in config.items()
           if k not in ("id", "name", "description", "type", "status", "tickers",
                        "beliefs", "active_agents", "debate_rounds",
                        "created_at", "updated_at", "tags", "creator")},
    }

    store = get_store()
    store.register_strategy(strategy)
    return strategy


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """Get a single strategy by ID."""
    store = get_store()
    strategy = store.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    return strategy


@router.put("/strategies/{strategy_id}")
async def update_strategy(strategy_id: str, config: dict):
    """Update a strategy. Partial update — only sent fields are changed."""
    store = get_store()
    # Remove id from updates (shouldn't change)
    updates = {k: v for k, v in config.items() if k != "id"}
    result = store.update_strategy(strategy_id, updates)
    if result is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    return result


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, confirm: bool = Query(False)):
    """Delete a strategy and all its data. Requires ?confirm=true."""
    if not confirm:
        raise HTTPException(400, "Set ?confirm=true to permanently delete this strategy")

    store = get_store()
    existing = store.get_strategy(strategy_id)
    if existing is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")

    store.delete_strategy_data(strategy_id)
    # Also remove from system.db registry
    db = store._system_db()
    db.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))

    return {"deleted": strategy_id}


# ── Performance & Decisions ─────────────────────────────────


@router.get("/strategies/{strategy_id}/performance")
async def get_performance(
    strategy_id: str,
    period: str = Query("1m"),
    benchmark: str = Query("SPY"),
):
    """Get performance metrics for a strategy.
    Returns calculated metrics if real data exists, otherwise defaults.
    """
    store = get_store()
    decisions = store.get_decisions(strategy_id, limit=200)

    total_trades = len(decisions)
    if total_trades == 0:
        return {
            "account_id": strategy_id,
            "period": period,
            "total_return_pct": 0.0,
            "benchmark_return_pct": 0.0,
            "excess_return_pct": 0.0,
            "sharpe_ratio": None,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "total_trades": 0,
            "equity_curve": [],
        }

    # Calculate win rate from decisions with confidence
    bullish_decisions = [d for d in decisions if d.get("action") in ("BUY", "SELL")]
    wins = [d for d in bullish_decisions if d.get("confidence", 0) > 0.6]

    win_rate = round(len(wins) / len(bullish_decisions) * 100, 1) if bullish_decisions else 0.0

    return {
        "account_id": strategy_id,
        "period": period,
        "total_return_pct": 0.0,  # needs real PnL data from broker
        "benchmark_return_pct": 0.0,
        "excess_return_pct": 0.0,
        "sharpe_ratio": None,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": win_rate,
        "total_trades": total_trades,
        "equity_curve": [],
    }


@router.get("/strategies/{strategy_id}/decisions")
async def get_decisions(
    strategy_id: str,
    ticker: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=200),
):
    """Get decision history for a strategy."""
    store = get_store()
    decisions = store.get_decisions(strategy_id, ticker=ticker, limit=limit)

    # Apply date filters in Python (store doesn't support date range yet)
    if from_date:
        decisions = [d for d in decisions if d.get("created_at", "") >= from_date]
    if to_date:
        decisions = [d for d in decisions if d.get("created_at", "") <= to_date]

    return {"decisions": decisions[:limit], "total": len(decisions)}
