"""Daily Insights REST endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Empty, Queue
from threading import Thread

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from server.llm_defaults import DEFAULT_QUICK_THINK_MODEL
from storage import get_store

router = APIRouter(tags=["insights"])
logger = logging.getLogger(__name__)


def _sse_event(event: str, data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


# ── CRUD ──


@router.get("/insights")
async def list_insights(limit: int = Query(20, ge=1, le=100)):
    briefs = get_store().list_daily_briefs(limit=limit)
    return {"insights": briefs, "total": len(briefs)}


@router.get("/insights/latest")
async def latest_insight():
    brief = get_store().get_latest_brief()
    return {"insight": brief} if brief else {"insight": None}


# ── Watchlist Summary ──


@router.post("/insights/watchlist-summary")
async def watchlist_summary(data: dict):
    """Generate a short summary of news articles. Body: {ticker?, articles}"""
    articles = data.get("articles", [])
    ticker = data.get("ticker", "")
    if not articles:
        return {"summary": "No articles to summarize."}

    import os
    from langchain_openai import ChatOpenAI

    titles = "\n".join(
        f"- [{a.get('ticker', '')}] {a.get('title', '')} ({a.get('source', '')}, {a.get('published_at', '')[:10]})"
        for a in articles[:30]
    )
    scope = f"关于 {ticker} 的" if ticker else "关于多个标的的"
    prompt = f"""你是市场分析师，请{scope}以下新闻标题做一个简洁总结（100-200字中文）。
1. 概括关键信号和趋势，不要逐条复述
2. 如有冲突信号请指出 3. 用自然段落 4. 只基于提供的数据

{titles}

只输出总结文本。"""

    try:
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", DEFAULT_QUICK_THINK_MODEL),
            api_key=lambda: os.getenv("OPENAI_API_KEY") or "",
            base_url=os.getenv("OPENAI_API_BASE") or None,
            temperature=0.3,
        )
        result = llm.invoke(prompt)
        raw_content = result.content if hasattr(result, "content") else str(result)
        text = (
            raw_content
            if isinstance(raw_content, str)
            else json.dumps(raw_content, ensure_ascii=False)
        )
        return {"summary": text.strip()}
    except Exception as exc:
        return {"summary": f"Summary failed: {str(exc)[:200]}"}


# ── Watchlist News (must be before {insight_id} to avoid route conflict) ──


@router.get("/insights/watchlist-news")
async def watchlist_news(
    watchlist_id: str = Query(...),
    hours: int = Query(168, ge=1, le=720),
):
    """Fetch news for all tickers in a watchlist using Yahoo + Google RSS + Bing."""
    store = get_store()
    wl = (
        store._system_db()
        .execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,))
        .fetchone()
    )
    if wl is None:
        raise HTTPException(404, "Watchlist not found")

    import json as _json

    tickers = _json.loads(wl["tickers_json"])
    if not tickers:
        return {"tickers": [], "articles": [], "total": 0}

    from dataflow.providers.YFinance import df_get_news_yahoo
    from dataflow.providers.news_rss import fetch_google_news_rss
    from dataflow.providers.news_bing import get_company_news_bing

    all_articles: list[dict] = []

    def _fetch(ticker: str):
        results: list[dict] = []
        try:
            for a in df_get_news_yahoo(ticker, limit=5):
                a["_ticker"] = ticker
                a["_source"] = "Yahoo"
                results.append(a)
        except Exception:
            pass
        try:
            for a in fetch_google_news_rss(f"{ticker} stock", hours=hours):
                a["_ticker"] = ticker
                a["_source"] = "Google"
                results.append(a)
        except Exception:
            pass
        try:
            days = max(1, hours // 24)
            for a in get_company_news_bing(ticker, days=days, max_items=5):
                a["_ticker"] = ticker
                a["_source"] = "Bing"
                results.append(a)
        except Exception:
            pass
        return results

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch, t): t for t in tickers[:30]}
        for f in as_completed(futures):
            all_articles.extend(f.result())

    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_articles:
        url = a.get("url", a.get("link", ""))
        if url and url not in seen:
            seen.add(url)
            unique.append(
                {
                    "title": a.get("title", ""),
                    "url": url,
                    "source": a.get("_source", a.get("source_name", "")),
                    "ticker": a.get("_ticker", ""),
                    "published_at": a.get("published_at", ""),
                    "summary": a.get("summary", a.get("snippet", "")),
                }
            )

    unique.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    return {"tickers": tickers, "articles": unique, "total": len(unique)}


@router.get("/insights/{insight_id}")
async def get_insight(insight_id: str):
    brief = get_store().get_daily_brief(insight_id)
    if brief is None:
        raise HTTPException(404, "Brief not found")
    return brief


@router.delete("/insights/{insight_id}")
async def delete_insight(insight_id: str):
    deleted = get_store().delete_daily_brief(insight_id)
    if not deleted:
        raise HTTPException(404, "Brief not found")
    return {"ok": True}


# ── Generation (SSE) ──


@router.post("/insights/generate")
async def generate_insight(hours: int = Query(0)):
    """SSE streaming brief generation with real-time progress."""

    async def event_stream():
        queue: Queue = Queue()

        def _worker():
            try:
                from server.morning_brief import run

                result = run(hours=hours, progress_queue=queue)
                queue.put(("done", result))
            except Exception as exc:
                queue.put(("error", str(exc)))

        thread = Thread(target=_worker, daemon=True)
        thread.start()

        loop = asyncio.get_event_loop()

        while True:
            try:
                msg_type, payload = await loop.run_in_executor(
                    None, lambda: queue.get(timeout=300)
                )
            except Empty:
                yield _sse_event("error", {"message": "Timeout after 5 minutes"})
                break

            if msg_type == "done":
                yield _sse_event("done", {"ok": True, **payload})
                break

            if msg_type == "error":
                yield _sse_event("error", {"message": str(payload)[:500]})
                break

            if msg_type == "progress":
                yield _sse_event("progress", payload)
                continue

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
