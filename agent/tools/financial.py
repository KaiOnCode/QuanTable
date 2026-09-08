"""Financial data tools for the agent.

Reuses existing DataService methods. Wrapped as BaseTool subclasses for
auto-registration with the agent's ToolRegistry.
"""

# pyright: reportIncompatibleMethodOverride=false
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .base import BaseTool, ToolMeta, emit_progress

logger = logging.getLogger(__name__)


def _data_service():
    from agent.run_context import current_agent_run_context

    context = current_agent_run_context()
    if context is not None:
        return context.data_service
    from dataflow.service import DataService

    return DataService()


def _data_cutoff() -> datetime:
    from agent.run_context import current_agent_run_context

    context = current_agent_run_context()
    if context is None:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(context.as_of.replace("Z", "+00:00"))


class GetPriceTool(BaseTool):
    meta = ToolMeta(
        name="get_price",
        description="USE WHEN: user asks for stock price, quote, OHLCV, 股价, 行情. 获取股票历史价格数据。参数: ticker(股票代码,必填), days(天数,默认30,1Y=365,2Y=730,5Y=1825,MAX=3650)。返回每日开盘/最高/最低/收盘/成交量。",
        category="financial",
        timeout=20,
        repeatable=False,
        input_schema={
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, NVDA, 600519)",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days of history (default 30, max 3650)",
                },
            },
            "required": ["ticker"],
        },
    )

    def prompt(self) -> str:
        return (
            "Get current stock price and recent OHLCV data for a ticker.\n"
            "USE WHEN: user asks for a stock price, quote, 股价, 行情, or recent trading data.\n"
            "NOT for: technical indicators (use get_indicators), fundamentals (use get_fundamentals).\n"
            "Parameters: ticker (required) — stock symbol like AAPL, TSLA, 0700.HK.\n"
            "  days (optional, default 30) — days of history. 1Y=365, 2Y=730, MAX=3650.\n"
            "Returns: current price, change%, day range, volume, and recent OHLCV bars.\n"
            "ONE call per ticker is sufficient. Do not call again for the same ticker."
        )

    def execute(self, ticker: str = "", days: int | str = 30) -> str:
        try:
            days = int(days)
        except (ValueError, TypeError):
            days = 30
        emit_progress("fetching", message=f"Getting price data for {ticker}...")
        svc = _data_service()
        cutoff = _data_cutoff()
        end = cutoff.strftime("%Y-%m-%d")
        start = (cutoff - timedelta(days=int(days))).strftime("%Y-%m-%d")
        bars = svc.get_prices(ticker.upper(), start, end)

        if not bars:
            return self._error(f"No price data found for {ticker}")

        latest = bars[-1]
        prev = bars[-2] if len(bars) > 1 else latest
        change_pct = (
            ((latest["close"] - prev["close"]) / prev["close"] * 100)
            if prev["close"]
            else 0
        )

        emit_progress("done", message=f"Got {len(bars)} bars for {ticker}")
        return self._ok(
            {
                "ticker": ticker.upper(),
                "bars_count": len(bars),
                "latest": {
                    "date": latest["date"],
                    "open": latest["open"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "close": latest["close"],
                    "volume": latest["volume"],
                },
                "change_pct": round(change_pct, 2),
                "recent": [{"date": b["date"], "close": b["close"]} for b in bars[-5:]],
                "bars": [{"date": b["date"], "close": b["close"]} for b in bars[-100:]],
            }
        )


class GetIndicatorsTool(BaseTool):
    meta = ToolMeta(
        name="get_indicators",
        description="USE WHEN: user asks for RSI, MACD, moving average, 均线, technical indicators. 获取技术指标：RSI(相对强弱)、MACD、SMA(简单移动平均线/均线/MA)、ATR(真实波幅)。参数: ticker(股票代码,必填)。返回当前值和多空信号。",
        category="financial",
        timeout=15,
        repeatable=False,
        input_schema={
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker (required)"}
            },
            "required": ["ticker"],
        },
    )

    def prompt(self) -> str:
        return (
            "Get technical indicators: RSI, MACD, SMA, ATR for a ticker.\n"
            "USE WHEN: user asks for RSI, MACD, moving average, 均线, MA, technical indicators, 技术指标.\n"
            "NOT for: stock prices (use get_price), fundamentals (use get_fundamentals).\n"
            "Parameters: ticker (required) — stock symbol.\n"
            "Returns: RSI-14 value, MACD signal (bullish/bearish), SMA-20, SMA-50, ATR-14.\n"
            "ONE call per ticker is sufficient."
        )

    def execute(self, ticker: str = "") -> str:
        emit_progress("computing", message=f"Computing indicators for {ticker}...")
        svc = _data_service()
        result = svc.get_indicators(ticker.upper())
        if not result:
            return self._error(f"No indicator data for {ticker}")

        macd = result.get("macd", {}) or {}
        ma = result.get("ma", {}) or {}
        return self._ok(
            {
                "ticker": ticker.upper(),
                "rsi14": round(float(result.get("rsi14", 0)), 1)
                if result.get("rsi14")
                else None,
                "macd_signal": "bullish" if macd.get("hist", 0) > 0 else "bearish",
                "sma20": round(float(ma.get("sma20", 0)), 2)
                if ma.get("sma20")
                else None,
                "sma50": round(float(ma.get("sma50", 0)), 2)
                if ma.get("sma50")
                else None,
                "atr14": round(float(result.get("atr20", 0)), 2)
                if result.get("atr20")
                else None,
            }
        )


