"""Financial data tools for the agent.

Reuses existing DataService methods. Wrapped as BaseTool subclasses for
auto-registration with the agent's ToolRegistry.
"""

from __future__ import annotations

import json
import logging

from .base import BaseTool, ToolMeta, emit_progress

logger = logging.getLogger(__name__)


class GetPriceTool(BaseTool):
    meta = ToolMeta(
        name="get_price",
        description="获取股票的价格数据(OHLCV)。参数: ticker(股票代码), days(天数,默认30)。返回最近N天的开盘/最高/最低/收盘/成交量。",
        category="financial",
        timeout=15,
    )

    def execute(self, ticker: str = "", days: int | str = 30) -> str:
        try:
            days = int(days)
        except (ValueError, TypeError):
            days = 30
        emit_progress("fetching", message=f"Getting price data for {ticker}...")
        from dataflow.service import DataService
        from datetime import datetime, timezone, timedelta

        svc = DataService()
        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=int(days))).strftime("%Y-%m-%d")
        bars = svc.get_prices(ticker.upper(), start, end)

        if not bars:
            return self._error(f"No price data found for {ticker}")

        latest = bars[-1]
        prev = bars[-2] if len(bars) > 1 else latest
        change_pct = ((latest["close"] - prev["close"]) / prev["close"] * 100) if prev["close"] else 0

        emit_progress("done", message=f"Got {len(bars)} bars for {ticker}")
        return self._ok({
            "ticker": ticker.upper(),
            "bars_count": len(bars),
            "latest": {
                "date": latest["date"], "open": latest["open"],
                "high": latest["high"], "low": latest["low"],
                "close": latest["close"], "volume": latest["volume"],
            },
            "change_pct": round(change_pct, 2),
            "recent": [
                {"date": b["date"], "close": b["close"]} for b in bars[-5:]
            ],
        })


class GetIndicatorsTool(BaseTool):
    meta = ToolMeta(
        name="get_indicators",
        description="获取技术指标(RSI/MACD/SMA/ATR)。参数: ticker(股票代码)。返回当前指标值和信号。",
        category="financial",
        timeout=15,
    )

    def execute(self, ticker: str = "") -> str:
        emit_progress("computing", message=f"Computing indicators for {ticker}...")
        from dataflow.service import DataService

        svc = DataService()
        result = svc.get_indicators(ticker.upper())
        if not result:
            return self._error(f"No indicator data for {ticker}")

        macd = result.get("macd", {}) or {}
        ma = result.get("ma", {}) or {}
        return self._ok({
            "ticker": ticker.upper(),
            "rsi14": round(float(result.get("rsi14", 0)), 1) if result.get("rsi14") else None,
            "macd_signal": "bullish" if macd.get("hist", 0) > 0 else "bearish",
            "sma20": round(float(ma.get("sma20", 0)), 2) if ma.get("sma20") else None,
            "sma50": round(float(ma.get("sma50", 0)), 2) if ma.get("sma50") else None,
            "atr14": round(float(result.get("atr20", 0)), 2) if result.get("atr20") else None,
        })


class GetNewsTool(BaseTool):
    meta = ToolMeta(
        name="get_news",
        description="获取股票或关键词的最新新闻。参数: ticker(股票代码或关键词), days(天数,默认7)。返回新闻列表。",
        category="financial",
        timeout=20,
    )

    def execute(self, ticker: str = "", days: int = 7) -> str:
        emit_progress("fetching", message=f"Fetching news for {ticker}...")
        from dataflow.service import DataService

        svc = DataService()
        articles = svc.get_news(ticker.upper(), window_days=days)
        if not articles:
            return self._ok({"ticker": ticker.upper(), "count": 0, "articles": []})

        return self._ok({
            "ticker": ticker.upper(),
            "count": len(articles),
            "articles": [
                {"title": a.get("title", ""), "source": a.get("source_name", ""),
                 "url": a.get("url", ""), "published_at": a.get("published_at", "")}
                for a in articles[:10]
            ],
        })


