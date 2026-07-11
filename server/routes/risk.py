from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from dataflow.store import MarketDataStore
from risk.models import RiskOverview, StressResult
from risk.service import RiskAnalyticsService
from storage import get_store

router = APIRouter(tags=["risk"])


class StressRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    uniform_market_shock: float = Field(ge=-1, le=1)
    lookback_days: int = Field(default=252, ge=60, le=252)


def get_risk_service() -> RiskAnalyticsService:
    return RiskAnalyticsService(get_store(), MarketDataStore())


def _require_strategy(strategy_id: str) -> None:
    if get_store().get_strategy(strategy_id) is None:
        raise HTTPException(404, "Strategy not found")


@router.get("/risk/{strategy_id}/overview", response_model=RiskOverview)
async def get_risk_overview(
    strategy_id: str,
    lookback_days: int = Query(default=252, ge=60, le=252),
) -> RiskOverview:
    _require_strategy(strategy_id)
    return get_risk_service().overview(strategy_id, lookback_days)


@router.post("/risk/{strategy_id}/stress", response_model=StressResult)
async def run_risk_stress(strategy_id: str, request: StressRequest) -> StressResult:
    _require_strategy(strategy_id)
    return get_risk_service().stress(
        strategy_id,
        uniform_market_shock=request.uniform_market_shock,
        lookback_days=request.lookback_days,
    )
