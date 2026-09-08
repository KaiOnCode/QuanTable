from __future__ import annotations

from storage.store import ContextStore


def _create_monitor(store: ContextStore, monitor_id: str = "monitor-1") -> str:
    return store.register_monitor(
        {
            "id": monitor_id,
            "name": "AI Chip Watch",
            "mode": "keyword",
            "targets": {"keywords": ["AI chip"]},
            "sources": ["news"],
            "schedule": {},
            "agent": {},
            "output": {},
            "status": "active",
            "created_at": "2026-07-06T00:00:00Z",
        }
    )


def test_monitor_run_state_transitions(tmp_path) -> None:
    store = ContextStore(tmp_path)
    monitor_id = _create_monitor(store)

    store.start_monitor_run(monitor_id, run_id="run-1")
    running = store.get_monitor(monitor_id)
    assert running is not None
    assert running["run_status"] == "running"
    assert running["current_run_id"] == "run-1"
    assert running["last_run_started_at"]

    store.finish_monitor_run(monitor_id, run_id="run-1")
    finished = store.get_monitor(monitor_id)
    assert finished is not None
    assert finished["run_status"] == "idle"
    assert finished["current_run_id"] is None
    assert finished["last_run_finished_at"]
    assert finished["last_run_error"] == ""


def test_monitor_run_state_records_failure(tmp_path) -> None:
    store = ContextStore(tmp_path)
    monitor_id = _create_monitor(store)

    store.start_monitor_run(monitor_id, run_id="run-1")
    store.fail_monitor_run(monitor_id, run_id="run-1", error="Execution failed")

    failed = store.get_monitor(monitor_id)
    assert failed is not None
    assert failed["run_status"] == "failed"
    assert failed["current_run_id"] is None
    assert failed["last_run_error"] == "Execution failed"
