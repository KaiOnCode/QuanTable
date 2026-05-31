"""MonitorTask CRUD + execution endpoints.

GET  /api/monitors              — list all monitor tasks
POST /api/monitors              — create a new monitor task
GET  /api/monitors/:id          — get task detail
PUT  /api/monitors/:id          — update task config
DELETE /api/monitors/:id        — delete task
POST /api/monitors/:id/run      — trigger one execution
GET  /api/monitors/:id/reports  — list historical reports
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Query

from storage import get_store

router = APIRouter(tags=["monitors"])
logger = logging.getLogger(__name__)

# Track currently-executing tasks to prevent duplicate runs
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
    monitor_id = store.register_monitor({
        "id": str(uuid.uuid4()),
        "name": config.get("name", "Untitled Monitor"),
        "description": config.get("description", ""),
        "mode": config.get("mode", "keyword"),
        "targets": config.get("targets", {}),
        "sources": config.get("sources", ["news"]),
        "schedule": config.get("schedule", {"frequency": "daily", "time": "09:00"}),
        "agent": config.get("agent", {"enabled": False}),
        "output": config.get("output", {"format": "summary", "language": "zh"}),
        "status": "active",
        "created_at": _now(),
    })
    return get_store().get_monitor(monitor_id)


@router.get("/monitors/{monitor_id}")
async def get_monitor(monitor_id: str):
    task = get_store().get_monitor(monitor_id)
    if task is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")
    return task


@router.put("/monitors/{monitor_id}")
async def update_monitor(monitor_id: str, config: dict):
    result = get_store().update_monitor(monitor_id, config)
    if result is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")
    return result


@router.delete("/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str):
    get_store().delete_monitor(monitor_id)
    return {"deleted": monitor_id}


# ── Reports ─────────────────────────────────────────────────


@router.get("/monitors/{monitor_id}/reports")
async def list_reports(monitor_id: str, limit: int = Query(20, ge=1, le=100)):
    reports = get_store().list_monitoring_reports(monitor_id, limit=limit)
    return {"reports": reports, "total": len(reports)}


# ── Execution ───────────────────────────────────────────────


@router.post("/monitors/{monitor_id}/run")
async def run_monitor(monitor_id: str):
    """Trigger a single execution of a monitor task.
    Returns the generated MonitoringReport.
    """
    task = get_store().get_monitor(monitor_id)
    if task is None:
        raise HTTPException(404, f"Monitor {monitor_id} not found")

    # Prevent concurrent execution
    if monitor_id in _running_tasks:
        raise HTTPException(409, "Task is already running. Please wait.")

    # Validate that task has actual targets
    targets = task.get("targets", {})
    mode = task.get("mode", "keyword")
    has_input = bool(
        (mode == "keyword" and targets.get("keywords"))
        or (mode == "ticker" and targets.get("tickers"))
    )
    if not has_input:
        raise HTTPException(400, "Add keywords or tickers before running this task.")

    _running_tasks.add(monitor_id)
    try:
        report = _execute_monitor_task(task)
        report["monitor_id"] = monitor_id
        rid = get_store().save_monitoring_report(report)
        get_store().touch_monitor_run(monitor_id)
        return {"report_id": rid, "ok": True, **report}
    except Exception as exc:
        logger.exception("Manual run failed for monitor %s", monitor_id)
        raise HTTPException(500, f"Execution failed: {str(exc)[:200]}")
    finally:
        _running_tasks.discard(monitor_id)


def _execute_monitor_task(task: dict) -> dict:
    """Execute a monitor task: collect data via DataService, summarize, return report."""
    import time
    started_at = time.time()

    targets = task.get("targets", {}) or {}
    mode = task.get("mode", "keyword")
    sources = task.get("sources", ["news"])
    agent_cfg = task.get("agent", {}) or {}
    output_cfg = task.get("output", {}) or {}

    keywords = targets.get("keywords", []) if isinstance(targets, dict) else []
    tickers = targets.get("tickers", []) if isinstance(targets, dict) else []

    from dataflow.service import DataService
    svc = DataService()

    news_articles: list[dict] = []
    price_data: dict = {}
    search_details: list[str] = []

    # ── News (all through DataService) ──
    if "news" in sources:
        for kw in keywords[:5]:
            results = svc.search_news(kw, limit=10)
            search_details.append(f'keyword "{kw}": {len(results)} results')
            news_articles.extend(results)
        for t in tickers[:10]:
            articles = svc.get_news(t, window_days=7)
            search_details.append(f"ticker {t}: {len(articles)} articles")
            news_articles.extend(articles)
        seen: set[str] = set()
        news_articles = [n for n in news_articles if n["id"] not in seen and not seen.add(n["id"])]

    # ── Prices (all through DataService) ──
    if "prices" in sources and tickers:
        for t in tickers[:10]:
            try:
                bars = svc.get_prices(t, _today_minus(7), _today_str())
                if bars:
                    price_data[t] = {"latest": bars[-1]["close"], "change_pct": _calc_change(bars)}
                    search_details.append(f"ticker {t}: ¥{bars[-1]['close']}")
                else:
                    search_details.append(f"ticker {t}: no price data")
            except Exception as e:
                search_details.append(f"ticker {t}: price error ({e})")

    # ── Summarize ──
    if agent_cfg.get("enabled") and (news_articles or price_data):
        summary, findings, sentiment, alerts = _agent_summarize(
            task, news_articles, price_data, output_cfg.get("language", "zh")
        )
    else:
        summary = _rich_summary(task, news_articles, price_data, search_details)
        findings = [a.get("title", "")[:120] for a in news_articles[:5]]
        sentiment = "neutral"
        alerts = []

    elapsed_ms = int((time.time() - started_at) * 1000)

    return {
        "session_id": str(uuid.uuid4()),
        "summary": summary,
        "key_findings": findings,
        "sentiment": sentiment,
        "related_tickers": sorted(set(a.get("ticker", "") for a in news_articles[:20] if a.get("ticker")))[:10],
        "alerts": alerts,
        "raw_data": {
            "news_ids": [a["id"] for a in news_articles[:20]],
            "price_snapshots": price_data,
            "search_details": search_details,
            "elapsed_ms": elapsed_ms,
        },
        "generated_at": _now(),
    }


# ── Helpers ──────────────────────────────────────────────────


def _today_str() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _today_minus(days: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _calc_change(bars: list[dict]) -> float:
    if len(bars) < 2:
        return 0.0
    latest = bars[-1]["close"]
    prev = bars[-2]["close"]
    return ((latest - prev) / prev) * 100 if prev else 0.0


def _rich_summary(task: dict, news: list, prices: dict, details: list) -> str:
    """Generate a meaningful summary even with zero results."""
    name = task.get("name", "")
    count = len(news)
    price_count = len(prices)
    parts = [f"[{name}] 搜索完成"]

    if count > 0:
        parts.append(f"找到 {count} 条相关新闻")
        if price_count > 0:
            parts.append(f"获取 {price_count} 个标的价格")
    else:
        parts.append("未找到相关新闻（数据库和实时搜索均无结果）")
        parts.append("可尝试: 添加更多关键词、扩大搜索范围、或稍后重试")

    # Add search detail
    if details:
        detail_str = " | ".join(details[:4])
        parts.append(f"搜索记录: {detail_str}")

    return "。".join(parts)


def _agent_summarize(task: dict, news: list, prices: dict, lang: str):
    """Call LLM to summarize news and price data into structured findings."""
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
        import os

        api_base = os.getenv("OPENAI_API_BASE", "")
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=api_base if api_base else None,
            temperature=0.0,
            max_tokens=1024,
        )

        # Build compact context
        headlines = "\n".join(
            f"- [{a.get('ticker','')}] {a.get('title','')[:120]}"
            for a in news[:15]
        )
        price_str = "\n".join(
            f"- {t}: {d['latest']} ({d['change_pct']:+.2f}%)"
            for t, d in prices.items()
        )

        prompt_lang = "中文" if lang == "zh" else "English"
        sys_msg = SystemMessage(content=f"你是市场监控助手。用{prompt_lang}输出简洁的市场动态摘要。")
        user_msg = HumanMessage(content=f"""监控任务: {task.get('name', '')}
描述: {task.get('description', '')}

最新新闻标题:
{headlines or '无'}

价格变动:
{price_str or '无'}

请输出JSON（不要其他文字）:
{{"summary": "一句话摘要（≤100字）", "findings": ["发现1", "发现2", "发现3"], "sentiment": "positive/negative/mixed", "alerts": [{{"level": "info/warn", "message": "..."}}]}}""")

        resp = llm.invoke([sys_msg, user_msg])
        content = resp.content if hasattr(resp, "content") else str(resp)
        content = content.strip().lstrip("```json").rstrip("```").strip()

        result = json.loads(content)
        return (
            result.get("summary", _simple_summary(task, news, prices)),
            result.get("findings", []),
            result.get("sentiment", "neutral"),
            result.get("alerts", []),
        )
    except Exception as exc:
        logger.warning("Agent summarization failed: %s", exc)
        return _rich_summary(task, news, prices, []), [], "neutral", []
