from __future__ import annotations

import json
import time
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import Any, Literal

HISTORY_DIR = Path(__file__).resolve().parent.parent / "data" / "history"

RunEvent = tuple[Literal["progress", "debate", "result", "error"], dict[str, Any]]
SubscriberQueue = Queue[RunEvent | None]

_subscribers: dict[str, list[SubscriberQueue]] = {}
_subscribers_lock = Lock()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _snapshot_path(session_id: str) -> Path:
    return HISTORY_DIR / f"{session_id}.json"


def _deleted_dir() -> Path:
    return HISTORY_DIR / ".deleted"


def _deletion_marker_path(session_id: str) -> Path:
    return _deleted_dir() / f"{session_id}.deleted"


def is_snapshot_deleted(session_id: str) -> bool:
    return _deletion_marker_path(session_id).exists()


def _write_snapshot(snapshot: dict[str, Any]) -> None:
    session_id = str(snapshot["session_id"])
    if is_snapshot_deleted(session_id):
        return
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _snapshot_path(session_id)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def create_running_snapshot(
    *,
    session_id: str,
    ticker: str,
    mode: str,
    request_payload: dict[str, object],
) -> dict[str, object]:
    now = _now()
    snapshot: dict[str, object] = {
        "session_id": session_id,
        "ticker": ticker,
        "mode": mode,
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "request": request_payload,
        "progress_events": [],
        "agent_reports": {},
        "result": None,
        "error": None,
    }
    _write_snapshot(snapshot)
    return snapshot


def load_snapshot(session_id: str) -> dict[str, Any]:
    if is_snapshot_deleted(session_id):
        raise FileNotFoundError(session_id)
    return json.loads(_snapshot_path(session_id).read_text(encoding="utf-8"))


def delete_snapshot(session_id: str) -> bool:
    path = _snapshot_path(session_id)
    existed = path.exists()
    _deleted_dir().mkdir(parents=True, exist_ok=True)
    _deletion_marker_path(session_id).write_text(_now(), encoding="utf-8")
    if existed:
        path.unlink()
    return existed


def record_progress(session_id: str, event: dict[str, object]) -> None:
    if is_snapshot_deleted(session_id):
        return
    snapshot = load_snapshot(session_id)
    event_with_time = dict(event)
    event_with_time.setdefault("timestamp", _now())
    progress_events = list(snapshot.get("progress_events") or [])
    progress_events.append(event_with_time)
    snapshot["progress_events"] = progress_events

    agent = event_with_time.get("agent")
    report = event_with_time.get("report")
    if isinstance(agent, str) and isinstance(report, str) and report:
        agent_reports = dict(snapshot.get("agent_reports") or {})
        agent_reports[agent] = report
        snapshot["agent_reports"] = agent_reports

    snapshot["updated_at"] = _now()
    _write_snapshot(snapshot)


def complete_snapshot(session_id: str, result_payload: dict[str, object]) -> None:
    if is_snapshot_deleted(session_id):
        return
    snapshot = load_snapshot(session_id)
    now = _now()
    snapshot["status"] = "completed"
    snapshot["updated_at"] = now
    snapshot["completed_at"] = now
    snapshot["result"] = result_payload
    snapshot["error"] = None
    if isinstance(result_payload.get("agent_reports"), dict):
        agent_reports = dict(snapshot.get("agent_reports") or {})
        agent_reports.update(result_payload["agent_reports"])  # type: ignore[arg-type]
        snapshot["agent_reports"] = agent_reports
    _write_snapshot(snapshot)


def fail_snapshot(session_id: str, error: str) -> None:
    if is_snapshot_deleted(session_id):
        return
    snapshot = load_snapshot(session_id)
    now = _now()
    snapshot["status"] = "failed"
    snapshot["updated_at"] = now
    snapshot["completed_at"] = now
    snapshot["error"] = error
    _write_snapshot(snapshot)


def list_snapshots(limit: int = 20) -> list[dict[str, Any]]:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        HISTORY_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    snapshots: list[dict[str, Any]] = []
    for path in files:
        if len(snapshots) >= limit:
            break
        session_id = path.stem
        if is_snapshot_deleted(session_id):
            continue
        try:
            snapshots.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return snapshots


def create_run(session_id: str) -> None:
    with _subscribers_lock:
        _subscribers.setdefault(session_id, [])


def has_run(session_id: str) -> bool:
    if is_snapshot_deleted(session_id):
        return False
    with _subscribers_lock:
        if session_id in _subscribers:
            return True
    return _snapshot_path(session_id).exists()


def subscribe_run(session_id: str) -> SubscriberQueue:
    queue: SubscriberQueue = Queue()
    with _subscribers_lock:
        subscribers = _subscribers.get(session_id)
        if subscribers is not None:
            subscribers.append(queue)
            return queue

    try:
        snapshot = load_snapshot(session_id)
    except FileNotFoundError:
        queue.put(None)
        return queue

    status = snapshot.get("status", "completed")
    if status == "completed" and snapshot.get("result"):
        queue.put(("result", snapshot["result"]))  # type: ignore[arg-type]
    elif status == "failed":
        queue.put(
            (
                "error",
                {
                    "agent": "orchestrator",
                    "error": str(snapshot.get("error") or "Analysis failed"),
                    "timestamp": _now(),
                },
            )
        )
    queue.put(None)
    return queue


def publish_run_event(session_id: str, event: RunEvent) -> None:
    with _subscribers_lock:
        subscribers = list(_subscribers.get(session_id, []))
    for queue in subscribers:
        queue.put(event)


def close_run(session_id: str) -> None:
    with _subscribers_lock:
        subscribers = _subscribers.pop(session_id, [])
    for queue in subscribers:
        queue.put(None)


def run_orchestrator_stream(
    *,
    ticker: str,
    date: str,
    current_position_pct: float,
    strategy_id: str,
    session_id: str,
    memory_enabled: bool,
    account_id: str,
    decision_id: str,
):
    from quick_ask.orchestrator import IntelliFin_Assistant

    assistant = IntelliFin_Assistant()
    yield from assistant.stream(
        ticker,
        date=date,
        current_position_pct=current_position_pct,
        strategy_id=strategy_id,
        session_id=session_id,
        memory_enabled=memory_enabled,
        account_id=account_id,
        decision_id=decision_id,
    )
