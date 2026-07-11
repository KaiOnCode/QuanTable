from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from reporting.models import ReportJob, ReportStatus, ReportType
from reporting.repository import (
    ArtifactUnavailableError,
    ReportRepository,
    ReportStorageError,
)
from reporting.service import ReportGenerationError, ReportService
from reporting.source import ReportSourceError, ReportSourceResolver
from server.analysis_runs import HISTORY_DIR
from storage import get_store
from utils.pdf_generator import ReportPdfRenderer

router = APIRouter(tags=["reports"])

Ticker = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        pattern=r"^[A-Za-z0-9.^-]{1,16}$",
    ),
]


class StockReportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ticker: Ticker
    strategy_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    sections: tuple[
        Literal["decision", "market", "news", "fundamentals", "risk"], ...
    ] = Field(min_length=1)


class SectorReportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scan_run_id: str = Field(min_length=1, max_length=128)
    sections: tuple[
        Literal["overview", "constituents", "decision", "data_gaps", "sources"],
        ...,
    ] = Field(min_length=1)


class ReportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    report_type: ReportType
    title: str
    tickers: tuple[str, ...]
    source_type: str
    source_ids: tuple[str, ...]
    parameters: dict[str, object]
    status: ReportStatus
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str


class ReportListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[ReportResponse, ...]
    total: int


@lru_cache(maxsize=1)
def get_report_repository() -> ReportRepository:
    root = Path(__file__).resolve().parents[2] / "data" / "generated-reports"
    return ReportRepository(get_store(), root)


@lru_cache(maxsize=1)
def get_report_service() -> ReportService:
    repository = get_report_repository()
    return ReportService(
        repository,
        ReportSourceResolver(get_store(), HISTORY_DIR),
        ReportPdfRenderer(),
    )


def _response(job: ReportJob) -> ReportResponse:
    return ReportResponse(
        id=job.id,
        report_type=job.report_type,
        title=job.title,
        tickers=job.tickers,
        source_type=job.source_type,
        source_ids=job.source_ids,
        parameters=job.parameters,
        status=job.status,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        updated_at=job.updated_at,
    )


def _submit(call: Callable[[], ReportJob]) -> ReportResponse:
    try:
        return _response(call())
    except ReportSourceError as error:
        raise HTTPException(422, str(error)) from error
    except ReportGenerationError as error:
        raise HTTPException(503, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, "Invalid report request") from error


@router.post("/reports/stock", status_code=201, response_model=ReportResponse)
async def create_stock_report(
    request: StockReportRequest,
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    return _submit(
        lambda: service.submit_stock(
            title=f"{request.ticker} source report",
            ticker=request.ticker,
            strategy_id=request.strategy_id,
            session_id=request.session_id,
            sections=request.sections,
        )
    )


@router.post("/reports/sector", status_code=201, response_model=ReportResponse)
async def create_sector_report(
    request: SectorReportRequest,
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    return _submit(
        lambda: service.submit_sector(
            title="Sector scanner source report",
            scan_run_id=request.scan_run_id,
            sections=request.sections,
        )
    )


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(
    limit: int = Query(default=50, ge=1, le=100),
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportListResponse:
    try:
        jobs = repository.list(limit)
    except ReportStorageError as error:
        raise HTTPException(500, "Report storage is unavailable") from error
    return ReportListResponse(
        items=tuple(_response(job) for job in jobs), total=len(jobs)
    )


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: str,
    repository: ReportRepository = Depends(get_report_repository),
) -> ReportResponse:
    try:
        job = repository.get(report_id)
    except ReportStorageError as error:
        raise HTTPException(500, "Report storage is unavailable") from error
    if job is None:
        raise HTTPException(404, "Report not found")
    return _response(job)


@router.get("/reports/{report_id}/download")
async def download_report(
    report_id: str,
    repository: ReportRepository = Depends(get_report_repository),
) -> FileResponse:
    job = repository.get(report_id)
    if job is None:
        raise HTTPException(404, "Report not found")
    if job.status != ReportStatus.COMPLETED:
        raise HTTPException(409, "Report is not completed")
    try:
        artifact = repository.resolve_artifact(report_id)
        filename = repository.download_filename(report_id)
    except ArtifactUnavailableError as error:
        raise HTTPException(404, "Report artifact is unavailable") from error
    return FileResponse(artifact, media_type="application/pdf", filename=filename)
