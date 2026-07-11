from __future__ import annotations

import json
from pathlib import Path

from reporting.models import ReportSection, ResolvedReportSource
from storage.store import ContextStore


class ReportSourceError(ValueError):
    pass


class ReportSourceResolver:
    def __init__(self, store: ContextStore, analysis_history: str | Path) -> None:
        self._store = store
        self._history = Path(analysis_history)

    def stock(
        self, ticker: str, strategy_id: str, session_id: str | None = None
    ) -> ResolvedReportSource:
        ticker = ticker.strip().upper()
        snapshot = (
            self._load_snapshot(session_id)
            if session_id
            else self._latest_snapshot(ticker, strategy_id)
        )
        self._validate_analysis(snapshot, ticker, strategy_id)
        try:
            return ResolvedReportSource(
                source_type="analysis",
                source_ids=(str(snapshot["session_id"]),),
                tickers=(ticker,),
                content=self._analysis_content(snapshot),
            )
        except ValueError as error:
            raise ReportSourceError(
                "Completed analysis has no report content"
            ) from error

    def sector(self, scan_run_id: str) -> ResolvedReportSource:
        run = self._store.get_scan_run(scan_run_id)
        if run is None:
            raise ReportSourceError("scan run not found")
        if run.status != "completed" or not run.result_json:
            raise ReportSourceError("scan run must be completed")
        result, tickers = self._scan_result(run.result_json)
        analysis_ids: list[str] = []
        gaps: list[str] = []
        analysis_parts: list[str] = []
        for ticker in tickers:
            try:
                snapshot = self._latest_snapshot(ticker, None)
                analysis_ids.append(str(snapshot["session_id"]))
                decision = self._analysis_content(snapshot).get(ReportSection.DECISION)
                if decision:
                    analysis_parts.append(f"{ticker}: {decision}")
            except ReportSourceError:
                gaps.append(f"{ticker}: completed analysis unavailable")
        content = {
            ReportSection.OVERVIEW: (
                f"Completed scan {scan_run_id} matched {len(tickers)} tickers."
            ),
            ReportSection.CONSTITUENTS: ", ".join(tickers),
            ReportSection.SOURCES: f"Scanner run: {scan_run_id}",
        }
        if analysis_parts:
            content[ReportSection.DECISION] = "\n".join(analysis_parts)
        raw_warnings = result.get("warnings", [])
        warnings = raw_warnings if isinstance(raw_warnings, list) else []
        all_gaps = gaps + [str(item) for item in warnings if str(item).strip()]
        if all_gaps:
            content[ReportSection.DATA_GAPS] = "\n".join(all_gaps)
        return ResolvedReportSource(
            source_type="scan_run",
            source_ids=(scan_run_id, *analysis_ids),
            tickers=tickers,
            content=content,
            data_gaps=tuple(gaps),
        )

    @staticmethod
    def _scan_result(raw: str) -> tuple[dict[str, object], tuple[str, ...]]:
        try:
            result = json.loads(raw)
            items = result["results"]
            tickers = tuple(
                sorted(
                    {
                        str(item["ticker"]).strip().upper()
                        for item in items
                        if isinstance(item, dict) and item.get("ticker")
                    }
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise ReportSourceError("Scanner run result is invalid") from error
        if not isinstance(result, dict):
            raise ReportSourceError("Scanner run result is invalid")
        if not tickers:
            raise ReportSourceError("Scanner run has no matched tickers")
        return result, tickers

    def _load_snapshot(self, session_id: str) -> dict[str, object]:
        if Path(session_id).name != session_id:
            raise ReportSourceError("Analysis snapshot not found")
        path = self._history / f"{session_id}.json"
        if path.is_symlink() or path.resolve().parent != self._history.resolve():
            raise ReportSourceError("Analysis snapshot not found")
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
            raise ReportSourceError("Analysis snapshot not found") from error
        if not isinstance(snapshot, dict):
            raise ReportSourceError("Analysis snapshot is invalid")
        return snapshot

    def _latest_snapshot(
        self, ticker: str, strategy_id: str | None
    ) -> dict[str, object]:
        candidates: list[tuple[str, dict[str, object]]] = []
        for path in self._history.glob("*.json"):
            if path.is_symlink():
                continue
            try:
                snapshot = json.loads(path.read_text(encoding="utf-8"))
                request = snapshot.get("request", {})
                if (
                    not isinstance(request, dict)
                    or snapshot.get("status") != "completed"
                ):
                    continue
                if str(snapshot.get("ticker", "")).upper() != ticker:
                    continue
                if (
                    strategy_id is not None
                    and request.get("strategy_id") != strategy_id
                ):
                    continue
                timestamp = str(
                    snapshot.get("completed_at") or snapshot.get("updated_at") or ""
                )
                candidates.append((timestamp, snapshot))
            except (json.JSONDecodeError, OSError, AttributeError):
                continue
        if not candidates:
            raise ReportSourceError("Completed analysis snapshot not found")
        return max(candidates, key=lambda item: item[0])[1]

    @staticmethod
    def _validate_analysis(
        snapshot: dict[str, object], ticker: str, strategy_id: str | None
    ) -> None:
        if snapshot.get("status") != "completed":
            raise ReportSourceError("Analysis snapshot must be completed")
        request = snapshot.get("request")
        if not isinstance(request, dict):
            raise ReportSourceError("Analysis snapshot identity is invalid")
        if str(snapshot.get("ticker", "")).upper() != ticker:
            raise ReportSourceError("Analysis snapshot identity does not match")
        if strategy_id is not None and request.get("strategy_id") != strategy_id:
            raise ReportSourceError("Analysis snapshot identity does not match")

    @staticmethod
    def _analysis_content(snapshot: dict[str, object]) -> dict[ReportSection, str]:
        result = snapshot.get("result")
        if not isinstance(result, dict):
            return {}
        reports = result.get("agent_reports")
        reports = reports if isinstance(reports, dict) else {}
        mapping = {
            ReportSection.DECISION: result.get("report"),
            ReportSection.MARKET: reports.get("market_analyst"),
            ReportSection.NEWS: reports.get("news_analyst"),
            ReportSection.FUNDAMENTALS: reports.get("fundamentals_analyst"),
            ReportSection.RISK: reports.get("risk_analyst"),
        }
        return {
            section: value.strip()
            for section, value in mapping.items()
            if isinstance(value, str) and value.strip()
        }
