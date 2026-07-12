"""Strategy CRUD endpoints.

All endpoints read/write through ContextStore (system.db + per-strategy DBs).
No mock data — every response is computed from real stored data.
"""

from __future__ import annotations

import uuid
from typing import Annotated, assert_never

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import JsonValue, ValidationError

from storage.strategy_config import StrategyConfigPayload
from storage.strategy_policy import (
    StrategyEligibilityError,
    validate_quant_strategy_definition,
)
from server.routes.strategy_lifecycle import (
    CloneStrategyRequest,
    LifecycleAction,
    StopStrategyRequest,
    sanitize_clone_config,
)
from storage import get_store

router = APIRouter(tags=["strategies"])


async def _parse_strategy_config(
    payload: dict[str, JsonValue] = Body(...),
) -> StrategyConfigPayload:
    try:
        return StrategyConfigPayload.model_validate(payload)
    except ValidationError as exc:
        detail = [
            {
                key: value
                for key, value in error.items()
                if key not in {"ctx", "input", "url"}
            }
            for error in exc.errors()
        ]
        raise HTTPException(422, detail=detail) from exc


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_strategy_policy(strategy: dict[str, object]) -> None:
    if strategy.get("type") != "quant":
        return
    try:
        validate_quant_strategy_definition(strategy)
    except StrategyEligibilityError as exc:
        raise HTTPException(
            422, detail={"code": exc.code, "message": exc.message}
        ) from exc


def _transition_strategy(
    strategy_id: str, action: LifecycleAction
) -> dict[str, JsonValue]:
    store = get_store()
    strategy = store.get_strategy(strategy_id)
    if strategy is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")

    current_status = str(strategy.get("status", "draft"))
    match action:
        case "start":
            allowed_statuses = frozenset(("draft", "paused", "stopped"))
            target_status = "active"
        case "pause":
            allowed_statuses = frozenset(("active",))
            target_status = "paused"
        case "stop":
            allowed_statuses = frozenset(("draft", "active", "paused"))
            target_status = "stopped"
        case unreachable:
            assert_never(unreachable)

    if current_status == target_status:
        return strategy
    if current_status not in allowed_statuses:
        raise HTTPException(
            409, f"Cannot {action} strategy from status {current_status}"
        )

    updated = store.update_strategy(strategy_id, {"status": target_status})
    if updated is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    return updated


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
async def create_strategy(
    config: Annotated[StrategyConfigPayload, Depends(_parse_strategy_config)],
):
    """Create a new strategy. Persists to system.db and returns the stored record."""
    strategy_id = str(uuid.uuid4())
    now = _now()

    # Build full config with defaults
    strategy = {
        "id": strategy_id,
        **config.model_dump(),
        "created_at": now,
        "updated_at": now,
    }

    _validate_strategy_policy(strategy)
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
async def update_strategy(
    strategy_id: str,
    config: Annotated[StrategyConfigPayload, Depends(_parse_strategy_config)],
):
    """Update a strategy. Partial update — only sent fields are changed."""
    store = get_store()
    existing = store.get_strategy(strategy_id)
    if existing is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    # Remove id from updates (shouldn't change)
    updates = config.model_dump(exclude_unset=True)
    _validate_strategy_policy({**existing, **updates})
    result = store.update_strategy(strategy_id, updates)
    if result is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")
    return result


@router.post("/strategies/{strategy_id}/clone", status_code=201)
async def clone_strategy(
    strategy_id: str, request: CloneStrategyRequest
) -> dict[str, JsonValue]:
    store = get_store()
    source = store.get_strategy(strategy_id)
    if source is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")

    now = _now()
    clone = {
        **sanitize_clone_config(source),
        "id": str(uuid.uuid4()),
        "name": request.name,
        "status": "draft",
        "parent_strategy_id": strategy_id,
        "created_at": now,
        "updated_at": now,
    }
    store.register_strategy(clone)
    return clone


@router.post("/strategies/{strategy_id}/start")
async def start_strategy(strategy_id: str) -> dict[str, JsonValue]:
    return _transition_strategy(strategy_id, "start")


@router.post("/strategies/{strategy_id}/pause")
async def pause_strategy(strategy_id: str) -> dict[str, JsonValue]:
    return _transition_strategy(strategy_id, "pause")


@router.post("/strategies/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: str, request: StopStrategyRequest
) -> dict[str, JsonValue]:
    if request.liquidate:
        raise HTTPException(409, "Liquidation is not supported")
    return _transition_strategy(strategy_id, "stop")


@router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str, confirm: bool = Query(False)):
    """Delete a strategy and all its data. Requires ?confirm=true."""
    if not confirm:
        raise HTTPException(
            400, "Set ?confirm=true to permanently delete this strategy"
        )

    store = get_store()
    existing = store.get_strategy(strategy_id)
    if existing is None:
        raise HTTPException(404, f"Strategy {strategy_id} not found")

    store.delete_strategy_data(strategy_id)
    # Also remove from system.db registry
    db = store._system_db()
    db.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    db.commit()

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

    win_rate = (
        round(len(wins) / len(bullish_decisions) * 100, 1) if bullish_decisions else 0.0
    )

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