class GetNewsTool(BaseTool):
    meta = ToolMeta(
        name="get_news",
        description="USE WHEN: user asks for latest news about a stock or topic. 获取股票或关键词的最新新闻。参数: ticker(股票代码或关键词), days(天数,默认7)。返回新闻列表。",
        category="financial",
        timeout=20,
        input_schema={
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker or keyword (required)",
                },
                "days": {
                    "type": "integer",
                    "description": "Days of news to fetch (default 7)",
                },
            },
            "required": ["ticker"],
        },
    )

    def prompt(self) -> str:
        return (
            "Get latest news for a stock ticker or keyword.\n"
            "USE WHEN: user asks for latest news, 新闻, recent developments about a stock.\n"
            "NOT for: general internet search (use web_search), stock prices (use get_price).\n"
            "Parameters: ticker (required) — stock symbol or keyword.\n"
            "  days (optional, default 7) — how many days of news to fetch.\n"
            "Returns: list of articles with title, source, URL, and publish date.\n"
            "ONE call per ticker is sufficient."
        )

    def execute(self, ticker: str = "", days: int | str = 7) -> str:
        try:
            days = int(days)
        except Exception:
            days = 7
        emit_progress("fetching", message=f"Fetching news for {ticker}...")
        svc = _data_service()
        articles = svc.get_news(ticker.upper(), window_days=days)
        if not articles:
            return self._ok({"ticker": ticker.upper(), "count": 0, "articles": []})

        return self._ok(
            {
                "ticker": ticker.upper(),
                "count": len(articles),
                "articles": [
                    {
                        "title": a.get("title", ""),
                        "source": a.get("source_name", ""),
                        "url": a.get("url", ""),
                        "published_at": a.get("published_at", ""),
                    }
                    for a in articles[:10]
                ],
            }
        )


