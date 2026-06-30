"""LangChain tools for agents — wraps DataService methods.

Now supports 8 tools (was 4):
    get_price, get_indicators, get_fundamentals, get_news,
    get_sector, get_macro, get_sentiment, recall_memory
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Optional

from langchain_core.tools import tool

from dataflow.service import DataService

_data_service = DataService()


def _struct(data: dict | list) -> str:
    """Return compact JSON alongside formatted text so tools output is
    both human-readable AND machine-parseable."""
    return json.dumps(data, ensure_ascii=False, default=str)


# ── 1. get_price (unchanged signature) ─────────────────────


@tool
def get_price(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    lookback_days: Annotated[int, "回溯天数，例如 30 表示最近30天的数据"] = 30,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """获取指定股票代码的股价数据（OHLCV）。"""
    result = _data_service.df_get_prices(symbol, lookback_days, end_date=end_date)

    if not result or not result.get("rows"):
        return f"未找到股票代码 {symbol} 在最近 {lookback_days} 天的数据"

    ticker = result.get("ticker", symbol)
    rows = result.get("rows", [])

    output = f"股票代码: {ticker}\n数据条数: {len(rows)}\n\n"
    output += "日期\t\t开盘价\t最高价\t最低价\t收盘价\t成交量\n"
    output += "-" * 70 + "\n"

    for row in rows:
        ts = row.get("ts", "")[:10]
        o = row.get("o", 0)
        h = row.get("h", 0)
        l = row.get("l", 0)  # noqa: E741
        c = row.get("c", 0)
        v = int(row.get("v", 0))
        output += f"{ts}\t{o:.2f}\t{h:.2f}\t{l:.2f}\t{c:.2f}\t{v:,}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 2. get_indicators ──────────────────────────────────────


@tool
def get_indicators(
    symbol: Annotated[str, "公司的股票代码"],
    lookback_days: Annotated[int, "回溯天数"] = 30,
    end_date: Annotated[Optional[str], "结束日期（ISO格式）"] = None,
) -> str:
    """获取指定股票代码的技术指标（RSI, MACD, SMA, ATR, 支撑/阻力）。"""
    result = _data_service.df_get_indicators(symbol, lookback_days, end_date=end_date)

    if not result:
        return f"未找到股票代码 {symbol} 的技术指标数据"

    output = f"股票代码: {symbol}\n技术指标数据:\n\n"

    if "rsi14" in result and result["rsi14"] is not None:
        rsi = result["rsi14"]
        rsi_label = "超卖" if rsi < 30 else "超买" if rsi > 70 else "中性"
        output += f"RSI(14): {rsi:.2f} ({rsi_label})\n"

    if "macd" in result and result["macd"]:
        macd = result["macd"]
        output += f"MACD 柱: {macd.get('hist', 0):.4f}\n"
        output += f"MACD 信号交叉: {'是' if macd.get('signal_cross') else '否'}\n"

    if "ma" in result and result["ma"]:
        ma = result["ma"]
        if ma.get("sma20"):
            output += f"SMA(20): {ma['sma20']:.2f}\n"
        if ma.get("sma50"):
            output += f"SMA(50): {ma['sma50']:.2f}\n"

    if "atr20" in result and result["atr20"] is not None:
        output += f"ATR(20): {result['atr20']:.4f}\n"

    if "levels" in result and result["levels"]:
        levels = result["levels"]
        if levels.get("support"):
            output += f"支撑位: {levels['support']:.2f}\n"
        if levels.get("resistance"):
            output += f"阻力位: {levels['resistance']:.2f}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 3. get_fundamentals ────────────────────────────────────


@tool
def get_fundamentals(
    symbol: Annotated[str, "公司的股票代码"],
    end_date: Annotated[Optional[str], "结束日期（ISO格式）"] = None,
) -> str:
    """获取指定股票代码的基本面数据（PE/PB/ROE/增长/估值）。"""
    result = _data_service.df_get_fundamentals(symbol, end_date=end_date)

    if not result:
        return f"未找到股票代码 {symbol} 的基本面数据"

    output = f"股票代码: {symbol}\n基本面数据:\n\n"

    ttm = result.get("ttm", {})
    if ttm:
        output += "【估值指标 (TTM)】\n"
        if ttm.get("pe") is not None:
            output += f"  PE: {ttm['pe']:.2f}\n"
        if ttm.get("pb") is not None:
            output += f"  PB: {ttm['pb']:.2f}\n"
        if ttm.get("ps") is not None:
            output += f"  PS: {ttm['ps']:.2f}\n"
        if ttm.get("eps") is not None:
            output += f"  EPS: {ttm['eps']:.2f}\n"
        if ttm.get("gross_margin") is not None:
            output += f"  毛利率: {ttm['gross_margin']:.2f}%\n"
        output += "\n"

    growth = result.get("growth", {})
    if growth:
        output += "【增长指标】\n"
        if growth.get("eps_yoy") is not None:
            output += f"  EPS 同比增长: {growth['eps_yoy']:.2f}%\n"
        if growth.get("rev_yoy") is not None:
            output += f"  营收同比增长: {growth['rev_yoy']:.2f}%\n"
        output += "\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 4. get_news ────────────────────────────────────────────


@tool
def get_news(
    symbol: Annotated[str, "公司的股票代码"],
    window_days: Annotated[int, "窗口天数"] = 7,
    end_date: Annotated[Optional[str], "结束日期（ISO格式）"] = None,
) -> str:
    """获取指定股票代码的新闻数据。"""
    result = _data_service.df_get_news(
        symbol, window_days=window_days, end_date=end_date
    )

    if not result:
        return f"未找到股票代码 {symbol} 在最近 {window_days} 天的新闻"

    output = (
        f"股票代码: {symbol}\n新闻 (最近 {window_days} 天): "
        f"共 {len(result)} 条\n" + "-" * 80 + "\n"
    )

    for idx, news in enumerate(result, 1):
        title = news.get("title", "无标题")
        summary = news.get("summary", "")
        source = news.get("source", "未知来源")
        date_str = (news.get("published_at") or "")[:10] or "未知日期"
        output += f"【{idx}】{title}\n"
        if summary:
            output += f"  摘要: {summary[:200]}\n"
        output += f"  来源: {source} | {date_str}\n"
        output += "-" * 80 + "\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 5. get_sector (NEW) ────────────────────────────────────


@tool
def get_sector(
    symbol: Annotated[str, "公司的股票代码"],
) -> str:
    """获取指定股票代码的行业背景和同行比较数据。"""
    result = _data_service.df_get_sector_context(symbol)

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


# ── 6. get_macro (NEW) ─────────────────────────────────────


@tool
def get_macro(
    window_days: Annotated[int, "窗口天数"] = 7,
) -> str:
    """获取全球经济日历——CPI、FOMC、失业率等宏观事件。"""
    result = _data_service.df_get_macro_calendar(window_days=window_days)

    if not result:
        return f"最近 {window_days} 天无宏观事件"

    output = f"宏观日历 (未来 {window_days} 天):\n共 {len(result)} 个事件\n\n"
    output += "日期\t\t事件\t\t重要性\n"
    output += "-" * 60 + "\n"

    for ev in result:
        date = (ev.get("date") or "")[:10]
        event = ev.get("event", "")[:30]
        impact = ev.get("impact", "medium")
        output += f"{date}\t{event}\t{impact}\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 7. get_sentiment (NEW) ─────────────────────────────────


@tool
def get_sentiment(
    symbol: Annotated[str, "公司的股票代码"],
    window_days: Annotated[int, "窗口天数，默认 7"] = 7,
) -> str:
    """获取指定股票代码的新闻情绪评分（-1.0 到 1.0）。"""
    from dataflow.providers.sentiment import df_get_sentiment

    result = df_get_sentiment(symbol, window_days=window_days)

    if result["article_count"] == 0:
        return f"未找到 {symbol} 的情绪数据——最近 {window_days} 天无相关新闻"

    score = result["score"]
    label = "看多" if score > 0.1 else "看空" if score < -0.1 else "中性"

    output = (
        f"股票代码: {symbol}\n"
        f"情绪评分: {score:.2f} ({label})\n"
        f"置信度: {result['confidence']:.2f}\n"
        f"新闻条数: {result['article_count']}\n"
        f"关键词: {', '.join(result['top_keywords'][:5])}\n"
    )
    output += f"\n<!-- JSON: {_struct(result)} -->"
    return output


# ── 8. recall_memory (NEW) ─────────────────────────────────


@tool
def recall_memory(
    symbol: Annotated[str, "公司的股票代码"],
    limit: Annotated[int, "最多返回的记录数"] = 5,
) -> str:
    """从策略记忆中检索相关的历史交易记录和经验教训。

    返回按 OWM 分数排序的过往决策，帮助 PM 利用历史经验。
    """
    from memory.store import MemoryStore

    store = MemoryStore("data/memory.db")
    records = store.recall(ticker=symbol, limit=limit, min_score=0.0)

    if not records:
        return f"未找到 {symbol} 的相关历史记忆"

    output = f"股票代码: {symbol}\n相关历史记忆 ({len(records)} 条):\n\n"

    for i, rec in enumerate(records, 1):
        output += f"【记忆 {i}】OWM: {rec.owm_score:.2f}\n"
        output += f"  {rec.episodic[:200]}\n"
        if rec.semantic:
            output += f"  规则: {rec.semantic[:150]}\n"
        output += "\n"

    output += f"<!-- JSON: {_struct([r.model_dump() for r in records])} -->"
    return output


# ── Tool list for auto-discovery ────────────────────────────

ALL_TOOLS = [
    get_price,
    get_indicators,
    get_fundamentals,
    get_news,
    get_sector,
    get_macro,
    get_sentiment,
    recall_memory,
]