class GetFundamentalsTool(BaseTool):
    meta = ToolMeta(
        name="get_fundamentals",
        description="获取股票基本面数据(PE/PB/ROE/市值等)。参数: ticker(股票代码)。",
        category="financial",
        timeout=20,
    )

    def execute(self, ticker: str = "") -> str:
        emit_progress("fetching", message=f"Fetching fundamentals for {ticker}...")
        from dataflow.service import DataService

        svc = DataService()
        data = svc.get_fundamentals(ticker.upper())
        if not data:
            return self._error(f"No fundamentals data for {ticker}")
        return self._ok(data)


class WebSearchTool(BaseTool):
    meta = ToolMeta(
        name="web_search",
        description="搜索互联网获取最新信息。参数: query(搜索关键词)。返回搜索结果列表。",
        category="data",
        timeout=15,
    )

    def execute(self, query: str = "") -> str:
        emit_progress("searching", message=f"Searching: {query}...")
        try:
            from dataflow.providers.news_rss import fetch_google_news_rss
            articles = fetch_google_news_rss(query)
            return self._ok({
                "query": query, "count": len(articles),
                "results": [
                    {"title": a.get("title", ""), "source": a.get("source_name", ""),
                     "url": a.get("url", ""), "published_at": a.get("published_at", "")}
                    for a in articles[:8]
                ],
            })
        except Exception as exc:
            return self._error(str(exc))


class SearchSymbolTool(BaseTool):
    meta = ToolMeta(
        name="search_symbol",
        description="搜索股票代码或公司名称。参数: query(搜索词,支持中英文)。返回匹配的股票列表。",
        category="financial",
        timeout=10,
    )

    def execute(self, query: str = "") -> str:
        import yfinance as yf
        try:
            t = yf.Ticker(query.upper())
            info = t.info or {}
            name = info.get("shortName") or info.get("longName") or query.upper()
            return self._ok({
                "ticker": query.upper(),
                "name": name,
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", ""),
                "market_cap": info.get("marketCap"),
            })
        except Exception:
            return self._error(f"Could not find symbol: {query}")


class GetMetaTool(BaseTool):
    meta = ToolMeta(name="get_meta",
        description="获取股票基本信息(名称/行业/市值/交易所/货币)。参数: ticker。",
        category="financial", timeout=10)

    def execute(self, ticker: str = "") -> str:
        from dataflow.service import DataService
        svc = DataService()
        meta = svc.get_meta(ticker.upper())
        return self._ok(meta) if meta else self._error(f"No meta for {ticker}")


class GetSentimentTool(BaseTool):
    meta = ToolMeta(name="get_sentiment",
        description="获取新闻情绪评分(-1到1,正=看多,负=看空)。参数: ticker, days(默认7)。",
        category="financial", timeout=15)

    def execute(self, ticker: str = "", days: int | str = 7) -> str:
        try: days = int(days)
        except: days = 7
        from dataflow.providers.sentiment import df_get_sentiment
        r = df_get_sentiment(ticker.upper(), window_days=days)
        return self._ok(r)


class GetMacroCalendarTool(BaseTool):
    meta = ToolMeta(name="get_macro_calendar",
        description="获取全球经济日历(CPI/FOMC/非农等)。参数: days(默认7)。",
        category="financial", timeout=15)

    def execute(self, days: int | str = 7) -> str:
        try: days = int(days)
        except: days = 7
        from dataflow.service import DataService
        svc = DataService()
        events = svc.df_get_macro_calendar(window_days=days)
        return self._ok({"events": events, "count": len(events)})


class SearchNewsTool(BaseTool):
    meta = ToolMeta(name="search_news",
        description="全文搜索历史新闻(FTS5)。参数: query(关键词), ticker(可选), limit(默认20)。",
        category="financial", timeout=5)

    def execute(self, query: str = "", ticker: str = "", limit: int | str = 20) -> str:
        try: limit = int(limit)
        except: limit = 20
        from dataflow.service import DataService
        svc = DataService()
        results = svc.search_news(query, ticker=ticker.upper() if ticker else None, limit=limit)
        return self._ok({"query": query, "count": len(results), "results": results[:limit]})


