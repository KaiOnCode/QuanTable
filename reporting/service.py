from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from reporting.models import (
    RenderedSection,
    ReportJob,
    ReportPayload,
    ReportSection,
    ReportType,
    ResolvedReportSource,
)
from reporting.repository import ReportRepository
from reporting.source import ReportSourceError, ReportSourceResolver


class ReportGenerationError(RuntimeError):
    pass


class PdfRenderer(Protocol):
    def preflight(self) -> None: ...

    def render(self, payload: ReportPayload, output_path: Path) -> None: ...


_SECTION_TITLES = {
    ReportSection.OVERVIEW: "Overview",
    ReportSection.DECISION: "Investment Decision",
    ReportSection.MARKET: "Market Analysis",
    ReportSection.NEWS: "News Analysis",
    ReportSection.FUNDAMENTALS: "Fundamental Analysis",
    ReportSection.RISK: "Risk Analysis",
    ReportSection.CONSTITUENTS: "Matched Tickers",
    ReportSection.DATA_GAPS: "Data Gaps",
    ReportSection.SOURCES: "Sources",
}


class ReportService:
    def __init__(
        self,
        repository: ReportRepository,
        resolver: ReportSourceResolver,
        renderer: PdfRenderer,
        max_workers: int = 2,
    ) -> None:
        if not 1 <= max_workers <= 4:
            raise ValueError("max_workers must be between 1 and 4")
        self._repository = repository
        self._resolver = resolver
        self._renderer = renderer
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._repository.recover_interrupted()

    def generate_stock_now(self, **kwargs: object) -> ReportJob:
        job, payload = self._prepare_stock(**kwargs)
        return self._run(job, payload)

    def submit_stock(self, **kwargs: object) -> ReportJob:
        job, payload = self._prepare_stock(**kwargs)
        self._executor.submit(self._run, job, payload)
        return job

    def generate_sector_now(self, **kwargs: object) -> ReportJob:
        job, payload = self._prepare_sector(**kwargs)
        return self._run(job, payload)

    def submit_sector(self, **kwargs: object) -> ReportJob:
        job, payload = self._prepare_sector(**kwargs)
        self._executor.submit(self._run, job, payload)
        return job

    def close(self) -> None:
        self._executor.shutdown(wait=True)

    def _prepare_stock(self, **kwargs: object) -> tuple[ReportJob, ReportPayload]:
        sections = self._sections(kwargs["sections"])
        self._preflight()
        source = self._resolver.stock(
            str(kwargs["ticker"]),
            str(kwargs["strategy_id"]),
            str(kwargs["session_id"]) if kwargs.get("session_id") else None,
        )
        return self._prepare(ReportType.STOCK, str(kwargs["title"]), source, sections)

    def _prepare_sector(self, **kwargs: object) -> tuple[ReportJob, ReportPayload]:
        sections = self._sections(kwargs["sections"])
        self._preflight()
        source = self._resolver.sector(str(kwargs["scan_run_id"]))
        return self._prepare(ReportType.SECTOR, str(kwargs["title"]), source, sections)

    def _prepare(
        self,
        report_type: ReportType,
        title: str,
        source: ResolvedReportSource,
        sections: tuple[ReportSection, ...],
    ) -> tuple[ReportJob, ReportPayload]:
        rendered = tuple(
            RenderedSection(
                kind=section,
                title=_SECTION_TITLES[section],
                content=source.content[section],
            )
            for section in sections
            if section in source.content and source.content[section].strip()
        )
        if not rendered:
            raise ReportSourceError(
                "Selected sections have no persisted source content"
            )
        payload = ReportPayload(
            report_type=report_type,
            title=title,
            tickers=source.tickers,
            source_ids=source.source_ids,
            sections=rendered,
            generated_at=datetime.now(timezone.utc),
        )
        job = self._repository.create(
            report_type=report_type,
            title=title,
            tickers=source.tickers,
            source_type=source.source_type,
            source_ids=source.source_ids,
            parameters={"sections": [section.value for section in sections]},
        )
        return job, payload

    def _run(self, job: ReportJob, payload: ReportPayload) -> ReportJob:
        temporary = self._repository.artifact_root / f".{job.id}.tmp"
        final = self._repository.artifact_root / f"{job.id}.pdf"
        if not self._repository.mark_running(job.id):
            raise ReportGenerationError("Report job could not start")
        try:
            self._renderer.render(payload, temporary)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
            self._validate_pdf(temporary)
            temporary.replace(final)
            if not self._repository.complete(job.id, final.name):
                final.unlink(missing_ok=True)
                raise RuntimeError("report metadata did not complete")
        except Exception as error:
            temporary.unlink(missing_ok=True)
            final.unlink(missing_ok=True)
            self._repository.fail(job.id, "Report generation failed")
            raise ReportGenerationError("Report generation failed") from error
        completed = self._repository.get(job.id)
        if completed is None:
            raise ReportGenerationError("Report job disappeared")
        return completed

    def _preflight(self) -> None:
        try:
            self._renderer.preflight()
        except Exception as error:
            raise ReportGenerationError(
                "PDF renderer or Unicode font is unavailable"
            ) from error

    @staticmethod
    def _sections(value: object) -> tuple[ReportSection, ...]:
        if not isinstance(value, tuple) or not value:
            raise ValueError("at least one report section is required")
        return tuple(ReportSection(section) for section in value)

    @staticmethod
    def _validate_pdf(path: Path) -> None:
        with path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise RuntimeError("renderer output is not a PDF")
        if path.stat().st_size <= 5 or b"/Type /Page" not in path.read_bytes():
            raise RuntimeError("renderer output is empty")
