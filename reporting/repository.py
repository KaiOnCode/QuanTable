from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from reporting.models import ReportJob, ReportStatus, ReportType
from storage.store import ContextStore, ReportJobRecord


class ReportStorageError(RuntimeError):
    pass


class ArtifactUnavailableError(ReportStorageError):
    pass


class ReportRepository:
    def __init__(self, store: ContextStore, artifact_root: str | Path) -> None:
        self._store = store
        self.artifact_root = Path(artifact_root).resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        report_type: ReportType,
        title: str,
        tickers: tuple[str, ...],
        source_type: str,
        source_ids: tuple[str, ...],
        parameters: dict[str, object],
    ) -> ReportJob:
        record = self._store.create_report_job(
            uuid4().hex,
            report_type.value,
            title,
            json.dumps(tickers),
            source_type,
            json.dumps(source_ids),
            json.dumps(parameters, ensure_ascii=False),
        )
        return self._model(record)

    def get(self, report_id: str) -> ReportJob | None:
        record = self._store.get_report_job(report_id)
        return self._model(record) if record else None

    def list(self, limit: int = 50) -> list[ReportJob]:
        return [self._model(record) for record in self._store.list_report_jobs(limit)]

    def mark_running(self, report_id: str) -> bool:
        return self._store.mark_report_job_running(report_id)

    def complete(self, report_id: str, artifact_name: str) -> bool:
        if Path(artifact_name).name != artifact_name:
            raise ReportStorageError("artifact name must be a basename")
        return self._store.complete_report_job(report_id, artifact_name)

    def fail(self, report_id: str, error: str) -> bool:
        return self._store.fail_report_job(report_id, error)

    def recover_interrupted(self) -> int:
        return self._store.recover_interrupted_report_jobs()

    def resolve_artifact(self, report_id: str) -> Path:
        job = self.get(report_id)
        if job is None or job.status != "completed" or not job.artifact_name:
            raise ArtifactUnavailableError("Report artifact is unavailable")
        name = job.artifact_name
        if Path(name).name != name:
            raise ArtifactUnavailableError("Report artifact is unavailable")
        candidate = self.artifact_root / name
        if candidate.is_symlink():
            raise ArtifactUnavailableError("Report artifact is unavailable")
        resolved = candidate.resolve()
        if resolved.parent != self.artifact_root or not resolved.is_file():
            raise ArtifactUnavailableError("Report artifact is unavailable")
        return resolved

    def download_filename(self, report_id: str) -> str:
        job = self.get(report_id)
        if job is None:
            raise ArtifactUnavailableError("Report artifact is unavailable")
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", job.title).strip("-._")
        return f"{stem or 'report'}.pdf"

    @staticmethod
    def _model(record: ReportJobRecord) -> ReportJob:
        try:
            tickers = json.loads(record.tickers_json)
            source_ids = json.loads(record.source_ids_json)
            parameters = json.loads(record.parameters_json)
            return ReportJob(
                id=record.id,
                report_type=ReportType(record.report_type),
                title=record.title,
                tickers=tuple(tickers),
                source_type=record.source_type,
                source_ids=tuple(source_ids),
                parameters=parameters,
                status=ReportStatus(record.status),
                artifact_name=record.artifact_name,
                error=record.error,
                created_at=record.created_at,
                started_at=record.started_at,
                completed_at=record.completed_at,
                updated_at=record.updated_at,
            )
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
            raise ReportStorageError("Report job storage is corrupt") from error
