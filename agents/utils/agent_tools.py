from __future__ import annotations

import json
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
    """获取指定股票代码的股价数据（OHLCV）。"""
    result = get_data_service().df_get_prices(symbol, lookback_days, end_date=end_date)

    if not result or not result.get("rows"):
        return f"未找到股票代码 {symbol} 在最近 {lookback_days} 天的数据"

    ticker = result.get("ticker", symbol)
    tz = result.get("tz")
    rows = result.get("rows", [])

    output = f"股票代码: {ticker}\n"
    if tz:
        output += f"时区: {tz}\n"
    output += f"数据条数: {len(rows)}\n\n"
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
    """获取指定股票代码的技术指标。"""
    result = get_data_service().df_get_indicators(
        symbol, lookback_days, end_date=end_date
    )

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
    """获取指定股票代码的基本面数据。"""
    result = get_data_service().df_get_fundamentals(symbol, end_date=end_date)

    if not result:
        return f"未找到股票代码 {symbol} 的基本面数据"

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


@tool
def get_news(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    window_days: Annotated[int, "窗口天数，例如 7 表示最近7天的数据"] = 7,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """获取指定股票代码的新闻数据。"""
    result = get_data_service().df_get_news(
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
        published_at = news.get("published_at", "")
        url = news.get("url", "")
        date_str = (
            published_at[:10]
            if published_at and len(published_at) >= 10
            else "未知日期"
        )
        output += f"【{idx}】{title}\n"
        if summary:
            summary_short = summary[:200] + "..." if len(summary) > 200 else summary
            output += f"  摘要: {summary_short}\n"
        output += f"  来源: {source} | {date_str}\n"
        if url:
            output += f"  链接: {url}\n"
        output += "-" * 80 + "\n"

    output += f"\n<!-- JSON: {_struct(result)} -->"
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