class GetFundamentalsTool(BaseTool):
    meta = ToolMeta(
        name="get_fundamentals",
        description="USE WHEN: user asks for PE, PB, ROE, financial data, valuation, fundamentals. 获取股票基本面数据(PE/PB/ROE/市值等)。参数: ticker(股票代码)。",
        category="financial",
        timeout=20,
        input_schema={
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker (required)"}
            },
            "required": ["ticker"],
        },
    )

    def prompt(self) -> str:
        return (
            "Get fundamental/valuation data: PE, PB, ROE, market cap, dividend yield, etc.\n"
            "USE WHEN: user asks for PE, PB, ROE, 估值, 基本面, financial data, valuation.\n"
            "NOT for: stock prices (use get_price), technical indicators (use get_indicators).\n"
            "Parameters: ticker (required) — stock symbol.\n"
            "Returns: PE ratio, PB ratio, ROE, market cap, sector, industry, dividend yield.\n"
            "ONE call per ticker is sufficient."
        )

    def execute(self, ticker: str = "") -> str:
        emit_progress("fetching", message=f"Fetching fundamentals for {ticker}...")
        svc = _data_service()
        data = svc.get_fundamentals(ticker.upper())
        if not data:
            return self._error(f"No fundamentals data for {ticker}")
        return self._ok(data)


class WebSearchTool(BaseTool):
    meta = ToolMeta(
        name="web_search",
        description="USE WHEN: user asks about current events, general knowledge, non-stock topics, interest rates, economic data. 搜索互联网获取最新信息。参数: query(搜索关键词,必填)。返回搜索结果列表。",
        category="data",
        timeout=15,
        input_schema={
            "properties": {
                "query": {"type": "string", "description": "Search query (required)"}
            },
            "required": ["query"],
        },
    )

    def prompt(self) -> str:
        return (
            "Search the internet for current information.\n"
            "USE WHEN: user asks about current events, general knowledge, interest rates, "
            "economic data, or any topic not covered by stock-specific tools.\n"
            "NOT for: stock prices (use get_price), stock news (use get_news), "
            "stock fundamentals (use get_fundamentals).\n"
            "Parameters: query (required) — search keywords in any language.\n"
            "Returns: list of results with title, source, URL, and date.\n"
            "For ticker-based queries, prefer the dedicated financial tools."
        )

    def execute(self, query: str = "") -> str:
        emit_progress("searching", message=f"Searching: {query}...")
        try:
            from dataflow.providers.news_rss import fetch_google_news_rss

            articles = fetch_google_news_rss(query)
            return self._ok(
                {
                    "query": query,
                    "count": len(articles),
                    "results": [
                        {
                            "title": a.get("title", ""),
                            "source": a.get("source_name", ""),
                            "url": a.get("url", ""),
                            "published_at": a.get("published_at", ""),
                        }
                        for a in articles[:8]
                    ],
                }
            )
        except Exception as exc:
            return self._error(str(exc))


class SearchSymbolTool(BaseTool):
    meta = ToolMeta(
        name="search_symbol",
        description="USE WHEN: user mentions a company name (not ticker), needs to find stock code, 搜索股票代码. 搜索股票代码或公司名称。参数: query(搜索词,支持中英文)。返回匹配的股票列表。",
        category="financial",
        timeout=10,
    )

    def prompt(self) -> str:
        return (
            "Look up a stock ticker symbol by company name.\n"
            "USE WHEN: user mentions a company but you don't know its ticker symbol. "
            "Also use when a financial tool returns an error for an unknown ticker.\n"
            "Parameters: query (required) — company name in English or Chinese.\n"
            "Returns: ticker symbol, company name, sector, exchange, currency.\n"
            "Call this BEFORE get_price/get_indicators if you're unsure of the ticker."
        )

    def execute(self, query: str = "") -> str:
        import yfinance as yf

        try:
            t = yf.Ticker(query.upper())
            info = t.info or {}
            name = info.get("shortName") or info.get("longName") or query.upper()
            return self._ok(
                {
                    "ticker": query.upper(),
                    "name": name,
                    "sector": info.get("sector", ""),
                    "industry": info.get("industry", ""),
                    "currency": info.get("currency", "USD"),
                    "exchange": info.get("exchange", ""),
                    "market_cap": info.get("marketCap"),
                }
            )
        except Exception:
            return self._error(f"Could not find symbol: {query}")


