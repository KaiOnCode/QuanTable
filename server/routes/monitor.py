"""MonitorTask CRUD + execution endpoints.

GET  /api/monitors              — list all monitor tasks
POST /api/monitors              — create a new monitor task
GET  /api/monitors/:id          — get task detail
PUT  /api/monitors/:id          — update task config
DELETE /api/monitors/:id        — delete task
POST /api/monitors/:id/run      — trigger one execution
GET  /api/monitors/:id/reports  — list historical reports
GET  /api/monitors/:id/news     — list collected news
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["monitors"])
logger = logging.getLogger(__name__)

_running_tasks: set[str] = set()


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CRUD ────────────────────────────────────────────────────


@router.get("/monitors")
async def list_monitors(status: str | None = Query(None)):
    store = get_store()
    tasks = store.list_monitors(status=status)
    return {"monitors": tasks, "total": len(tasks)}


@router.post("/monitors", status_code=201)
async def create_monitor(config: dict):
    store = get_store()
    mid = str(uuid.uuid4())

    # Optional keyword expansion
    expand = config.get("expand_keywords", False)
    expanded_keywords = config.get("expanded_keywords", [])
    expanded_tickers = config.get("expanded_tickers", [])
    if expand:
        try:
            from server.monitor_engine import expand_keywords

            result = expand_keywords(
                config.get("name", ""),
                config.get("description", ""),
            )
            expanded_keywords = result.get("keywords", [])
            expanded_tickers = result.get("tickers", [])
        except Exception as exc:
            logger.warning("Keyword expansion failed: %s", exc)

    monitor_id = store.register_monitor(
        {
            "id": mid,
            "name": config.get("name", "Untitled Monitor"),
            "description": config.get("description", ""),
            "mode": config.get("mode", "keyword"),
            "targets": config.get("targets", {}),
            "sources": config.get("sources", ["news", "prices"]),
            "schedule": config.get("schedule", {}),
            "agent": config.get("agent", {}),
            "output": config.get("output", {}),
            "cron_expression": config.get("cron_expression", ""),
            "expanded_keywords": expanded_keywords,
            "expanded_tickers": expanded_tickers,
            "report_language": config.get("report_language", "zh"),
            "status": "active",
            "created_at": _now(),
        }
    )

    # Register scheduler job
    _register_job(monitor_id, config.get("cron_expression", ""))

    result = store.get_monitor(monitor_id)
    if result is None:
        raise HTTPException(500, "Monitor was not created")
    result["expanded_keywords"] = expanded_keywords
    result["expanded_tickers"] = expanded_tickers
    return result


@router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: str):
    task = get_store().get_monitor(monitor_id)
    if task is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")
    return task


@router.put("/monitors/{monitor_id}")
async def update_monitor(monitor_id: str, config: dict):
    task = get_store().get_monitor(monitor_id)
    if task is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")

    result = get_store().update_monitor(monitor_id, config)
    if result is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")

    # Re-register scheduler job if cron changed
    if "cron_expression" in config:
        _register_job(monitor_id, config["cron_expression"])
    return result


@router.delete("/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str):
    get_store().delete_monitor(monitor_id)
    _remove_job(monitor_id)
    return {"deleted": monitor_id}


# ── Reports ─────────────────────────────────────────────────


@router.get("/monitors/{monitor_id}/reports")
async def list_reports(monitor_id: str, limit: int = Query(20, ge=1, le=100)):
    reports = get_store().list_monitoring_reports(monitor_id, limit=limit)
    return {"reports": reports, "total": len(reports)}


# ── Collected News ──────────────────────────────────────────


@router.get("/monitors/{monitor_id}/news")
async def list_news(monitor_id: str, limit: int = Query(50, ge=1, le=200)):
    news = get_store().list_monitor_news(monitor_id, limit=limit)
    return {"news": news, "total": len(news)}


# ── Execution ───────────────────────────────────────────────


@router.post("/monitors/{monitor_id}/run")
async def run_monitor(monitor_id: str):
    """Trigger a single execution of a monitor task."""
    task = get_store().get_monitor(monitor_id)
    if task is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")

    if monitor_id in _running_tasks or task.get("run_status") == "running":
        raise HTTPException(409, "Task is already running. Please wait.")

    targets = task.get("targets", {})
    mode = task.get("mode", "keyword")
    has_input = bool(
        (mode == "keyword" and targets.get("keywords"))
        or (mode == "ticker" and targets.get("tickers"))
    )
    if not has_input:
        raise HTTPException(400, "Add keywords or tickers before running this task.")

    run_id = str(uuid.uuid4())
    started = get_store().start_monitor_run(monitor_id, run_id)
    if started is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")

    _running_tasks.add(monitor_id)
    asyncio.create_task(_execute_monitor_run(monitor_id, run_id))
    return {
        "ok": True,
        "monitor_id": monitor_id,
        "run_id": run_id,
        "status": "running",
    }


async def _execute_monitor_run(monitor_id: str, run_id: str) -> None:
    try:
        from server.monitor_engine import execute

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, execute, monitor_id)
        get_store().finish_monitor_run(monitor_id, run_id)
    except Exception as exc:
        logger.exception("Manual run failed for monitor %s", monitor_id)
        get_store().fail_monitor_run(monitor_id, run_id, str(exc))
    finally:
        _running_tasks.discard(monitor_id)


# ── Scheduler integration ───────────────────────────────────


def _register_job(monitor_id: str, cron_expression: str) -> None:
    """Register or update a cron job for this monitor."""
    if not cron_expression:
        _remove_job(monitor_id)
        return
    try:
        from apscheduler.triggers.cron import CronTrigger
        from scheduler import _get_scheduler

        scheduler = _get_scheduler()
        if not scheduler:
            return

        job_id = f"monitor_{monitor_id}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

        trigger = CronTrigger.from_crontab(cron_expression)
        scheduler.add_job(
            _run_scheduled,
            trigger=trigger,
            args=[monitor_id],
            id=job_id,
            replace_existing=True,
        )
        logger.info("Monitor %s scheduled: %s", monitor_id, cron_expression)
    except Exception as exc:
        logger.warning("Failed to register cron for %s: %s", monitor_id, exc)


def _remove_job(monitor_id: str) -> None:
    try:
        from scheduler import _get_scheduler

        scheduler = _get_scheduler()
        if scheduler:
            scheduler.remove_job(f"monitor_{monitor_id}")
    except Exception:
        pass


def _run_scheduled(monitor_id: str) -> None:
    """Entry point for APScheduler job."""
    import threading

    def _run():
        store = get_store()
        task = store.get_monitor(monitor_id)
        if task is None:
            return
        if monitor_id in _running_tasks or task.get("run_status") == "running":
            logger.info("Skipping scheduled monitor %s; run already active", monitor_id)
            return
        run_id = str(uuid.uuid4())
        started = store.start_monitor_run(monitor_id, run_id)
        if started is None:
            return
        _running_tasks.add(monitor_id)
        try:
            from server.monitor_engine import execute

            execute(monitor_id)
            store.finish_monitor_run(monitor_id, run_id)
        except Exception as exc:
            logger.error("Scheduled run failed for %s: %s", monitor_id, exc)
            store.fail_monitor_run(monitor_id, run_id, str(exc))
        finally:
            _running_tasks.discard(monitor_id)

    threading.Thread(target=_run, daemon=True).start()


# ── Re-register on startup ──────────────────────────────────


def register_all_jobs() -> None:
    """Re-register all active monitors' cron jobs on server startup."""
    try:
        store = get_store()
        tasks = store.list_monitors(status="active")
        count = 0
        for t in tasks:
            cron = t.get("cron_expression", "")
            if cron:
                _register_job(t["id"], cron)
                count += 1
        if count:
            logger.info("Registered %d monitor cron jobs", count)
    except Exception as exc:
        logger.warning("Failed to register monitor jobs: %s", exc)
