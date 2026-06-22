"""MonitorEngine — core execution logic for monitor tasks.

Python automation + LLM as judgment node. No agent tool call loops.
LLM only used for: keyword expansion (on creation), optional news filtering,
and report generation.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from dotenv import load_dotenv

load_dotenv("properties.env")

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _llm(temp: float = 0.0, max_tok: int = 2048):
    """Create LLM instance from environment config."""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE") or None,
        temperature=temp,
        max_tokens=max_tok,
    )


# ── Keyword Expansion ────────────────────────────────────────


def expand_keywords(user_input: str, description: str = "") -> dict:
    """One-shot LLM call to expand a natural language description into
    search keywords and suggested tickers. Called ONCE when creating a monitor.

    Returns: {"keywords": [...], "tickers": [...]}
    """
    prompt = f"""用户想要监控一个主题/板块，请根据用户的描述，给出用于新闻搜索的关键词列表和相关的股票代码列表。

用户描述: {user_input}
{f'补充说明: {description}' if description else ''}

请以JSON格式输出，只输出JSON，不要其他内容：
{{
  "keywords": ["关键词1", "关键词2", ...],
  "tickers": ["TICKER1", "TICKER2", ...]
}}

要求：
- keywords: 5-10个搜索关键词，中英文都要有，覆盖不同角度
- tickers: 5-15个相关股票代码（如果用户描述的是具体股票则少一些）
- 美股用标准代码(如AAPL)，港股加.HK(如0700.HK)，A股加.SS或.SZ
"""

    try:
        llm = _llm(temp=0.0, max_tok=1024)
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        # Extract JSON from response (may be wrapped in ```json ... ```)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as exc:
        logger.warning("Keyword expansion failed: %s", exc)
        return {"keywords": [], "tickers": []}


# ── News Collection ──────────────────────────────────────────


def collect_news(monitor: dict, window_days: int = 7) -> list[dict]:
    """Fetch news for a monitor's keywords and tickers.

    Strategy (ordered by reliability):
    1. Yahoo Finance news for each ticker (most reliable — JSON API, no scraping)
    2. DataService.get_news() for each ticker (Google → AkShare → Yahoo fallback)
    3. Google News scraping for keywords (unreliable — may get CAPTCHA'd)
    4. Yahoo Finance for expanded_tickers if keywords are the main mode
    """
    from storage.store import ContextStore
    from dataflow.providers.YFinance import df_get_news_yahoo

    store = ContextStore()
    mode = monitor.get("mode", "keyword")
    targets = monitor.get("targets", {})
    keywords = targets.get("keywords", [])
    tickers = list(targets.get("tickers", []))
    monitor_id = monitor.get("id", "")

    # Also use expanded tickers for keyword monitors
    all_tickers = list(tickers)
    if not all_tickers:
        expanded = monitor.get("expanded_tickers", [])
        all_tickers = list(expanded) if expanded else []

    all_articles: list[dict] = []

    # ── 1. Yahoo Finance (primary — most reliable) ──
    for t in all_tickers[:15]:
        try:
            articles = df_get_news_yahoo(t, limit=10)
            for a in articles:
                a["_ticker"] = t
                a["_source"] = "yahoo"
            all_articles.extend(articles)
            if articles:
                logger.debug("Yahoo news for %s: %d articles", t, len(articles))
        except Exception as exc:
            logger.warning("Yahoo news for %s failed: %s", t, exc)

    # ── 2. DataService ticker news (Google → AkShare → Yahoo chain) ──
    if tickers:
        from dataflow.service import DataService
        svc = DataService()
        for t in tickers[:10]:
            try:
                articles = svc.get_news(t, window_days=window_days)
                for a in articles:
                    a["_ticker"] = t
                    a["_source"] = "dataservice"
                all_articles.extend(articles)
            except Exception as exc:
                logger.warning("DataService news for %s failed: %s", t, exc)

    # ── 3. Bing News RSS keywords (reliable XML API) ──
    if keywords:
        from dataflow.providers.news_bing import get_company_news_bing
        for kw in keywords[:5]:
            try:
                articles = get_company_news_bing(kw, days=window_days, max_items=10)
                for a in articles:
                    a["_search_keyword"] = kw
                    a["_source"] = "bing"
                all_articles.extend(articles)
                logger.debug("Bing keyword '%s': %d articles", kw, len(articles))
            except Exception as exc:
                logger.warning("Bing keyword '%s' failed: %s", kw, exc)

    # Dedup by URL
    seen = set()
    unique: list[dict] = []
    for a in all_articles:
        url = a.get("url", "") or a.get("link", "") or ""
        if url and url not in seen:
            seen.add(url)
            unique.append(a)

    # Store in monitor_news
    if monitor_id and unique:
        normalized = []
        for a in unique:
            normalized.append({
                "title": a.get("title", ""),
                "summary": a.get("summary", a.get("snippet", "")),
                "url": a.get("url", a.get("link", "")),
                "source_name": a.get("source_name", a.get("source", a.get("_source", ""))),
                "published_at": a.get("published_at", ""),
            })
        count = store.save_monitor_news(monitor_id, normalized)
        logger.info("Monitor %s: %d new articles saved (sources: %s)",
                    monitor_id, count,
                    set(a.get("_source", "?") for a in unique))

    return unique


# ── Price Collection ─────────────────────────────────────────


def collect_prices(tickers: list[str], lookback_days: int = 7) -> dict[str, dict]:
    """Get recent price data for a list of tickers.

    Returns: {TICKER: {latest_close, prev_close, change_pct, prices: [...]}}
    """
    from dataflow.service import DataService

    svc = DataService()
    start = (_today_dt() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end = _today_str()

    result = {}
    for t in tickers[:10]:
        try:
            bars = svc.get_prices(t, start, end)
            if bars and len(bars) >= 2:
                latest = bars[-1]
                prev = bars[-2]
                change_pct = ((latest["close"] - prev["close"]) / prev["close"]) * 100 if prev["close"] else 0
                result[t.upper()] = {
                    "latest_close": latest["close"],
                    "latest_date": latest["date"],
                    "prev_close": prev["close"],
                    "change_pct": round(change_pct, 2),
                    "prices": [{"date": b["date"], "close": b["close"]} for b in bars[-5:]],
                }
            elif bars:
                result[t.upper()] = {
                    "latest_close": bars[-1]["close"],
                    "latest_date": bars[-1]["date"],
                    "prices": [{"date": b["date"], "close": b["close"]} for b in bars[-5:]],
                }
        except Exception as exc:
            logger.warning("Price fetch for %s failed: %s", t, exc)
    return result


# ── News Filtering (optional LLM) ────────────────────────────


def filter_news(articles: list[dict], monitor: dict) -> list[dict]:
    """Optional LLM call to filter news by relevance to the monitor topic.
    If LLM is not available, returns all articles.
    """
    if not articles:
        return []

    if len(articles) <= 3:
        return articles  # Too few, don't bother filtering

    name = monitor.get("name", "")
    if not name:
        return articles

    # Build prompt with article list
    article_texts = []
    for i, a in enumerate(articles):
        title = a.get("title", "")[:200]
        article_texts.append(f"{i+1}. {title}")

    prompt = f"""用户监控主题: "{name}"
以下是抓取到的新闻标题列表，请判断每条新闻是否与该主题相关。

新闻列表:
{chr(10).join(article_texts)}

请以JSON数组输出，每个元素是该条新闻的相关性(0=无关, 1=弱相关, 2=直接相关):
例如: [2, 0, 1, 2, 0, ...]
只输出JSON数组，不要其他内容。"""

    try:
        llm = _llm()
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        scores = json.loads(text)
        if isinstance(scores, list) and len(scores) == len(articles):
            for i, s in enumerate(scores):
                articles[i]["relevance_score"] = s
            relevant = [a for a, s in zip(articles, scores) if s >= 1]
            logger.debug("News filter: %d → %d relevant", len(articles), len(relevant))
            return relevant
    except Exception as exc:
        logger.warning("News filtering failed: %s", exc)

    return articles


# ── Context Building ─────────────────────────────────────────


def build_context(monitor: dict, news: list[dict], prices: dict[str, dict]) -> str:
    """Build the context text for LLM report generation.
    Includes past reports summaries + new data.
    """
    from storage.store import ContextStore
    store = ContextStore()

    monitor_id = monitor.get("id", "")
    name = monitor.get("name", "")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [
        f"# Monitor: {name}",
        f"当前日期: {today}（所有分析请基于此日期，不要使用你训练数据中的日期）",
    ]

    # Past reports (all history, as summaries)
    try:
        past_reports = store.list_monitoring_reports(monitor_id, limit=10)
        if past_reports:
            parts.append("\n## 历史报告摘要\n")
            for r in past_reports[:5]:
                title = r.get("title", "") or r.get("summary", "")[:100]
                summary = r.get("summary_text", "") or r.get("summary", "")
                if title or summary:
                    parts.append(f"- [{r.get('generated_at', '')[:10]}] {title}")
                    if summary:
                        parts.append(f"  {summary[:300]}")
    except Exception as exc:
        logger.warning("Failed to load past reports: %s", exc)

    # New news
    if news:
        parts.append(f"\n## 最新新闻 ({len(news)}条)\n")
        for i, a in enumerate(news[:20], 1):
            title = a.get("title", "")
            source = a.get("source_name", "")
            date = (a.get("published_at", "") or "")[:10]
            parts.append(f"{i}. [{date}] {title} ({source})")

    # Price data
    if prices:
        parts.append("\n## 价格数据\n")
        for ticker, data in sorted(prices.items()):
            chg = data.get("change_pct")
            chg_str = f"{chg:+.2f}%" if chg is not None else ""
            parts.append(
                f"- **{ticker}**: ${data.get('latest_close', '?')} "
                f"({data.get('latest_date', '')}) 变动: {chg_str}"
            )

    return "\n".join(parts)


# ── Report Generation ────────────────────────────────────────


def generate_report(monitor: dict, context: str) -> dict:
    """Generate a structured report using LLM.

    Returns a dict with: title, summary, key_findings, sentiment, alerts,
    related_tickers, content (full markdown text).
    """
    name = monitor.get("name", "")
    mode = monitor.get("mode", "keyword")
    language = monitor.get("report_language", "zh")

    lang_instruction = "用中文输出" if language == "zh" else "Output in English"

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = f"""你是金融监控报告生成器。{lang_instruction}。

CRITICAL RULES（违反将导致报告无效）：
1. 当前真实日期是 {today}。报告中所有日期必须是2026年，绝不能出现2025年或更早的日期。
2. 只基于下面提供的真实数据进行总结，不要编造任何新闻或数据。
3. 如果下面没有新闻数据，在报告中明确写"本期未获取到相关新闻"。
4. 如果下面没有价格数据，在报告中明确写"本期未获取到价格数据"。

{context}

请基于以上信息，生成一份监控报告。以JSON格式输出：
{{
  "title": "报告标题（简洁明了）",
  "summary": "一段话总结本周/本次监控的核心发现 (100-200字)",
  "key_findings": ["发现1", "发现2", "发现3"],
  "sentiment": "positive/neutral/negative",
  "alerts": [{{"level": "info/warning/critical", "message": "告警内容"}}],
  "related_tickers": ["受影响的股票代码"],
  "trading_suggestion": "如果有明确的交易机会则给出建议，否则写'无明确建议'",
  "content": "完整的Markdown格式报告正文，包含：概述、重要新闻解读、价格分析、风险评估、下周关注要点"
}}

要求：
- key_findings 至少3条，每条20-50字
- 如果有重大价格变动或重要新闻，在alerts中标记
- content 要详细但不冗长，分节清晰
- 只输出JSON，不要```json```包裹"""

    try:
        llm = _llm(temp=0.3, max_tok=4096)
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        report = json.loads(text)
        report["monitor_id"] = monitor.get("id", "")
        report["generated_at"] = _now()
        report["report_type"] = "scheduled"
        return report
    except Exception as exc:
        logger.warning("Report generation failed: %s", exc)
        # Fallback: basic report
        return {
            "title": f"{name} 监控报告",
            "summary": f"本期监控共收集 {context.count(chr(10))} 条信息。",
            "key_findings": [],
            "sentiment": "neutral",
            "alerts": [],
            "related_tickers": [],
            "trading_suggestion": "",
            "content": f"## {name} 监控报告\n\n报告生成失败: {exc}\n\n原始数据:\n{context[:2000]}",
            "monitor_id": monitor.get("id", ""),
            "generated_at": _now(),
            "report_type": "scheduled",
        }


# ── Main Execute ─────────────────────────────────────────────


def execute(monitor_id: str) -> dict:
    """Run a full monitor cycle: collect → filter → build → report → store.

    This is the main entry point called by both the scheduler and the REST API.
    """
    from storage.store import ContextStore
    store = ContextStore()

    monitor = store.get_monitor(monitor_id)
    if not monitor:
        raise ValueError(f"Monitor {monitor_id} not found")

    name = monitor.get("name", "untitled")
    mode = monitor.get("mode", "keyword")
    targets = monitor.get("targets", {})
    keywords = targets.get("keywords", [])
    tickers = targets.get("tickers", [])
    sources = monitor.get("sources", ["news"])
    started_at = time.time()

    logger.info("Monitor [%s] starting: mode=%s, keywords=%d, tickers=%d",
                name, mode, len(keywords), len(tickers))

    # 1. Collect news
    news_articles: list[dict] = []
    if "news" in sources:
        news_articles = collect_news(monitor, window_days=7)

    # 2. Collect prices
    prices: dict[str, dict] = {}
    if "prices" in sources and tickers:
        prices = collect_prices(tickers, lookback_days=7)

    # 3. Filter news (optional LLM)
    filtered_news = filter_news(news_articles, monitor)

    # 4. Build context
    context = build_context(monitor, filtered_news, prices)

    # 5. Generate report
    report = generate_report(monitor, context)

    # 6. Add metadata
    report["monitor_id"] = monitor_id
    report["session_id"] = str(uuid.uuid4())
    report["raw_data"] = {
        "news_count": len(news_articles),
        "filtered_news_count": len(filtered_news),
        "price_tickers": list(prices.keys()),
        "elapsed_ms": int((time.time() - started_at) * 1000),
    }
    # Build collected news list BEFORE persisting
    collected = [
        {"title": a.get("title", ""), "url": a.get("url", ""), "source": a.get("source_name", "")}
        for a in news_articles[:30]
    ]
    report["collected_news"] = collected
    report["source_news_ids"] = [a.get("url", "") for a in filtered_news[:20]]
    report["raw_data"]["collected_news"] = collected
    report["context_report_ids"] = []
    report["summary_text"] = report.get("summary", "")
    report["content_text"] = report.get("content", "")

    # 7. Store
    try:
        rid = store.save_monitoring_report(report)
        report["id"] = rid
        store.touch_monitor_run(monitor_id)
        logger.info("Monitor [%s] done: report=%s, news=%d, elapsed=%dms",
                    name, rid, len(news_articles), report["raw_data"]["elapsed_ms"])
    except Exception as exc:
        logger.error("Failed to save report for %s: %s", monitor_id, exc)

    return report


def _today_dt() -> datetime:
    return datetime.now(timezone.utc)