class GetMetaTool(BaseTool):
    meta = ToolMeta(
        name="get_meta",
        description="获取股票基本信息(名称/行业/市值/交易所/货币)。参数: ticker。",
        category="financial",
        timeout=10,
    )

    def execute(self, ticker: str = "") -> str:
        from dataflow.service import DataService

        svc = DataService()
        meta = svc.get_meta(ticker.upper())
        return self._ok(meta) if meta else self._error(f"No meta for {ticker}")


class GetSentimentTool(BaseTool):
    meta = ToolMeta(
        name="get_sentiment",
        description="获取新闻情绪评分(-1到1,正=看多,负=看空)。参数: ticker, days(默认7)。",
        category="financial",
        timeout=15,
    )

    def execute(self, ticker: str = "", days: int | str = 7) -> str:
        try:
            days = int(days)
        except Exception:
            days = 7
        from dataflow.providers.sentiment import df_get_sentiment

        r = df_get_sentiment(ticker.upper(), window_days=days)
        return self._ok(r)


class GetMacroCalendarTool(BaseTool):
    meta = ToolMeta(
        name="get_macro_calendar",
        description="获取全球经济日历(CPI/FOMC/非农等)。参数: days(默认7)。",
        category="financial",
        timeout=15,
    )

    def execute(self, days: int | str = 7) -> str:
        try:
            days = int(days)
        except Exception:
            days = 7
        from dataflow.service import DataService

        svc = DataService()
        events = svc.df_get_macro_calendar(window_days=days)
        return self._ok({"events": events, "count": len(events)})


class SearchNewsTool(BaseTool):
    meta = ToolMeta(
        name="search_news",
        description="全文搜索历史新闻(FTS5)。参数: query(关键词), ticker(可选), limit(默认20)。",
        category="financial",
        timeout=5,
    )

    def execute(self, query: str = "", ticker: str = "", limit: int | str = 20) -> str:
        try:
            limit = int(limit)
        except Exception:
            limit = 20
        from dataflow.service import DataService

        svc = DataService()
        results = svc.search_news(
            query, ticker=ticker.upper() if ticker else None, limit=limit
        )
        return self._ok(
            {"query": query, "count": len(results), "results": results[:limit]}
        )


class RunAnalysisTool(BaseTool):
    meta = ToolMeta(
        name="run_analysis",
        description="运行完整的多Agent分析流程(技术面/新闻/基本面/风险/PM综合)。参数: ticker, date(可选)。耗时较长(30-60秒)。",
        category="research",
        timeout=120,
        is_readonly=True,
    )

    def execute(self, ticker: str = "", date: str = "") -> str:
        emit_progress("analyzing", message=f"Running full analysis on {ticker}...")
        from quick_ask.orchestrator import IntelliFin_Assistant

        assistant = IntelliFin_Assistant()
        from datetime import datetime, timezone

        d = date or datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        result = assistant.run(ticker.upper(), date=d)
        return self._ok(
            {
                "ticker": ticker.upper(),
                "action": result.get("Action", "HOLD"),
                "target_position_pct": result.get("Target_position_pct", 0),
                "pm_report": result.get("PM_report", "")[:2000],
                "market_report": str(result.get("market_report", ""))[:500],
                "news_report": str(result.get("news_report", ""))[:500],
                "fundamental_report": str(result.get("fundamental_report", ""))[:500],
                "risk_report": str(result.get("risk_report", ""))[:500],
            }
        )


class GenerateBriefTool(BaseTool):
    meta = ToolMeta(
        name="generate_brief",
        description="生成晨间市场简报(50+新闻源,覆盖全球市场)。参数: hours(默认24,只包含最近N小时新闻)。耗时较长(30-60秒)。",
        category="research",
        timeout=120,
        is_readonly=True,
    )

    def execute(self, hours: int | str = 24) -> str:
        try:
            hours = int(hours)
        except Exception:
            hours = 24
        emit_progress(
            "generating", message=f"Generating market brief (last {hours}h)..."
        )
        from server.morning_brief import run

        brief = run(hours=hours)
        return self._ok(
            {
                "title": brief.get("title", ""),
                "summary": brief.get("summary", ""),
                "content": brief.get("content", "")[:3000],
                "news_count": brief.get("news_count", 0),
                "elapsed_s": brief.get("elapsed_s", 0),
            }
        )


