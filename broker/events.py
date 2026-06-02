from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BrokerEvent(BaseModel):
    event_id: str = ""
    sequence: int = 0
    # Keep a small stable string so other modules can branch on event type
    # without importing engine internals.
    event_type: str
    entity_type: str = ""
    entity_id: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    strategy_id: str = ""
    account_id: str = "default"
    session_id: str = ""
    decision_id: str = ""
    ticker: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    # Backwards-compatible alias for existing broker tests and callers.
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def sync_payload_and_details(self) -> BrokerEvent:
        if self.payload and not self.details:
            self.details = dict(self.payload)
        elif self.details and not self.payload:
            self.payload = dict(self.details)
        return self


class BrokerEventSink(Protocol):
    def publish(self, event: BrokerEvent) -> BrokerEvent: ...

    def load_events(
        self,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        session_id: str | None = None,
        decision_id: str | None = None,
        event_type: str | None = None,
    ) -> list[BrokerEvent]: ...


class InMemoryBrokerEventSink:
    def __init__(self) -> None:
        self._events: list[BrokerEvent] = []
        self._next_sequence_by_key: dict[tuple[str, str], int] = {}

    def publish(self, event: BrokerEvent) -> BrokerEvent:
        stored_event = event.model_copy(deep=True)
        if not stored_event.event_id:
            stored_event.event_id = str(uuid4())
        sequence_key = (stored_event.strategy_id, stored_event.account_id)
        next_sequence = self._next_sequence_by_key.get(sequence_key, 1)
        stored_event.sequence = next_sequence
        self._next_sequence_by_key[sequence_key] = next_sequence + 1
        self._events.append(stored_event.model_copy(deep=True))
        return stored_event.model_copy(deep=True)

    def load_events(
        self,
        *,
        strategy_id: str | None = None,
        account_id: str | None = None,
        session_id: str | None = None,
        decision_id: str | None = None,
        event_type: str | None = None,
    ) -> list[BrokerEvent]:
        events = [event.model_copy(deep=True) for event in self._events]
        if strategy_id is not None:
            events = [event for event in events if event.strategy_id == strategy_id]
        if account_id is not None:
            events = [event for event in events if event.account_id == account_id]
        if session_id is not None:
            events = [event for event in events if event.session_id == session_id]
        if decision_id is not None:
            events = [event for event in events if event.decision_id == decision_id]
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        return events