class RunAnalysisTool(BaseTool):
    meta = ToolMeta(name="run_analysis",
        description="运行完整的多Agent分析流程(技术面/新闻/基本面/风险/PM综合)。参数: ticker, date(可选)。耗时较长(30-60秒)。",
        category="research", timeout=120, is_readonly=True)

    def execute(self, ticker: str = "", date: str = "") -> str:
        emit_progress("analyzing", message=f"Running full analysis on {ticker}...")
        import time as _time
        from agentgraph.orchestrator import IntelliFin_Assistant
        assistant = IntelliFin_Assistant()
        from datetime import datetime, timezone
        d = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        result = assistant.run(ticker.upper(), date=d)
        return self._ok({
            "ticker": ticker.upper(),
            "action": result.get("Action", "HOLD"),
            "target_position_pct": result.get("Target_position_pct", 0),
            "pm_report": result.get("PM_report", "")[:2000],
            "market_report": str(result.get("market_report", ""))[:500],
            "news_report": str(result.get("news_report", ""))[:500],
            "fundamental_report": str(result.get("fundamental_report", ""))[:500],
            "risk_report": str(result.get("risk_report", ""))[:500],
        })


class GenerateBriefTool(BaseTool):
    meta = ToolMeta(name="generate_brief",
        description="生成晨间市场简报(50+新闻源,覆盖全球市场)。参数: hours(默认24,只包含最近N小时新闻)。耗时较长(30-60秒)。",
        category="research", timeout=120, is_readonly=True)

    def execute(self, hours: int | str = 24) -> str:
        try: hours = int(hours)
        except: hours = 24
        emit_progress("generating", message=f"Generating market brief (last {hours}h)...")
        from server.morning_brief import run
        brief = run(hours=hours)
        return self._ok({
            "title": brief.get("title", ""),
            "summary": brief.get("summary", ""),
            "content": brief.get("content", "")[:3000],
            "news_count": brief.get("news_count", 0),
            "elapsed_s": brief.get("elapsed_s", 0),
        })


class LoadSkillTool(BaseTool):
    meta = ToolMeta(name="load_skill",
        description="加载指定技能/策略的完整文档。参数: name(技能名称)。用于获取详细方法论、分析框架或交易策略。",
        category="workspace", timeout=5)

    def execute(self, name: str = "") -> str:
        from skills.loader import SkillLoader
        import os
        skills_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "skills")
        loader = SkillLoader(skills_dir)
        loader.discover()
        skill = loader.get(name)
        if not skill:
            # Try partial match
            for s in loader.skills.values():
                if name.lower() in s.name.lower():
                    skill = s
                    break
        if not skill:
            names = ", ".join(sorted(loader.skills.keys())[:30])
            return self._error(f"Skill '{name}' not found. Available: {names}...")
        return self._ok({
            "name": skill.name,
            "category": skill.category,
            "description": skill.description,
            "content": skill.prompt_template[:3000],
        })


class WebFetchTool(BaseTool):
    meta = ToolMeta(name="web_fetch",
        description="抓取网页全文内容(转为Markdown)。参数: url(网页地址)。",
        category="data", timeout=20)

    def execute(self, url: str = "") -> str:
        emit_progress("fetching", message=f"Fetching {url[:60]}...")
        try:
            import requests
            resp = requests.get(f"https://r.jina.ai/{url}",
                headers={"Accept": "text/markdown", "User-Agent": "Mozilla/5.0"},
                timeout=15)
            resp.raise_for_status()
            text = resp.text[:5000]
            return self._ok({"url": url, "content": text, "length": len(text)})
        except Exception as exc:
            return self._error(str(exc))