class LoadSkillTool(BaseTool):
    meta = ToolMeta(
        name="load_skill",
        description="加载指定技能/策略的完整文档。参数: name(技能名称), offset(起始字符位置,默认0), limit(最大字符数,默认8000)。用于获取详细方法论、分析框架或交易策略。",
        category="workspace",
        timeout=5,
    )

    def prompt(self) -> str:
        return (
            "Load the full documentation of a skill/strategy/methodology.\n"
            "USE WHEN: user asks how to use a specific analysis technique "
            "(e.g., candlestick patterns, DCF valuation, pair trading).\n"
            "Also use when the system prompt lists relevant skills for the query.\n"
            "Parameters: name (required) — skill name.\n"
            "  offset (optional) — start reading from this character position.\n"
            "  limit (optional, default 8000) — max characters to load.\n"
            "Skills are listed in the 'Relevant Skills' section of this prompt."
        )

    def execute(
        self, name: str = "", offset: int | str = 0, limit: int | str = 8000
    ) -> str:
        try:
            offset = int(offset)
            limit = int(limit)
        except (ValueError, TypeError):
            offset = 0
            limit = 8000
        if not name.strip():
            return self._error("name required")

        from skills.loader import get_loader

        loader = get_loader()
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

        full_content = skill.prompt_template
        total_len = len(full_content)
        chunk = full_content[offset : offset + limit]

        return self._ok(
            {
                "name": skill.name,
                "category": skill.category,
                "description": skill.description,
                "version": skill.version,
                "is_builtin": skill.is_builtin,
                "content": chunk,
                "total_length": total_len,
                "offset": offset,
                "limit": limit,
                "has_more": (offset + limit) < total_len,
            }
        )


class SearchSkillsTool(BaseTool):
    meta = ToolMeta(
        name="search_skills",
        description="搜索技能/策略(匹配名称/描述/内容)。参数: query(关键词,必填), category(分类过滤,可选), limit(默认20)。",
        category="workspace",
        timeout=5,
    )

    def execute(
        self, query: str = "", category: str = "", limit: int | str = 20
    ) -> str:
        try:
            limit = int(limit)
        except Exception:
            limit = 20
        if not query.strip():
            return self._error("query required")

        from skills.loader import get_loader

        loader = get_loader()
        loader.discover()
        query_lower = query.lower()
        results = []
        for skill in loader.skills.values():
            if category and skill.category != category:
                continue
            score = 0
            match_context = ""
            if query_lower in skill.name.lower():
                score = 100
                match_context = f"name: {skill.name}"
            elif query_lower in skill.description.lower():
                score = 50
                match_context = skill.description[:200]
            elif query_lower in skill.prompt_template.lower():
                score = 10
                idx = skill.prompt_template.lower().find(query_lower)
                start = max(0, idx - 40)
                end = min(len(skill.prompt_template), idx + len(query) + 40)
                match_context = "..." + skill.prompt_template[start:end] + "..."
            if score > 0:
                results.append(
                    {
                        "name": skill.name,
                        "category": skill.category,
                        "description": skill.description[:150],
                        "version": skill.version,
                        "is_builtin": skill.is_builtin,
                        "match_score": score,
                        "match_context": match_context[:300],
                    }
                )
        results.sort(key=lambda x: -x["match_score"])
        return self._ok(
            {"query": query, "count": len(results), "results": results[:limit]}
        )


