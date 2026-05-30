"""Trading belief models."""

from __future__ import annotations

from typing import Literal
import uuid

from pydantic import BaseModel, Field

BeliefStyle = Literal["aggressive", "moderate", "conservative"]


class TradingBelief(BaseModel):
    """A natural-language trading philosophy that biases agent decision-making."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    style: BeliefStyle = "moderate"
    tags: list[str] = Field(default_factory=list)
    weight: float = 1.0
    is_active: bool = True

    # Performance tracking (updated over time)
    win_rate: float | None = None
    avg_return_pct: float | None = None
    total_trades: int = 0
