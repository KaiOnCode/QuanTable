from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reporting.repository import ReportRepository
from reporting.service import ReportService
from reporting.source import ReportSourceResolver
from server.main import app
from storage.store import ContextStore


class _Renderer:
    def __init__(self, *, fail: bool = False, wait: float = 0) -> None:
        self.fail = fail
        self.wait = wait

    def preflight(self) -> None:
        return None

    def render(self, payload, output_path: Path) -> None:
        if self.wait:
            time.sleep(self.wait)
        if self.fail:
            raise RuntimeError("renderer secret detail")
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, payload.title)
        for section in payload.sections:
            pdf.ln(10)
            pdf.multi_cell(0, 8, f"{section.title}: {section.content}")
        pdf.output(str(output_path))


def _snapshot(history: Path, session_id: str = "analysis-1") -> None:
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{session_id}.json").write_text(
        json.dumps(
            {
                "session_id": session_id,
                "ticker": "AAPL",
                "status": "completed",
                "completed_at": "2026-07-11T00:00:00Z",
                "request": {"ticker": "AAPL", "strategy_id": "strategy-a"},
                "result": {
                    "report": "DECISION-AAPL",
                    "agent_reports": {
                        "market_analyst": "MARKET-AAPL",
                        "risk_analyst": "RISK-AAPL",
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _scan(store: ContextStore, run_id: str = "scan-1", *, matches: bool = True) -> None:
    store.create_scan_run(run_id, '{"mode":"agent","query":"technology"}', "agent")
    result = {
        "universe": [],
        "results": ([{"ticker": "AAPL", "snapshot": {}}] if matches else []),
        "scanned_count": 1,
        "matched_count": 1 if matches else 0,
        "missing_data_count": 0,
        "warnings": [],
        "scanned_at": "2026-07-11T00:00:00Z",
    }
    assert store.complete_scan_run(run_id, "[]", json.dumps(result))


@pytest.fixture
def reports_api(tmp_path: Path):
    from server.routes import reports

    store = ContextStore(tmp_path / "data")
    history = tmp_path / "history"
    repository = ReportRepository(store, tmp_path / "artifacts")
    service = ReportService(
        repository, ReportSourceResolver(store, history), _Renderer()
    )
    app.dependency_overrides[reports.get_report_repository] = lambda: repository
    app.dependency_overrides[reports.get_report_service] = lambda: service
    with TestClient(app) as client:
        yield client, store, history, repository
    app.dependency_overrides.clear()
    service.close()
    store.close()


def _poll(client: TestClient, report_id: str) -> dict[str, object]:
    for _ in range(100):
        response = client.get(f"/api/reports/{report_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("report did not settle")


def test_stock_create_poll_list_and_safe_pdf_download(reports_api) -> None:
    client, _, history, _ = reports_api
    _snapshot(history)

    created = client.post(
        "/api/reports/stock",
        json={
            "ticker": "aapl",
            "strategy_id": "strategy-a",
            "session_id": "analysis-1",
            "sections": ["decision", "risk"],
        },
    )
    assert created.status_code == 201
    assert set(created.json()).isdisjoint({"artifact_name", "content_path"})
    completed = _poll(client, created.json()["id"])
    assert completed["status"] == "completed"
    assert completed["parameters"] == {"sections": ["decision", "risk"]}

    listed = client.get("/api/reports")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0] == completed

    downloaded = client.get(f"/api/reports/{completed['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.content.startswith(b"%PDF-")
    disposition = downloaded.headers["content-disposition"]
    assert disposition == 'attachment; filename="AAPL-source-report.pdf"'
    assert "/" not in disposition.removeprefix('attachment; filename="').removesuffix(
        '"'
    )


def test_sector_create_uses_completed_scan_and_empty_source_is_422(reports_api) -> None:
    client, store, history, _ = reports_api
    _snapshot(history)
    _scan(store)

    created = client.post(
        "/api/reports/sector",
        json={"scan_run_id": "scan-1", "sections": ["overview", "constituents"]},
    )
    assert created.status_code == 201
    completed = _poll(client, created.json()["id"])
    assert completed["status"] == "completed"
    assert completed["source_type"] == "scan_run"
    assert completed["tickers"] == ["AAPL"]

    _scan(store, "scan-empty", matches=False)
    empty = client.post(
        "/api/reports/sector",
        json={"scan_run_id": "scan-empty", "sections": ["overview"]},
    )
    assert empty.status_code == 422
    assert "matched tickers" in empty.json()["detail"]


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/reports/stock",
            {
                "ticker": "AAPL",
                "strategy_id": "strategy-a",
                "session_id": "missing",
                "sections": ["decision"],
            },
        ),
        ("/api/reports/sector", {"scan_run_id": "missing", "sections": ["overview"]}),
        (
            "/api/reports/stock",
            {
                "ticker": "AAPL",
                "strategy_id": "strategy-a",
                "session_id": "../secret",
                "sections": ["decision"],
            },
        ),
    ],
)
def test_source_errors_are_safe_422(
    reports_api, path: str, payload: dict[str, object]
) -> None:
    client, _, _, _ = reports_api
    response = client.post(path, json=payload)
    assert response.status_code == 422
    assert "secret" not in response.text


def test_pending_missing_and_deleted_download_are_not_served(reports_api) -> None:
    from reporting.models import ReportType

    client, _, _, repository = reports_api
    pending = repository.create(
        report_type=ReportType.STOCK,
        title="Pending",
        tickers=("AAPL",),
        source_type="analysis",
        source_ids=("analysis-1",),
        parameters={},
    )
    assert client.get(f"/api/reports/{pending.id}/download").status_code == 409
    assert client.get("/api/reports/missing").status_code == 404
    assert client.get("/api/reports/missing/download").status_code == 404

    repository.mark_running(pending.id)
    final = repository.artifact_root / f"{pending.id}.pdf"
    final.write_bytes(b"%PDF-/Type /Page")
    repository.complete(pending.id, final.name)
    final.unlink()
    assert client.get(f"/api/reports/{pending.id}/download").status_code == 404


def test_renderer_failure_becomes_safe_failed_job(tmp_path: Path) -> None:
    from server.routes import reports

    store = ContextStore(tmp_path / "data")
    history = tmp_path / "history"
    _snapshot(history)
    repository = ReportRepository(store, tmp_path / "artifacts")
    service = ReportService(
        repository, ReportSourceResolver(store, history), _Renderer(fail=True)
    )
    app.dependency_overrides[reports.get_report_repository] = lambda: repository
    app.dependency_overrides[reports.get_report_service] = lambda: service
    with TestClient(app) as client:
        created = client.post(
            "/api/reports/stock",
            json={
                "ticker": "AAPL",
                "strategy_id": "strategy-a",
                "session_id": "analysis-1",
                "sections": ["decision"],
            },
        )
        failed = _poll(client, created.json()["id"])
        assert failed["status"] == "failed"
        assert failed["error"] == "Report generation failed"
        assert "secret" not in json.dumps(failed)
    app.dependency_overrides.clear()
    service.close()
    store.close()