class ListSkillsTool(BaseTool):
    meta = ToolMeta(
        name="list_skills",
        description="列出所有可用技能。参数: category(分类过滤,可选), limit(默认50)。返回技能列表含分类概览和计数。",
        category="workspace",
        timeout=5,
    )

    def execute(self, category: str = "", limit: int | str = 50) -> str:
        try:
            limit = int(limit)
        except Exception:
            limit = 50
        from skills.loader import get_loader

        loader = get_loader()
        loader.discover()
        skills = list(loader.skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        skills.sort(key=lambda s: (s.category, s.name))
        result = [
            {
                "name": s.name,
                "category": s.category,
                "description": s.description[:200],
                "version": s.version,
                "is_builtin": s.is_builtin,
            }
            for s in skills[:limit]
        ]
        cat_counts: dict[str, int] = {}
        for s in loader.skills.values():
            cat_counts[s.category] = cat_counts.get(s.category, 0) + 1
        return self._ok(
            {
                "total": len(loader.skills),
                "shown": len(result),
                "categories": cat_counts,
                "skills": result,
            }
        )


class SaveSkillTool(BaseTool):
    meta = ToolMeta(
        name="save_skill",
        description="创建或更新用户技能。参数: name(小写+连字符), content(完整SKILL.md含YAML frontmatter), category(默认user)。",
        category="workspace",
        timeout=10,
        is_readonly=False,
    )

    def execute(self, name: str = "", content: str = "", category: str = "user") -> str:
        import re
        from pathlib import Path

        if not name or not content:
            return self._error("name and content required")
        slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())[:60]
        skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        user_dir = skills_dir / "user" / slug
        user_dir.mkdir(parents=True, exist_ok=True)
        skill_path = user_dir / "SKILL.md"
        if not content.strip().startswith("---"):
            content = (
                f"---\nname: {slug}\n"
                f"description: User-created skill\n"
                f"category: {category}\n"
                f'version: "1.0"\n'
                f"---\n\n{content}"
            )
        # Validate YAML frontmatter
        try:
            import yaml

            parts = content.split("---")
            if len(parts) >= 3:
                yaml.safe_load(parts[1])
        except Exception as e:
            return self._error(f"Invalid YAML frontmatter: {e}")
        skill_path.write_text(content, encoding="utf-8")
        from skills.loader import reset_loader

        reset_loader()
        return self._ok(
            {
                "name": slug,
                "path": str(skill_path),
                "message": f"Skill '{slug}' saved. Use load_skill('{slug}') to read it.",
            }
        )


class DeleteSkillTool(BaseTool):
    meta = ToolMeta(
        name="delete_skill",
        description="删除用户创建的技能（不能删除内置技能）。参数: name(技能名称)。",
        category="workspace",
        timeout=5,
        is_readonly=False,
    )

    def execute(self, name: str = "") -> str:
        import re
        import shutil
        from pathlib import Path

        if not name.strip():
            return self._error("name required")
        slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())[:60]
        skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
        user_skill_dir = skills_dir / "user" / slug
        # Safety: ensure we're only deleting from user/
        try:
            user_skill_dir.resolve().relative_to((skills_dir / "user").resolve())
        except ValueError:
            return self._error("Cannot delete skills outside user directory")
        if not user_skill_dir.exists():
            return self._error(
                f"User skill '{slug}' not found. Only user skills can be deleted."
            )
        shutil.rmtree(user_skill_dir)
        from skills.loader import reset_loader

        reset_loader()
        return self._ok(
            {
                "name": slug,
                "message": f"Skill '{slug}' deleted.",
            }
        )


class WebFetchTool(BaseTool):
    meta = ToolMeta(
        name="web_fetch",
        description="抓取网页全文内容(转为Markdown)。参数: url(网页地址)。",
        category="data",
        timeout=20,
    )

    def execute(self, url: str = "") -> str:
        emit_progress("fetching", message=f"Fetching {url[:60]}...")
        try:
            import requests

            resp = requests.get(
                f"https://r.jina.ai/{url}",
                headers={"Accept": "text/markdown", "User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text[:5000]
            return self._ok({"url": url, "content": text, "length": len(text)})
        except Exception as exc:
            return self._error(str(exc))
