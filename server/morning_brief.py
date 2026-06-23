"""Morning Brief Engine — daily market intelligence.

Collects market data + 1000+ news articles → LLM generates structured brief.
Designed for reliability: all data sources are free, no API keys needed beyond LLM.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv("properties.env")

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── Market tickers ──────────────────────────────────────────

MARKET_TICKERS: dict[str, list[str]] = {
    "us_indices": ["SPY", "QQQ", "DIA", "IWM", "^VIX"],
    "asia": ["^HSI", "000001.SS", "^N225", "^KS11"],
    "commodities": ["CL=F", "GC=F", "HG=F"],
    "fixed_income": ["^TNX", "^FVX"],
    "fx": ["DX-Y.NYB", "USDCNY=X", "USDHKD=X", "USDJPY=X"],
    "crypto": ["BTC-USD", "ETH-USD"],
    "sectors": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY"],
}


# ── Data Collection ─────────────────────────────────────────


def collect_market_data() -> dict:
    """Fetch price snapshots for all market tickers concurrently.

    Returns: {category: {ticker: {name, price, change_pct, currency}}}
    """
    import yfinance as yf

    all_tickers: list[tuple[str, str]] = []
    for category, tickers in MARKET_TICKERS.items():
        for t in tickers:
            all_tickers.append((category, t))

    results: dict[str, dict] = {cat: {} for cat in MARKET_TICKERS}

    def _fetch(cat: str, ticker: str):
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            hist = t.history(period="2d")
            name = info.get("shortName") or info.get("longName") or ticker
            currency = info.get("currency", "USD")
            if hist.empty:
                price = info.get("regularMarketPrice")
                prev = info.get("previousClose")
            else:
                price = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else price
            change_pct = ((price - prev) / prev * 100) if prev and price else None
            return cat, ticker, {
                "name": name,
                "price": round(price, 2) if price else None,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "currency": currency,
            }
        except Exception as exc:
            logger.debug("Market data failed for %s: %s", ticker, exc)
            return cat, ticker, {"name": ticker, "price": None, "change_pct": None, "currency": "USD"}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_fetch, cat, t) for cat, t in all_tickers]
        for f in as_completed(futures):
            cat, ticker, data = f.result()
            results[cat][ticker] = data

    return results


def collect_news(hours: int = 0) -> list[dict]:
    """Fetch news articles across 50 categories, deduplicate.

    Args:
        hours: If > 0, only include articles from the last N hours (e.g. 24).
    """
    from dataflow.providers.news_rss import fetch_all_news, dedup_articles

    categorized = fetch_all_news(hours=hours)
    return dedup_articles(categorized)


# ── Brief Generation ────────────────────────────────────────


def _build_prompt(market_data: dict, articles: list[dict]) -> tuple[str, list[dict]]:
    """Build LLM prompt from structured market data + numbered news articles.

    Returns (prompt, numbered_articles) — numbered_articles is the top 50
    articles with index numbers for citation.
    """
    today = _today_str()

    # Pick top articles (diverse categories, up to 10 per category)
    categorized: dict[str, list[dict]] = {}
    for a in articles:
        cat = a.get("_category", "other")
        if cat not in categorized:
            categorized[cat] = []
        if len(categorized[cat]) < 10:
            categorized[cat].append(a)

    # Flatten and number
    numbered: list[dict] = []
    idx = 1
    for cat_articles in categorized.values():
        for a in cat_articles:
            numbered.append({**a, "_idx": idx})
            idx += 1

    # Market summary
    market_lines = [f"# 市场数据 ({today})"]
    labels = {
        "us_indices": "美股指数", "asia": "亚洲市场",
        "commodities": "大宗商品", "fixed_income": "固收",
        "fx": "外汇", "crypto": "加密货币", "sectors": "行业板块",
    }
    for cat, tickers in market_data.items():
        label = labels.get(cat, cat)
        market_lines.append(f"\n## {label}")
        for ticker, d in tickers.items():
            if d["price"] is not None:
                chg = f"{d['change_pct']:+.2f}%" if d["change_pct"] is not None else ""
                market_lines.append(f"- {d['name']} ({ticker}): {d['price']} {chg}")

    # Numbered news list
    news_lines = ["\n# 新闻来源 (引用时请标注编号 [N])"]
    for a in numbered:
        cat = a.get("_category", "")
        news_lines.append(
            f"[{a['_idx']}] [{cat}] {a['title']} "
            f"({a.get('source_name', '')}) — {a.get('published_at', '')[:10]}"
        )

    prompt = f"""你是资深全球市场分析师，请基于以下真实数据生成一份全面的中文晨间市场简报。

━━━━━━ FORMAT EXAMPLE（严格遵循此格式）━━━━━━

## 隔夜市场综述

美股三大指数收盘涨跌互现。标普500涨0.3%至5960点，纳指受科技股拖累跌0.5% [3]。道指微涨0.1%。欧洲Stoxx 600涨0.8%。亚洲早盘日经225高开0.6% [22]。

## 今日焦点

1. **美联储维持利率不变**：鲍威尔强调通胀需进一步观察，市场预期9月首次降息 [1][8]
2. **Nvidia财报超预期**：Q2营收$32.5B同比增122%，但Q3指引偏保守，盘后跌3% [12]
3. **原油重返$80**：布伦特原油涨3.2%，OPEC+或延续减产 [15]

## 板块分析

科技XLK跌0.8%受Nvidia拖累 [12]。能源XLE涨2.1%受油价提振 [15]。金融XLF涨0.5% [7]。

## 宏观要闻

美联储第七次维持利率不变 [1]。美国5月CPI同比3.3%略低于预期 [8]。欧央行暗示6月可能降息 [22]。

