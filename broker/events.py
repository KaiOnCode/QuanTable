from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BrokerEvent(BaseModel):
    event_type: str
    timestamp: datetime = Field(default_factory=_utc_now)
    session_id: str = ""
    ticker: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
