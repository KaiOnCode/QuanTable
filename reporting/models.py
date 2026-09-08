from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReportType(StrEnum):
    STOCK = "stock"
    SECTOR = "sector"


class ReportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportSection(StrEnum):
    OVERVIEW = "overview"
    DECISION = "decision"
    MARKET = "market"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    RISK = "risk"
    CONSTITUENTS = "constituents"
    DATA_GAPS = "data_gaps"
    SOURCES = "sources"


class RenderedSection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ReportSection
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    report_type: ReportType
    title: str = Field(min_length=1)
    tickers: tuple[str, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)
    sections: tuple[RenderedSection, ...] = Field(min_length=1)
    generated_at: datetime


class ResolvedReportSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_type: str
    source_ids: tuple[str, ...] = Field(min_length=1)
    tickers: tuple[str, ...] = Field(min_length=1)
    content: dict[ReportSection, str]
    data_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_content(self) -> ResolvedReportSource:
        if not any(value.strip() for value in self.content.values()):
            raise ValueError("report source has no usable content")
        return self


class ReportJob(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    report_type: ReportType
    title: str
    tickers: tuple[str, ...]
    source_type: str
    source_ids: tuple[str, ...]
    parameters: dict[str, object]
    status: ReportStatus
    artifact_name: str | None
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str
