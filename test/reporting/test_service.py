from __future__ import annotations

import json
import os
import subprocess
from threading import Event
from pathlib import Path

import pytest

from reporting.models import ReportSection, ReportType
from reporting.repository import ArtifactUnavailableError, ReportRepository
from reporting.service import (
    ReportGenerationError,
    ReportService,
    ReportSourceError,
    ReportSourceResolver,
)
from storage.store import ContextStore
from utils.pdf_generator import ReportPdfRenderer


class _PdfRenderer:
    def __init__(self, *, preflight_error: Exception | None = None, fail: bool = False):
        self.preflight_error = preflight_error
        self.fail = fail

    def preflight(self) -> None:
        if self.preflight_error:
            raise self.preflight_error

    def render(self, payload, output_path: Path) -> None:
        if self.fail:
            output_path.write_bytes(b"partial")
            raise RuntimeError("renderer exploded at /secret/font.ttf")
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, payload.title)
        for section in payload.sections:
            pdf.ln(10)
            pdf.multi_cell(0, 8, f"{section.title}: {section.content}")
        pdf.output(str(output_path))


def _snapshot(
    history: Path,
    session_id: str,
    ticker: str = "AAPL",
    strategy_id: str = "strategy-a",
    status: str = "completed",
) -> None:
    history.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "ticker": ticker,
        "status": status,
        "completed_at": "2026-07-11T00:00:00Z" if status == "completed" else None,
        "request": {"ticker": ticker, "strategy_id": strategy_id},
        "result": {
            "report": f"DECISION-{ticker}",
            "action": "BUY",
            "agent_reports": {
                "market_analyst": f"MARKET-{ticker}",
                "risk_analyst": f"RISK-{ticker}",
            },
        }
        if status == "completed"
        else None,
        "agent_reports": {},
    }
    (history / f"{session_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _completed_scan(store: ContextStore, run_id: str = "scan-1") -> None:
    store.create_scan_run(run_id, '{"conditions":[]}', "rule")
    result = {
        "universe": [],
        "results": [
            {"ticker": "AAPL", "snapshot": {"sector": {"value": "Technology"}}},
            {"ticker": "MSFT", "snapshot": {"sector": {"value": "Technology"}}},
        ],
        "scanned_count": 2,
        "matched_count": 2,
        "missing_data_count": 0,
        "warnings": ["MSFT: missing analysis"],
        "scanned_at": "2026-07-11T00:00:00Z",
    }
    assert store.complete_scan_run(run_id, "[]", json.dumps(result))


@pytest.fixture
def reporting(tmp_path: Path):
    store = ContextStore(tmp_path / "data")
    history = tmp_path / "history"
    repository = ReportRepository(store, tmp_path / "generated-reports")
    resolver = ReportSourceResolver(store, history)
    yield store, history, repository, resolver
    store.close()


def test_stock_source_requires_completed_exact_identity_and_latest(reporting) -> None:
    store, history, _, resolver = reporting
    del store
    _snapshot(history, "older", status="completed")
    _snapshot(history, "newer", status="completed")
    os.utime(history / "older.json", (1, 1))
    os.utime(history / "newer.json", (2, 2))

    explicit = resolver.stock("AAPL", "strategy-a", session_id="older")
    latest = resolver.stock("AAPL", "strategy-a")
    assert explicit.source_ids == ("older",)
    assert latest.source_ids == ("newer",)

    _snapshot(history, "running", status="running")
    with pytest.raises(ReportSourceError, match="completed"):
        resolver.stock("AAPL", "strategy-a", session_id="running")
    with pytest.raises(ReportSourceError, match="identity"):
        resolver.stock("MSFT", "strategy-a", session_id="older")


def test_stock_source_excludes_tombstoned_analysis(reporting) -> None:
    _, history, _, resolver = reporting
    _snapshot(history, "deleted")
    deleted_dir = history / ".deleted"
    deleted_dir.mkdir(parents=True)
    (deleted_dir / "deleted.deleted").write_text("deleted", encoding="utf-8")

    with pytest.raises(ReportSourceError, match="not found"):
        resolver.stock("AAPL", "strategy-a", session_id="deleted")

    _snapshot(history, "available")
    latest = resolver.stock("AAPL", "strategy-a")
    assert latest.source_ids == ("available",)


def test_sector_uses_only_completed_scan_tickers_and_marks_analysis_gap(
    reporting,
) -> None:
    store, history, _, resolver = reporting
    _completed_scan(store)
    _snapshot(history, "aapl-analysis")

    source = resolver.sector("scan-1")

    assert source.tickers == ("AAPL", "MSFT")
    assert source.source_ids == ("scan-1", "aapl-analysis")
    assert source.data_gaps == ("MSFT: completed analysis unavailable",)
    with pytest.raises(ReportSourceError, match="scan run"):
        resolver.sector("missing")
    store.create_scan_run("running-scan", "{}", "rule")
    with pytest.raises(ReportSourceError, match="completed"):
        resolver.sector("running-scan")


def test_job_is_durable_atomic_and_selected_sections_control_pdf(reporting) -> None:
    store, history, repository, resolver = reporting
    _snapshot(history, "analysis-1")
    service = ReportService(repository, resolver, _PdfRenderer(), max_workers=1)

    job = service.generate_stock_now(
        title="AAPL audit",
        ticker="AAPL",
        strategy_id="strategy-a",
        session_id="analysis-1",
        sections=(ReportSection.DECISION, ReportSection.RISK),
    )

    assert job.status == "completed"
    artifact = repository.resolve_artifact(job.id)
    assert artifact.read_bytes().startswith(b"%PDF-")
    assert artifact.stat().st_size > 100
    assert not (repository.artifact_root / f".{job.id}.tmp").exists()
    reopened = ReportRepository(ContextStore(store.data_dir), repository.artifact_root)
    assert reopened.get(job.id) == job
    extracted = artifact.with_suffix(".txt")
    subprocess.run(
        ["pdftotext", str(artifact), str(extracted)], check=True, capture_output=True
    )
    text = extracted.read_text(encoding="utf-8")
    assert "DECISION-AAPL" in text
    assert "RISK-AAPL" in text
    assert "MARKET-AAPL" not in text
    service.close()


@pytest.mark.parametrize("failure", ["preflight", "render", "invalid_pdf"])
def test_failures_leave_no_temp_or_final(reporting, failure: str) -> None:
    _, history, repository, resolver = reporting
    _snapshot(history, "analysis-1")
    if failure == "preflight":
        renderer = _PdfRenderer(
            preflight_error=RuntimeError("font /secret/path missing")
        )
    elif failure == "render":
        renderer = _PdfRenderer(fail=True)
    else:

        class InvalidRenderer(_PdfRenderer):
            def render(self, payload, output_path: Path) -> None:
                output_path.write_bytes(b"not a pdf")

        renderer = InvalidRenderer()
    service = ReportService(repository, resolver, renderer, max_workers=1)

    with pytest.raises(ReportGenerationError) as caught:
        service.generate_stock_now(
            title="Failure",
            ticker="AAPL",
            strategy_id="strategy-a",
            session_id="analysis-1",
            sections=(ReportSection.DECISION,),
        )

    assert "/secret/" not in str(caught.value)
    jobs = repository.list()
    if failure == "preflight":
        assert jobs == []
    else:
        assert jobs[0].status == "failed"
        assert jobs[0].error == "Report generation failed"
        assert not (repository.artifact_root / f".{jobs[0].id}.tmp").exists()
        assert not (repository.artifact_root / f"{jobs[0].id}.pdf").exists()
    service.close()


def test_recovery_and_safe_artifact_resolution(reporting, tmp_path: Path) -> None:
    store, _, repository, _ = reporting
    pending = repository.create(
        report_type=ReportType.STOCK,
        title="Pending",
        tickers=("AAPL",),
        source_type="analysis",
        source_ids=("analysis-1",),
        parameters={},
    )
    assert repository.mark_running(pending.id)
    assert repository.recover_interrupted() == 1
    recovered = repository.get(pending.id)
    assert recovered is not None and recovered.status == "failed"

    malicious = repository.create(
        report_type=ReportType.STOCK,
        title="Traversal",
        tickers=("AAPL",),
        source_type="analysis",
        source_ids=("analysis-1",),
        parameters={},
    )
    store._system_db().execute(
        "UPDATE report_jobs SET status='completed', artifact_name='../outside.pdf' WHERE id=?",
        (malicious.id,),
    )
    store._system_db().commit()
    with pytest.raises(ArtifactUnavailableError):
        repository.resolve_artifact(malicious.id)

    target = tmp_path / "outside.pdf"
    target.write_bytes(b"%PDF-outside")
    link = repository.artifact_root / "linked.pdf"
    link.symlink_to(target)
    store._system_db().execute(
        "UPDATE report_jobs SET artifact_name='linked.pdf' WHERE id=?", (malicious.id,)
    )
    store._system_db().commit()
    with pytest.raises(ArtifactUnavailableError):
        repository.resolve_artifact(malicious.id)
    link.unlink()
    with pytest.raises(ArtifactUnavailableError):
        repository.resolve_artifact(malicious.id)


def test_empty_required_source_and_empty_sections_are_rejected(reporting) -> None:
    _, history, repository, resolver = reporting
    _snapshot(history, "empty")
    data = json.loads((history / "empty.json").read_text())
    data["result"]["report"] = ""
    data["result"]["agent_reports"] = {}
    (history / "empty.json").write_text(json.dumps(data), encoding="utf-8")
    service = ReportService(repository, resolver, _PdfRenderer())
    with pytest.raises(ReportSourceError, match="content"):
        resolver.stock("AAPL", "strategy-a", "empty")
    with pytest.raises(ValueError, match="section"):
        service.generate_stock_now(
            title="No sections",
            ticker="AAPL",
            strategy_id="strategy-a",
            session_id="empty",
            sections=(),
        )
    service.close()


def test_real_unicode_renderer_generates_readable_pdf(reporting) -> None:
    _, history, repository, resolver = reporting
    _snapshot(history, "analysis-real")
    data = json.loads((history / "analysis-real.json").read_text())
    data["result"]["report"] = "真实投资结论"
    (history / "analysis-real.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    service = ReportService(repository, resolver, ReportPdfRenderer())

    job = service.generate_stock_now(
        title="AAPL 真实报告",
        ticker="AAPL",
        strategy_id="strategy-a",
        session_id="analysis-real",
        sections=(ReportSection.DECISION,),
    )

    artifact = repository.resolve_artifact(job.id)
    info = subprocess.run(
        ["pdfinfo", str(artifact)], check=True, capture_output=True, text=True
    ).stdout
    extracted = artifact.with_suffix(".txt")
    subprocess.run(["pdftotext", str(artifact), str(extracted)], check=True)
    assert "Pages:" in info and "Pages:           1" in info
    assert "真实投资结论" in extracted.read_text(encoding="utf-8")
    service.close()


def test_background_job_has_no_final_artifact_before_renderer_finishes(
    reporting,
) -> None:
    _, history, repository, resolver = reporting
    _snapshot(history, "analysis-async")
    entered = Event()
    release = Event()

    class BlockingRenderer(_PdfRenderer):
        def render(self, payload, output_path: Path) -> None:
            entered.set()
            assert release.wait(timeout=5)
            super().render(payload, output_path)

    service = ReportService(repository, resolver, BlockingRenderer(), max_workers=1)
    job = service.submit_stock(
        title="Async",
        ticker="AAPL",
        strategy_id="strategy-a",
        session_id="analysis-async",
        sections=(ReportSection.DECISION,),
    )
    assert entered.wait(timeout=5)
    current = repository.get(job.id)
    assert current is not None and current.status == "running"
    assert not (repository.artifact_root / f"{job.id}.pdf").exists()
    release.set()
    service.close()
    completed = repository.get(job.id)
    assert completed is not None and completed.status == "completed"


def test_session_id_traversal_and_unknown_section_are_rejected(reporting) -> None:
    _, _, repository, resolver = reporting
    with pytest.raises(ReportSourceError):
        resolver.stock("AAPL", "strategy-a", "../outside")
    service = ReportService(repository, resolver, _PdfRenderer())
    with pytest.raises(ValueError):
        service.generate_stock_now(
            title="Invalid",
            ticker="AAPL",
            strategy_id="strategy-a",
            session_id="anything",
            sections=("unsupported",),
        )
    service.close()
