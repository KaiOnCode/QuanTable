from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Annotated, Any, Optional, Protocol, cast

from langchain_core.tools import tool

from dataflow.service import DataService


class ToolDataService(Protocol):
    def df_get_prices(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: Optional[str] = None,
    ) -> dict[str, Any]: ...

    def df_get_indicators(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: Optional[str] = None,
    ) -> dict[str, Any]: ...

    def df_get_fundamentals(
        self,
        ticker: str,
        end_date: Optional[str] = None,
    ) -> dict[str, Any]: ...

    def df_get_news(
        self,
        ticker: str,
        window_days: int = 7,
        max_items: int = 20,
        end_date: Optional[str] = None,
    ) -> list[dict[str, Any]]: ...


_data_service_factory: Callable[[], ToolDataService] = DataService
_data_service: ToolDataService | None = None


def configure_data_service_factory(factory: Callable[[], ToolDataService]) -> None:
    global _data_service_factory, _data_service
    _data_service_factory = factory
    _data_service = None


def reset_data_service_factory() -> None:
    configure_data_service_factory(DataService)


def get_data_service() -> ToolDataService:
    global _data_service
    if _data_service is None:
        _data_service = _data_service_factory()
    return _data_service


def _struct(data: dict[str, Any] | list[dict[str, Any]]) -> str:
    """Return compact JSON so tool output can be parsed downstream."""
    return json.dumps(data, ensure_ascii=False, default=str)


