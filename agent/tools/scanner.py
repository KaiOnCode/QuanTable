from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dataflow.store import MarketDataStore
from scanner.models import ScanCondition
from scanner.service import ScannerService, ScannerServiceError
from scanner.universe import TrackedUniverseResolver
from storage import get_store

from .base import BaseTool, ToolMeta


class ScanTrackedUniverseInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conditions: tuple[ScanCondition, ...] = Field(min_length=1)


class ScanTrackedUniverseTool(BaseTool):
    meta = ToolMeta(
        name="scan_tracked_universe",
        description=(
            "Evaluate typed conditions against the cached tracked universe. "
            "Call exactly once with conditions; it never fetches market data."
        ),
        is_readonly=True,
        category="financial",
        input_schema={
            "properties": {
                "conditions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "operator": {"type": "string"},
                            "value": {"type": ["number", "string"]},
                            "value2": {"type": ["number", "string", "null"]},
                        },
                        "required": ["field", "operator", "value"],
                    },
                }
            },
            "required": ["conditions"],
        },
    )

    def __init__(self, service: ScannerService | None = None) -> None:
        self._service = service or _default_scanner_service()

    def execute(self, **kwargs: object) -> str:
        try:
            payload = ScanTrackedUniverseInput.model_validate(kwargs)
        except ValidationError:
            return self._error("invalid scanner conditions")
        try:
            result = self._service.scan(payload.conditions)
        except ScannerServiceError as error:
            return self._error(str(error))
        return self._ok(
            {
                "conditions": [
                    condition.model_dump(mode="json")
                    for condition in payload.conditions
                ],
                "result": result.model_dump(mode="json"),
            }
        )


def _default_scanner_service() -> ScannerService:
    market_store = MarketDataStore()
    return ScannerService(
        TrackedUniverseResolver(get_store(), market_store), market_store
    )
