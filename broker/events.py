from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BrokerEvent(BaseModel):
    # Keep a small stable string so other modules can branch on event type
    # without importing engine internals.
    event_type: str
    timestamp: datetime = Field(default_factory=_utc_now)
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""
    ticker: str = ""
    # Use a fresh dict per event. Audit code may enrich this payload later.
    details: dict[str, Any] = Field(default_factory=dict)