@tool
def get_price(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    lookback_days: Annotated[int, "回溯天数，例如 30 表示最近30天的数据"] = 30,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """获取指定股票代码的股价数据（OHLCV）。缓存优先，缓存无数据才调 Yahoo。"""
    from datetime import datetime, timezone, timedelta
    from dataflow.store import MarketDataStore

    store = MarketDataStore()
    end = (datetime.fromisoformat(end_date.replace("Z", "+00:00")) if end_date
           else datetime.now(timezone.utc))
    start = end - timedelta(days=lookback_days)

    # Try live fetch first
    result = None
    source = "缓存"
    try:
        result = get_data_service().df_get_prices(symbol, lookback_days, end_date=end_date)
        source = "Yahoo Finance (实时)"
    except Exception:
        pass

    # Fallback to cache
    if not result or not result.get("rows"):
        cached = store.get_ohlcv(symbol.upper(), start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if cached:
            ticker = symbol.upper()
            rows = [{"ts": r["date"], "o": r["open"], "h": r["high"],
                     "l": r["low"], "c": r["close"], "v": r["volume"]} for r in cached]
            output = f"股票代码: {ticker}\n数据条数: {len(rows)} (来自缓存)\n\n"
            output += "日期\t\t开盘价\t最高价\t最低价\t收盘价\t成交量\n" + "-" * 70 + "\n"
            for row in rows:
                output += f"{row['ts']}\t{row['o']:.2f}\t{row['h']:.2f}\t{row['l']:.2f}\t{row['c']:.2f}\t{int(row['v']):,}\n"
            return output
        return f"未找到股票代码 {symbol} 在最近 {lookback_days} 天的数据（实时和缓存均无）"

    ticker = result.get("ticker", symbol)
    tz = result.get("tz")
    rows = result.get("rows", [])

    output = f"股票代码: {ticker}\n"
    if tz:
        output += f"时区: {tz}\n"
    output += f"数据条数: {len(rows)} (来源: {source})\n\n"
    output += "日期\t\t开盘价\t最高价\t最低价\t收盘价\t成交量\n"
    output += "-" * 70 + "\n"

    for row in rows:
        ts = row.get("ts", "")[:10]
        o = row.get("o", 0)
        h = row.get("h", 0)
        low = row.get("l", 0)
        c = row.get("c", 0)
        v = int(row.get("v", 0))
        output += f"{ts}\t{o:.2f}\t{h:.2f}\t{low:.2f}\t{c:.2f}\t{v:,}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    lookback_days: Annotated[int, "回溯天数，例如 30 表示最近30天的数据"] = 30,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """获取指定股票代码的技术指标。缓存优先。"""
    from calendar import month

    # Use the verified market snapshot for deterministic indicators
    result = get_verified_market_snapshot.invoke({
        "symbol": symbol, "curr_date": end_date or f"{2026}-07-17T00:00:00Z", "lookback_days": lookback_days})
    if result and len(result) > 50:
        return result

    # Fallback to live fetch
    try:
        result = get_data_service().df_get_indicators(
            symbol, lookback_days, end_date=end_date
        )
    except Exception as e:
        return f"指标数据获取失败: {e}"

    if not result:
        return f"未找到股票代码 {symbol} 的技术指标数据"

    output = f"股票代码: {symbol}\n技术指标数据:\n\n"

    rsi = result.get("rsi14")
    if rsi is not None:
        rsi_label = "超卖" if rsi < 30 else "超买" if rsi > 70 else "中性"
        output += f"RSI(14): {rsi:.2f} ({rsi_label})\n"

    macd = result.get("macd", {})
    if macd:
        hist = macd.get("hist")
        signal_cross = macd.get("signal_cross", False)
        if hist is not None:
            output += f"MACD 柱: {hist:.4f}\n"
        output += f"MACD 信号交叉: {'是' if signal_cross else '否'}\n"

    ma = result.get("ma", {})
    if ma:
        sma20 = ma.get("sma20")
        sma50 = ma.get("sma50")
        if sma20 is not None:
            output += f"SMA(20): {sma20:.2f}\n"
        if sma50 is not None:
            output += f"SMA(50): {sma50:.2f}\n"

    atr = result.get("atr20")
    if atr is not None:
        output += f"ATR(20): {atr:.4f}\n"

    levels = result.get("levels", {})
    if levels:
        support = levels.get("support")
        resistance = levels.get("resistance")
        if support is not None:
            output += f"支撑位: {support:.2f}\n"
        if resistance is not None:
            output += f"阻力位: {resistance:.2f}\n"

    breakout = result.get("breakout", {})
    if breakout:
        level = breakout.get("level")
        distance_pct = breakout.get("distance_pct")
        if level is not None:
            output += f"突破位: {level:.2f}\n"
        if distance_pct is not None:
            output += f"突破距离: {distance_pct:.2f}%\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


@tool
def get_fundamentals(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则获取实时数据，否则获取历史数据",
    ] = None,
) -> str:
    """获取指定股票代码的基本面数据。缓存优先。"""
    from datetime import datetime, timezone
    from dataflow.store import MarketDataStore

    store = MarketDataStore()
    end = (datetime.fromisoformat(end_date.replace("Z", "+00:00")) if end_date
           else datetime.now(timezone.utc))
    as_of = end.strftime("%Y-%m-%d")

    # Try live fetch first
    result = None
    source = "缓存"
    try:
        result = get_data_service().df_get_fundamentals(symbol, end_date=end_date)
        source = "Yahoo Finance (实时)"
    except Exception:
        pass

    # Fallback to cache
    if not result:
        cached = store.get_fundamentals(symbol.upper(), as_of_date=as_of)
        if cached:
            output = f"股票代码: {symbol.upper()}\n基本面数据 (来自缓存):\n\n"
            for k, v in sorted(cached.items()):
                if v is not None and k not in ("ticker", "as_of_date", "raw_json", "source"):
                    output += f"  {k}: {v}\n"
            return output
        return f"未找到股票代码 {symbol} 的基本面数据（实时和缓存均无）"

    output = f"股票代码: {symbol}\n基本面数据:\n\n"

    ttm = result.get("ttm", {})
    if ttm:
        pe = ttm.get("pe")
        pb = ttm.get("pb")
        ps = ttm.get("ps")
        ev_ebitda = ttm.get("ev_ebitda")
        eps = ttm.get("eps")
        gross_margin = ttm.get("gross_margin")
        op_margin = ttm.get("op_margin")

        if any(x is not None for x in [pe, pb, ps, ev_ebitda, eps]):
            output += "【估值指标 (TTM)】\n"
            if pe is not None:
                output += f"  PE: {pe:.2f}\n"
            if pb is not None:
                output += f"  PB: {pb:.2f}\n"
            if ps is not None:
                output += f"  PS: {ps:.2f}\n"
            if ev_ebitda is not None:
                output += f"  EV/EBITDA: {ev_ebitda:.2f}\n"
            if eps is not None:
                output += f"  EPS: {eps:.2f}\n"
            output += "\n"

        if gross_margin is not None or op_margin is not None:
            output += "【盈利能力】\n"
            if gross_margin is not None:
                output += f"  毛利率: {gross_margin:.2f}%\n"
            if op_margin is not None:
                output += f"  营业利润率: {op_margin:.2f}%\n"
            output += "\n"

    growth = result.get("growth", {})
    if growth:
        eps_yoy = growth.get("eps_yoy")
        rev_yoy = growth.get("rev_yoy")

        if eps_yoy is not None or rev_yoy is not None:
            output += "【增长指标】\n"
            if eps_yoy is not None:
                output += f"  EPS 同比增长: {eps_yoy:.2f}%\n"
            if rev_yoy is not None:
                output += f"  营收同比增长: {rev_yoy:.2f}%\n"
            output += "\n"

    balance = result.get("balance", {})
    if balance:
        net_debt_to_ebitda = balance.get("net_debt_to_ebitda")
        if net_debt_to_ebitda is not None:
            output += "【财务健康度】\n"
            output += f"  净债务/EBITDA: {net_debt_to_ebitda:.2f}\n\n"

    sector_bench = result.get("sector_bench", {})
    if sector_bench:
        sector_pe = sector_bench.get("pe")
        if sector_pe is not None:
            output += "【行业基准】\n"
            output += f"  行业市盈率: {sector_pe:.2f}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


def _fetch_news_multi_source(symbol: str, window_days: int) -> tuple[list[dict], str]:
    """Multi-provider news: Yahoo + Google RSS merged, dedup by URL."""
    from dataflow.store import MarketDataStore
    store = MarketDataStore()
    all_articles = []
    seen_urls = set()
    sources = []

    def _add(articles, source_name):
        nonlocal all_articles
        added = 0
        for a in articles:
            url = a.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            a.setdefault("summary", "")
            a.setdefault("published_at", "")
            a.setdefault("source_name", a.get("source_name", source_name))
            all_articles.append(a)
            added += 1
        if added:
            sources.append(source_name)

    # Layer 1: Yahoo Finance
    try:
        import yfinance as yf
        t = yf.Ticker(symbol.upper())
        raw = t.news or []
        yahoo_articles = []
        for item in raw[:20]:
            content = item.get("content", {}) or {}
            pub_time = content.get("pubDate") or content.get("providerPublishTime") or ""
            if isinstance(pub_time, (int, float)):
                from datetime import datetime, timezone
                pub_time = datetime.fromtimestamp(pub_time, tz=timezone.utc).isoformat()
            provider = content.get("provider", {}) or {}
            yahoo_articles.append({
                "title": content.get("title", "") or item.get("title", ""),
                "summary": content.get("summary", "") or "",
                "source_name": provider.get("displayName", "") if isinstance(provider, dict) else "Yahoo Finance",
                "url": content.get("canonicalUrl", {}).get("url", "") if isinstance(content.get("canonicalUrl"), dict) else str(content.get("canonicalUrl", "")),
                "published_at": str(pub_time) if pub_time else "",
            })
        _add(yahoo_articles, "Yahoo Finance")
    except Exception:
        pass

    # Layer 2: Google News RSS
    try:
        from dataflow.providers.news_rss import fetch_google_news_rss
        google_articles = fetch_google_news_rss(f"{symbol} stock news")
        for a in google_articles:
            a.setdefault("source_name", a.get("source_name", "Google News"))
        _add(google_articles[:50], "Google News RSS")
    except Exception:
        pass

    if all_articles:
        try:
            store.add_news_articles(symbol.upper(), all_articles[:50])
        except Exception:
            pass
        return all_articles[:50], " + ".join(sources)

    # Layer 3: SQLite cache
    cached = store.get_news(symbol.upper(), window_days=window_days)
    if cached:
        return cached, "SQLite cache"

    return [], "none"

@tool
def get_news(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    window_days: Annotated[int, "窗口天数，例如 7 表示最近7天的数据"] = 7,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """获取指定股票代码的新闻。多源 fallback：缓存→Yahoo→Google RSS→Bing。"""
    articles, source = _fetch_news_multi_source(symbol, window_days)
    if not articles:
        return f"未找到 {symbol.upper()} 在最近 {window_days} 天的新闻（所有源均无数据）"

    output = f"股票代码: {symbol.upper()}\n新闻 (最近 {window_days} 天, 来源: {source}): 共 {len(articles)} 条\n" + "-" * 80 + "\n"
    for idx, n in enumerate(articles[:30], 1):
        title = n.get("title", "无标题")
        source_name = n.get("source_name", n.get("source", "未知"))
        date = (n.get("published_at") or "")[:10]
        summary = n.get("summary", "")
        output += f"【{idx}】{title}\n"
        if summary:
            output += f"  摘要: {summary[:200]}\n"
        output += f"  来源: {source_name} | {date}\n" + "-" * 80 + "\n"
    return output


@tool
def get_sector(
    symbol: Annotated[str, "公司的股票代码"],
) -> str:
    """获取指定股票代码的行业背景和同行比较数据。"""
    service = cast(Any, get_data_service())
    result = service.df_get_sector_context(symbol)

    if not result:
        return f"未找到股票代码 {symbol} 的行业数据"

    output = f"股票代码: {symbol}\n行业背景:\n\n"
    if "sector" in result:
        output += f"  行业: {result['sector']}\n"
    if "industry" in result:
        output += f"  子行业: {result['industry']}\n"
    if "peers" in result:
        output += f"  同行: {', '.join(result['peers'][:8])}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


@tool
def get_macro(
    window_days: Annotated[int, "窗口天数"] = 7,
) -> str:
    """获取全球经济日历——CPI、FOMC、失业率等宏观事件。"""
    service = cast(Any, get_data_service())
    result = service.df_get_macro_calendar(window_days=window_days)

    if not result:
        return f"最近 {window_days} 天无宏观事件"

    output = f"宏观日历 (未来 {window_days} 天):\n共 {len(result)} 个事件\n\n"
    output += "日期\t\t事件\t\t重要性\n"
    output += "-" * 60 + "\n"

    for event_item in result:
        date = (event_item.get("date") or "")[:10]
        event = event_item.get("event", "")[:30]
        impact = event_item.get("impact", "medium")
        output += f"{date}\t{event}\t{impact}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


@tool
def get_sentiment(
    symbol: Annotated[str, "公司的股票代码"],
    window_days: Annotated[int, "窗口天数，默认 7"] = 7,
) -> str:
    """获取指定股票代码的新闻情绪评分。用多源 news pipeline。"""
    articles, source = _fetch_news_multi_source(symbol, window_days)

    if not articles:
        return f"未找到 {symbol.upper()} 的情绪数据——最近 {window_days} 天无相关新闻"

    bullish_words = [
        "beat", "raise", "upgrade", "growth", "strong", "positive",
        "buy", "outperform", "opportunity", "expansion", "record",
        "surge", "jump", "rally", "boost", "accelerate",
    ]
    bearish_words = [
        "miss", "cut", "downgrade", "decline", "weak", "negative",
        "sell", "underperform", "risk", "layoff", "loss",
        "drop", "fall", "plunge", "slowdown", "warning",
    ]

    scores = []
    all_keywords = {}
    for a in articles:
        text = ((a.get("title") or "") + " " + (a.get("summary") or "")).lower()
        bull = sum(1 for w in bullish_words if w in text)
        bear = sum(1 for w in bearish_words if w in text)
        total = bull + bear
        scores.append((bull - bear) / total if total > 0 else 0.0)
        for w in bullish_words + bearish_words:
            if w in text:
                all_keywords[w] = all_keywords.get(w, 0) + 1

    avg_score = sum(scores) / len(scores) if scores else 0.0
    variance = sum((s - avg_score) ** 2 for s in scores) / len(scores) if scores else 1.0
    confidence = min(1.0, len(articles) / 10.0 * (1.0 - min(variance, 0.5)))
    top_kw = [kw for kw, _ in sorted(all_keywords.items(), key=lambda x: -x[1])[:10]]

    label = "看多" if avg_score > 0.1 else "看空" if avg_score < -0.1 else "中性"
    output = (
        f"股票代码: {symbol.upper()}\n"
        f"情绪评分: {avg_score:.2f} ({label})\n"
        f"置信度: {confidence:.2f}\n"
        f"新闻条数: {len(articles)}\n"
        f"关键词: {', '.join(top_kw[:5])}\n"
        f"数据来源: {source}\n"
    )
    return output


@tool
def recall_memory(
    symbol: Annotated[str, "公司的股票代码"],
    limit: Annotated[int, "最多返回的记录数"] = 5,
) -> str:
    """从策略记忆中检索相关的历史交易记录和经验教训。"""
    from memory.store import MemoryStore

    store = MemoryStore("data/memory.db")
    records = store.recall(ticker=symbol, limit=limit, min_score=0.0)

    if not records:
        return f"未找到 {symbol} 的相关历史记忆"

    output = f"股票代码: {symbol}\n相关历史记忆 ({len(records)} 条):\n\n"

    for idx, record in enumerate(records, 1):
        output += f"【记忆 {idx}】OWM: {record.owm_score:.2f}\n"
        output += f"  {record.episodic[:200]}\n"
        if record.semantic:
            output += f"  规则: {record.semantic[:150]}\n"
        output += "\n"

    output += f"<!-- JSON: {_struct([record.model_dump() for record in records])} -->"
    return output


# ── New tools (Phase 1 expansion) ──────────────────────────


@tool
def get_verified_market_snapshot(
    symbol: Annotated[str, "公司的股票代码"],
    curr_date: Annotated[str, "当前分析日期（ISO格式）"],
    lookback_days: Annotated[int, "回溯天数，默认60"] = 60,
) -> str:
    """获取经过确定性验证的市场数据快照（OHLCV + 全部常用指标）。

    此工具直接从 MarketDataStore 读取数据并计算指标，无 LLM 参与。
    作为市场分析师的真相来源——所有价格/指标数值声明必须以此为准。
    """
    from dataflow.store import MarketDataStore
    from datetime import datetime, timedelta

    store = MarketDataStore()
    end_date = datetime.fromisoformat(curr_date.replace("Z", "+00:00").split("T")[0])
    start_date = (end_date - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    rows = store.get_ohlcv(symbol.upper(), start_date, end_str)
    if not rows:
        return f"未找到 {symbol.upper()} 在 {start_date} 至 {end_str} 的 OHLCV 数据"

    # Compute indicators deterministically
    closes = [float(r["close"]) for r in rows]
    highs = [float(r["high"]) for r in rows]
    lows = [float(r["low"]) for r in rows]
    volumes = [int(r["volume"]) for r in rows]
    dates = [r["date"] for r in rows]

    n = len(closes)
    latest_close = closes[-1] if closes else 0
    prev_close = closes[-2] if n > 1 else latest_close

    # SMA
    def sma(data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    sma200 = sma(closes, 200) if n >= 200 else None

    # EMA
    def ema(data, period):
        if len(data) < period:
            return None
        k = 2 / (period + 1)
        result = data[0]
        for x in data[1:]:
            result = x * k + result * (1 - k)
        return result

    ema10 = ema(closes[-30:], 10) if n >= 30 else None

    # RSI(14)
    if n >= 15:
        gains = []
        losses = []
        for i in range(n - 14, n):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        rsi = 100 - (100 / (1 + avg_gain / avg_loss)) if avg_loss > 0 else 100
    else:
        rsi = None

    # MACD
    if n >= 26:
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd_line = ema12 - ema26
        # Signal: EMA9 of MACD (simplified)
        macd_signal = None
    else:
        macd_line = macd_signal = None

    # ATR(14)
    if n >= 15:
        trs = []
        for i in range(n - 14, n):
            h = highs[i]
            l = lows[i]
            pc = closes[i - 1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            trs.append(tr)
        atr = sum(trs) / 14
    else:
        atr = None

    # Bollinger Bands (20)
    if n >= 20 and sma20:
        variance = sum((c - sma20) ** 2 for c in closes[-20:]) / 20
        stddev = variance**0.5
        boll_upper = sma20 + 2 * stddev
        boll_lower = sma20 - 2 * stddev
    else:
        boll_upper = boll_lower = None

    # Support / Resistance (simple: recent min/max)
    support = min(lows[-20:]) if n >= 20 else None
    resistance = max(highs[-20:]) if n >= 20 else None

    # Change %
    change_pct = ((latest_close - prev_close) / prev_close * 100) if prev_close else 0

    # Volume ratio (recent avg vs total avg)
    vol_20 = sum(volumes[-20:]) / min(20, n) if n >= 20 else 0
    vol_all = sum(volumes) / n if n > 0 else 0
    vol_ratio = vol_20 / vol_all if vol_all > 0 else 1.0

    rsi_label = "超卖" if (rsi or 50) < 30 else "超买" if (rsi or 50) > 70 else "中性"

    def _f(v, fmt=".2f"):
        """Format a value, return 'N/A' if None."""
        if v is None:
            return "N/A"
        return f"{v:{fmt}}"

    output = f"""股票代码: {symbol.upper()}
数据范围: {dates[0]} 至 {dates[-1]} ({n} 条)
最新收盘价: {latest_close:.2f} ({dates[-1]})
涨跌幅: {change_pct:+.2f}%

=== 趋势指标 ===
SMA(20):  {_f(sma20)}  {'→ 价格在均线上方' if sma20 and latest_close > sma20 else '→ 价格在均线下方' if sma20 else 'N/A'}
SMA(50):  {_f(sma50)}  {'→ 价格在均线上方' if sma50 and latest_close > sma50 else '→ 价格在均线下方' if sma50 else 'N/A'}
SMA(200): {_f(sma200)} {'→ 价格在均线上方' if sma200 and latest_close > sma200 else '→ 价格在均线下方' if sma200 else 'N/A'}
EMA(10):  {_f(ema10)} {'N/A' if ema10 is None else ''}
黄金交叉(SMA20/50): {'是' if sma20 and sma50 and sma20 > sma50 else '否'}

=== 动量指标 ===
RSI(14):    {_f(rsi,'.1f')} ({rsi_label})
MACD:        {_f(macd_line,'.4f')}

=== 波动率 ===
ATR(14):       {_f(atr)}
Bollinger上轨: {_f(boll_upper)}
Bollinger下轨: {_f(boll_lower)}

=== 位阶 ===
20日支撑: {_f(support)}
20日阻力: {_f(resistance)}

=== 成交量 ===
近20日均量: {vol_20:,.0f}
历史均量:   {vol_all:,.0f}
量比:       {vol_ratio:.2f}  {'→ 放量' if vol_ratio > 1.2 else '→ 缩量' if vol_ratio < 0.8 else '→ 持平'}
"""
    return output


@tool
def get_global_news(
    curr_date: Annotated[str, "当前日期（ISO格式）"],
    look_back_days: Annotated[int, "回溯天数，默认3"] = 3,
    limit: Annotated[int, "最大条数，默认15"] = 15,
) -> str:
    """获取全球宏观经济新闻。搜索利率、央行、GDP、通胀、地缘政治等关键词。"""
    from dataflow.providers.news_rss import fetch_google_news_rss

    macro_keywords = [
        "federal reserve interest rate",
        "央行 利率",
        "global economy GDP",
        "inflation CPI",
        "geopolitical risk trade war",
        "stock market outlook",
    ]

    all_articles = []
    seen_urls = set()
    for kw in macro_keywords:
        try:
            articles = fetch_google_news_rss(kw)
            for a in articles:
                url = a.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)
        except Exception:
            continue
        if len(all_articles) >= limit * 2:
            break

    if not all_articles:
        return "未找到宏观经济新闻"

    all_articles.sort(key=lambda a: a.get("published_at", ""), reverse=True)
    selected = all_articles[:limit]

    output = f"全球宏观经济新闻 (最近 {look_back_days} 天, {len(selected)} 条):\n" + "-" * 80 + "\n"
    for idx, a in enumerate(selected, 1):
        title = a.get("title", "无标题")
        source = a.get("source_name", "未知")
        date = (a.get("published_at") or "")[:10]
        url = a.get("url", "")
        output += f"【{idx}】{title}\n  来源: {source} | {date}"
        if url:
            output += f" | {url}"
        output += "\n" + "-" * 80 + "\n"

    return output


@tool
def get_macro_indicators(
    indicator: Annotated[str, "指标名称: cpi, core_pce, unemployment, fed_funds_rate, 10y_treasury, yield_curve, gdp"],
    curr_date: Annotated[str, "当前日期（ISO格式）"],
    look_back_days: Annotated[int, "回溯天数，默认365"] = 365,
) -> str:
    """获取宏观经济指标数据（FRED）。支持的指标：CPI、核心PCE、失业率、联邦基金利率、10年国债、收益率曲线、GDP。"""
    indicator_map = {
        "cpi": ("CPIAUCSL", "Consumer Price Index (CPI)", "指数"),
        "core_pce": ("PCEPILFE", "Core PCE (excl. food & energy)", "指数"),
        "unemployment": ("UNRATE", "Unemployment Rate", "%"),
        "fed_funds_rate": ("FEDFUNDS", "Federal Funds Effective Rate", "%"),
        "10y_treasury": ("DGS10", "10-Year Treasury Yield", "%"),
        "yield_curve": ("T10Y2Y", "10Y-2Y Treasury Spread", "%"),
        "gdp": ("GDP", "Gross Domestic Product", "十亿美元"),
    }

    if indicator.lower() not in indicator_map:
        valid = ", ".join(indicator_map.keys())
        return f"不支持的指标 '{indicator}'。可选: {valid}"

    series_id, name, unit = indicator_map[indicator.lower()]

    try:
        from fredapi import Fred

        api_key = os.environ.get("FRED_API_KEY", "")
        if not api_key:
            return f"FRED API 密钥未配置。请在环境变量中设置 FRED_API_KEY。"

        fred = Fred(api_key=api_key)
        end_date = curr_date[:10] if "T" in curr_date else curr_date
        data = fred.get_series(series_id, observation_end=end_date)
        if data.empty:
            return f"未找到 {name} ({series_id}) 的数据"

        recent = data.tail(min(24, len(data)))
        latest = float(recent.iloc[-1])
        prev = float(recent.iloc[-2]) if len(recent) > 1 else latest
        change = latest - prev

        timestamps = [str(idx)[:10] for idx in recent.index]
        values = [f"{float(v):.2f}" for v in recent.values]

        output = f"{name} ({series_id})\n"
        output += f"最新值: {latest:.2f} {unit} | 变动: {change:+.2f}\n\n"
        output += "近期数据:\n"
        for ts, val in zip(timestamps[-12:], values[-12:]):
            output += f"  {ts}: {val} {unit}\n"

        return output

    except ImportError:
        # Fallback: Google News search
        search_terms = {
            "cpi": "US CPI inflation latest data",
            "unemployment": "US unemployment rate latest",
            "fed_funds_rate": "Federal Reserve interest rate decision",
            "gdp": "US GDP growth latest",
        }
        query = search_terms.get(indicator.lower(), f"{name} latest data")
        from dataflow.providers.news_rss import fetch_google_news_rss

        articles = fetch_google_news_rss(query)
        if not articles:
            return f"未找到 {name} 的相关数据（FRED 不可用，新闻搜索也无结果）"

        output = f"{name} — 新闻搜索结果 (FRED 不可用):\n"
        for a in articles[:5]:
            output += f"- {a.get('title','')} ({a.get('source_name','')}, {str(a.get('published_at',''))[:10]})\n"
        return output
    except Exception as exc:
        return f"获取 {name} 数据失败: {exc}"


@tool
def get_balance_sheet(
    symbol: Annotated[str, "公司的股票代码"],
    freq: Annotated[str, "频率: quarterly 或 annual"] = "quarterly",
) -> str:
    """获取公司资产负债表。包含总资产、总负债、股东权益、流动资产、流动负债等。"""
    import yfinance as yf

    ticker = yf.Ticker(symbol.upper())
    try:
        if freq == "annual":
            bs = ticker.balance_sheet
        else:
            bs = ticker.quarterly_balance_sheet
    except Exception:
        return f"未找到 {symbol.upper()} 的资产负债表数据"

    if bs is None or bs.empty:
        return f"未找到 {symbol.upper()} 的资产负债表数据"

    latest = bs.iloc[:, 0]
    output = f"股票代码: {symbol.upper()}\n资产负债表 ({freq}, {str(bs.columns[0])[:10]}):\n\n"
    key_items = [
        "Total Assets", "Total Liabilities Net Minority Interest",
        "Stockholders Equity", "Total Debt",
        "Current Assets", "Current Liabilities",
        "Cash And Cash Equivalents", "Net Tangible Assets",
        "Working Capital", "Invested Capital",
    ]
    for item in key_items:
        if item in bs.index:
            val = latest[item]
            if hasattr(val, "iloc"):
                val = float(val.iloc[0]) if len(val) > 0 else 0
            output += f"  {item}: {float(val):,.0f}\n"

    return output


@tool
def get_cashflow(
    symbol: Annotated[str, "公司的股票代码"],
    freq: Annotated[str, "频率: quarterly 或 annual"] = "quarterly",
) -> str:
    """获取公司现金流量表。包含经营现金流、自由现金流、资本支出等。"""
    import yfinance as yf

    ticker = yf.Ticker(symbol.upper())
    try:
        if freq == "annual":
            cf = ticker.cashflow
        else:
            cf = ticker.quarterly_cashflow
    except Exception:
        return f"未找到 {symbol.upper()} 的现金流量表数据"

    if cf is None or cf.empty:
        return f"未找到 {symbol.upper()} 的现金流量表数据"

    latest = cf.iloc[:, 0]
    output = f"股票代码: {symbol.upper()}\n现金流量表 ({freq}, {str(cf.columns[0])[:10]}):\n\n"
    key_items = [
        "Operating Cash Flow", "Free Cash Flow",
        "Capital Expenditure", "Investing Cash Flow",
        "Financing Cash Flow", "End Cash Position",
        "Changes In Cash", "Issuance Of Debt",
        "Repayment Of Debt", "Repurchase Of Capital Stock",
    ]
    for item in key_items:
        if item in cf.index:
            val = latest[item]
            if hasattr(val, "iloc"):
                val = float(val.iloc[0]) if len(val) > 0 else 0
            output += f"  {item}: {float(val):,.0f}\n"

    return output


@tool
def get_income_statement(
    symbol: Annotated[str, "公司的股票代码"],
    freq: Annotated[str, "频率: quarterly 或 annual"] = "quarterly",
) -> str:
    """获取公司利润表。包含营收、毛利、营业利润、净利润、EPS等。"""
    import yfinance as yf

    ticker = yf.Ticker(symbol.upper())
    try:
        if freq == "annual":
            income = ticker.financials
        else:
            income = ticker.quarterly_financials
    except Exception:
        return f"未找到 {symbol.upper()} 的利润表数据"

    if income is None or income.empty:
        return f"未找到 {symbol.upper()} 的利润表数据"

    latest = income.iloc[:, 0]
    output = f"股票代码: {symbol.upper()}\n利润表 ({freq}, {str(income.columns[0])[:10]}):\n\n"
    key_items = [
        "Total Revenue", "Cost Of Revenue", "Gross Profit",
        "Operating Income", "Net Income", "EBIT", "EBITDA",
        "Diluted EPS", "Research And Development",
        "Selling General And Administration",
        "Interest Expense", "Tax Provision",
    ]
    for item in key_items:
        if item in income.index:
            val = latest[item]
            if hasattr(val, "iloc"):
                val = float(val.iloc[0]) if len(val) > 0 else 0
            output += f"  {item}: {float(val):,.0f}\n"

    return output


ALL_TOOLS = [
    get_price,
    get_indicators,
    get_fundamentals,
    get_news,
    get_sector,
    get_macro,
    get_sentiment,
    recall_memory,
    get_verified_market_snapshot,
    get_global_news,
    get_macro_indicators,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
]
