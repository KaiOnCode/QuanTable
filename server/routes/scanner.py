from __future__ import annotations

import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from dataflow.store import MarketDataStore
from scanner.models import ScanCondition, ScanResponse
from scanner.service import ScannerService, ScannerServiceError
from scanner.universe import TrackedUniverseResolver, UnsupportedUniverseError
from storage import get_store
from storage.store import ScanRunRecord, ScanRunStatus

router = APIRouter(tags=["scanner"])


class RuleScanRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conditions: tuple[ScanCondition, ...] = Field(min_length=1)
    universe: Literal["tracked"] = "tracked"


class ScanRunError(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: Literal["scanner_failed", "invalid_tool_output", "llm_unavailable"]
    message: str


class ScanRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    input: dict[str, object]
    compiled_conditions: tuple[ScanCondition, ...] | None
    result: ScanResponse | None
    error: ScanRunError | None
    status: ScanRunStatus
    mode: str
    strategy_id: str | None
    created_at: str
    completed_at: str | None
    updated_at: str


class ScanRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ScanRunResponse, ...]
    total: int


def get_scanner_service() -> ScannerService:
    market_store = MarketDataStore()
    return ScannerService(
        TrackedUniverseResolver(get_store(), market_store), market_store
    )


@router.post("/scanner/rule", status_code=201, response_model=ScanRunResponse)
async def create_rule_scan(request: RuleScanRequest) -> ScanRunResponse:
    store = get_store()
    run_id = uuid4().hex
    input_json = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    store.create_scan_run(run_id, input_json, mode="rule")
    try:
        result = get_scanner_service().scan(request.conditions, request.universe)
    except (ScannerServiceError, UnsupportedUniverseError) as error:
        failure = ScanRunError(code="scanner_failed", message="Scanner rule failed")
        store.fail_scan_run(run_id, failure.model_dump_json())
        raise HTTPException(422, str(error)) from error
    completed = store.complete_scan_run(
        run_id,
        json.dumps(
            [condition.model_dump(mode="json") for condition in request.conditions],
            ensure_ascii=False,
        ),
        result.model_dump_json(),
    )
    if not completed:
        raise RuntimeError("scanner run did not complete")
    run = store.get_scan_run(run_id)
    if run is None:
        raise RuntimeError("scanner run disappeared after completion")
    return _response_from_record(run)


@router.get("/scanner/runs", response_model=ScanRunListResponse)
async def list_scan_runs(
    status: ScanRunStatus | None = Query(None), limit: int = Query(50, ge=1, le=100)
) -> ScanRunListResponse:
    runs = get_store().list_scan_runs(status=status, limit=limit)
    return ScanRunListResponse(
        items=tuple(_response_from_record(run) for run in runs), total=len(runs)
    )


@router.get("/scanner/runs/{scan_run_id}", response_model=ScanRunResponse)
async def get_scan_run(scan_run_id: str) -> ScanRunResponse:
    run = get_store().get_scan_run(scan_run_id)
    if run is None:
        raise HTTPException(404, "Scanner run not found")
    return _response_from_record(run)


def _response_from_record(run: ScanRunRecord) -> ScanRunResponse:
    try:
        input_payload = json.loads(run.input_json)
        compiled_conditions = (
            tuple(
                ScanCondition.model_validate(item)
                for item in json.loads(run.compiled_conditions_json)
            )
            if run.compiled_conditions_json is not None
            else None
        )
        result = (
            ScanResponse.model_validate_json(run.result_json)
            if run.result_json is not None
            else None
        )
        error = (
            ScanRunError.model_validate_json(run.error_json)
            if run.error_json is not None
            else None
        )
    except (json.JSONDecodeError, ValidationError, TypeError) as error:
        raise HTTPException(500, "Scanner run storage is corrupt") from error
    if not isinstance(input_payload, dict):
        raise HTTPException(500, "Scanner run storage is corrupt")
    return ScanRunResponse(
        id=run.id,
        input=input_payload,
        compiled_conditions=compiled_conditions,
        result=result,
        error=error,
        status=run.status,
        mode=run.mode,
        strategy_id=run.strategy_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
        updated_at=run.updated_at,
    )