## 中国市场

上证指数涨0.8%至4163点 [35]。央行维持逆回购操作，人民币中间价6.77 [36]。

## 加密货币

比特币维持$64000附近 [48]。以太坊站上$3500 [48]。

## 今日关注

美国初请失业金人数（20:30）、美联储理事讲话（22:00）、Nvidia电话会（盘后）。

━━━━━━ RULES ━━━━━━
1. 当前日期 {today}，只能使用下面提供的数据，不得编造
2. **content 必须用 ## 标题分节，每个 ## 独占一行，节间空一行**
3. **每个板块至少 5-8 句**，用自然段落详述，必须包含具体数字（涨跌幅、价格、百分比）
4. **尽可能多地引用新闻**，至少引用 15-25 条不同的新闻编号 [N]
5. **提到任何新闻必须在句末标注 [N]**，可合并如 [3][7]
6. **content 总字数不少于 1500 字**，如果数据不足则写明"暂无相关数据"
7. 不要偷懒写短报告——你有数百条新闻可参考，充分利用它们

{chr(10).join(market_lines)}

{chr(10).join(news_lines)}

输出纯JSON（不要```包裹）：
{{"title": "晨间简报标题", "summary": "100-150字摘要", "content": "(按上面格式)", "key_events": ["事件1","事件2","事件3"], "tickers_covered": ["TICKER"]}}"""

    return prompt, numbered


def generate_brief(market_data: dict, articles: list[dict]) -> dict:
    """Call LLM to generate structured morning brief."""
    prompt, numbered_articles = _build_prompt(market_data, articles)

    # Build source list for storage and frontend display
    sources = []
    for a in numbered_articles:
        sources.append({
            "idx": a["_idx"],
            "title": a.get("title", ""),
            "url": a.get("url", ""),
            "source": a.get("source_name", ""),
            "category": a.get("_category", ""),
            "published_at": a.get("published_at", ""),
        })

    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE") or None,
            temperature=0.3,
            max_tokens=8192,
        )
        result = llm.invoke(prompt)
        text = result.content if hasattr(result, "content") else str(result)
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        brief = json.loads(text)
    except Exception as exc:
        logger.warning("LLM brief generation failed: %s", exc)
        brief = {
            "title": f"晨间简报 — {_today_str()}",
            "summary": f"市场数据已收集（{len(articles)}条新闻），但LLM生成失败",
            "content": f"## 市场数据\n\nLLM generation error: {exc}\n\n共收集 {len(articles)} 条新闻，覆盖 {len(market_data)} 个类别。",
            "key_events": [],
            "tickers_covered": [],
        }

    brief["generated_at"] = _now()
    brief["type"] = "morning_brief"
    brief["sources"] = sources  # Numbered articles cited in prompt
    brief["all_articles"] = [
        {"title": a.get("title", ""), "url": a.get("url", ""),
         "source": a.get("source_name", ""), "category": a.get("_category", ""),
         "published_at": a.get("published_at", ""), "summary": a.get("summary", "")}
        for a in articles[:500]  # All collected articles for frontend display
    ]
    return brief


# ── Main Entry Point ────────────────────────────────────────


def run(hours: int = 0, progress_queue=None) -> dict:
    """Full morning brief pipeline: collect → generate → store.

    Args:
        hours: If > 0, only fetch news from last N hours (e.g. 24).
        progress_queue: Optional queue.Queue for SSE streaming progress updates.
    """
    started = time.time()

    def _progress(stage: str, status: str, detail: str = ""):
        logger.info("MorningBrief [%s]: %s — %s", stage, status, detail)
        if progress_queue:
            progress_queue.put(("progress", {"stage": stage, "status": status, "detail": detail}))

    _progress("start", "initializing", f"hours={hours}")

    # 1. Market data
    _progress("market", "collecting", "Fetching 25 tickers...")
    market_data = collect_market_data()
    t_count = sum(len(v) for v in market_data.values())
    _progress("market", "done", f"{t_count} tickers fetched")

    # 2. News collection
    _progress("news", "collecting", "Fetching 52 RSS queries...")
    from dataflow.providers.news_rss import fetch_all_news, dedup_articles
    categorized = fetch_all_news(hours=hours)
    raw_total = sum(len(v) for v in categorized.values())
    _progress("news", "dedup", f"{raw_total} raw → deduplicating...")
    articles = dedup_articles(categorized)
    _progress("news", "done", f"{len(articles)} unique articles from {len(categorized)} categories")

    elapsed_collect = time.time() - started
    logger.info("MorningBrief: %d tickers, %d articles in %.1fs",
                t_count, len(articles), elapsed_collect)

    # 3. Generate brief
    _progress("llm", "generating", "Building prompt and calling LLM...")
    brief = generate_brief(market_data, articles)
    _progress("llm", "done", f"Brief generated ({len(brief.get('content', ''))} chars)")

    brief["market_data"] = market_data
    brief["news_count"] = len(articles)
    brief["news_sources"] = brief.get("sources", [])
    brief["elapsed_s"] = round(time.time() - started, 1)

    # 4. Store
    _progress("store", "saving", "Persisting to database...")
    try:
        from storage.store import ContextStore
        store = ContextStore()
        rid = store.save_daily_brief(brief)
        brief["id"] = rid
        _progress("store", "done", f"Saved {rid[:16]}...")
        logger.info("MorningBrief: saved %s (elapsed %.1fs)", rid, brief["elapsed_s"])
    except Exception as exc:
        _progress("store", "error", str(exc)[:100])
        logger.error("MorningBrief: save failed: %s", exc)

    _progress("done", "complete", f"{len(articles)} articles, {brief['elapsed_s']}s")
    return brief
