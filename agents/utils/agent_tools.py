from typing import Annotated, Optional

from langchain_core.tools import tool

from dataflow.service import DataService

# 创建 DataService 实例
_data_service = DataService()


@tool
def get_price(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    lookback_days: Annotated[int, "回溯天数，例如 30 表示最近30天的数据"] = 30,
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则使用当前日期",
    ] = None,
) -> str:
    """
    获取指定股票代码的股价数据（OHLCV）。
    参数:
        symbol (str): 公司的股票代码，例如 AAPL, TSM
        lookback_days (int): 回溯天数，默认30天，例如 30 表示最近30天的数据
        end_date (str, optional): 结束日期（ISO格式），如果为None则使用当前日期
    返回:
        str: 包含指定股票代码在指定天数范围内的股价数据的格式化字符串。
    """
    result = _data_service.df_get_prices(symbol, lookback_days, end_date=end_date)

    # 检查是否获取到数据
    if not result or not result.get("rows"):
        return f"未找到股票代码 {symbol} 在最近 {lookback_days} 天的数据"

    # 格式化输出
    ticker = result.get("ticker", symbol)
    tz = result.get("tz", "Unknown")
    rows = result.get("rows", [])

    # 构建格式化的字符串
    output = f"股票代码: {ticker}\n时区: {tz}\n数据条数: {len(rows)}\n\n"
    output += "日期\t\t开盘价\t最高价\t最低价\t收盘价\t成交量\n"
    output += "-" * 70 + "\n"

    for row in rows:
        ts = row.get("ts", "")[:10]  # 只取日期部分
        o = row.get("o", 0)
        h = row.get("h", 0)
        l = row.get("l", 0)
        c = row.get("c", 0)
        v = int(row.get("v", 0))
        output += f"{ts}\t{o:.2f}\t{h:.2f}\t{l:.2f}\t{c:.2f}\t{v:,}\n"

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
    """
    获取指定股票代码的技术指标。
    参数:
        symbol (str): 公司的股票代码，例如 AAPL, TSM
        lookback_days (int): 回溯天数，默认30天，例如 30 表示最近30天的数据
        end_date (str, optional): 结束日期（ISO格式），如果为None则使用当前日期
    返回:
        str: 包含指定股票代码技术指标的格式化字符串。
    """
    result = _data_service.df_get_indicators(symbol, lookback_days, end_date=end_date)

    # 检查是否获取到数据
    if not result:
        return f"未找到股票代码 {symbol} 的技术指标数据"

    # 构建格式化的字符串
    output = f"股票代码: {symbol}\n技术指标数据:\n\n"

    # RSI指标
    if "rsi14" in result:
        rsi = result.get("rsi14")
        if rsi is not None:
            output += f"RSI(14): {rsi:.2f}\n"

    # MACD指标
    if "macd" in result:
        macd = result.get("macd", {})
        if macd:
            hist = macd.get("hist")
            signal_cross = macd.get("signal_cross", False)
            if hist is not None:
                output += f"MACD 柱状图: {hist:.4f}\n"
            output += f"MACD 信号交叉: {'是' if signal_cross else '否'}\n"

    # 移动平均线
    if "ma" in result:
        ma = result.get("ma", {})
        if ma:
            sma20 = ma.get("sma20")
            sma50 = ma.get("sma50")
            if sma20 is not None:
                output += f"SMA(20): {sma20:.2f}\n"
            if sma50 is not None:
                output += f"SMA(50): {sma50:.2f}\n"

    # ATR指标
    if "atr20" in result:
        atr = result.get("atr20")
        if atr is not None:
            output += f"ATR(20): {atr:.4f}\n"

    # 支撑/阻力位
    if "levels" in result:
        levels = result.get("levels", {})
        if levels:
            support = levels.get("support")
            resistance = levels.get("resistance")
            if support is not None:
                output += f"支撑位: {support:.2f}\n"
            if resistance is not None:
                output += f"阻力位: {resistance:.2f}\n"

    # 突破信息
    if "breakout" in result:
        breakout = result.get("breakout", {})
        if breakout:
            level = breakout.get("level")
            distance_pct = breakout.get("distance_pct")
            if level is not None:
                output += f"突破位: {level:.2f}\n"
            if distance_pct is not None:
                output += f"突破距离: {distance_pct:.2f}%\n"

    return output


@tool
def get_fundamentals(
    symbol: Annotated[str, "公司的股票代码，例如 AAPL, TSM"],
    end_date: Annotated[
        Optional[str],
        "结束日期（ISO格式，例如 2024-01-15T00:00:00Z），如果为None则获取实时数据，否则获取历史数据",
    ] = None,
) -> str:
    """
    获取指定股票代码的基本面数据。
    参数:
        symbol (str): 公司的股票代码，例如 AAPL, TSM
        end_date (str, optional): 结束日期（ISO格式），如果为None则获取实时数据，否则获取历史数据
    返回:
        str: 包含指定股票代码基本面数据的格式化字符串。
    """
    result = _data_service.df_get_fundamentals(symbol, end_date=end_date)

    # 检查是否获取到数据
    if not result:
        return f"未找到股票代码 {symbol} 的基本面数据"

    # 构建格式化的字符串
    output = f"股票代码: {symbol}\n基本面数据:\n\n"

    # TTM (过去12个月) 估值指标和盈利能力
    if "ttm" in result:
        ttm = result.get("ttm", {})
        if ttm:
            # 估值指标
            pe = ttm.get("pe")
            pb = ttm.get("pb")
            ps = ttm.get("ps")
            ev_ebitda = ttm.get("ev_ebitda")
            eps = ttm.get("eps")
            gross_margin = ttm.get("gross_margin")
            op_margin = ttm.get("op_margin")

            # 如果有估值指标，显示估值指标部分
            if any(x is not None for x in [pe, pb, ps, ev_ebitda, eps]):
                output += "【估值指标 (TTM)】\n"
                if pe is not None:
                    output += f"  市盈率 (PE): {pe:.2f}\n"
                if pb is not None:
                    output += f"  市净率 (PB): {pb:.2f}\n"
                if ps is not None:
                    output += f"  市销率 (PS): {ps:.2f}\n"
                if ev_ebitda is not None:
                    output += f"  企业价值倍数 (EV/EBITDA): {ev_ebitda:.2f}\n"
                if eps is not None:
                    output += f"  每股收益 (EPS): {eps:.2f}\n"
                output += "\n"

            # 如果有盈利能力指标，显示盈利能力部分
            if gross_margin is not None or op_margin is not None:
                output += "【盈利能力】\n"
                if gross_margin is not None:
                    output += f"  毛利率: {gross_margin:.2f}%\n"
                if op_margin is not None:
                    output += f"  营业利润率: {op_margin:.2f}%\n"
                output += "\n"

    # 增长指标
    if "growth" in result:
        growth = result.get("growth", {})
        if growth:
            eps_yoy = growth.get("eps_yoy")
            rev_yoy = growth.get("rev_yoy")

            if eps_yoy is not None or rev_yoy is not None:
                output += "【增长指标】\n"
                if eps_yoy is not None:
                    output += f"  EPS 同比增长率: {eps_yoy:.2f}%\n"
                if rev_yoy is not None:
                    output += f"  营收同比增长率: {rev_yoy:.2f}%\n"
                output += "\n"

    # 资产负债表指标
    if "balance" in result:
        balance = result.get("balance", {})
        if balance:
            net_debt_to_ebitda = balance.get("net_debt_to_ebitda")

            if net_debt_to_ebitda is not None:
                output += "【财务健康度】\n"
                output += f"  净债务/EBITDA: {net_debt_to_ebitda:.2f}\n"
                output += "\n"

    # 行业基准
    if "sector_bench" in result:
        sector_bench = result.get("sector_bench", {})
        if sector_bench:
            sector_pe = sector_bench.get("pe")

            if sector_pe is not None:
                output += "【行业基准】\n"
                output += f"  行业市盈率: {sector_pe:.2f}\n"

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
    """
    获取指定股票代码的新闻数据。
    参数:
        symbol (str): 公司的股票代码，例如 AAPL, TSM
        window_days (int): 窗口天数，默认7天，例如 7 表示最近7天的数据
        end_date (str, optional): 结束日期（ISO格式），如果为None则使用当前日期
    返回:
        str: 包含指定股票代码新闻数据的格式化字符串。
    """
    result = _data_service.df_get_news(
        symbol, window_days=window_days, end_date=end_date
    )

    # 检查是否获取到数据
    if not result:
        return f"未找到股票代码 {symbol} 在最近 {window_days} 天的新闻"

    # 构建格式化的字符串
    output = f"股票代码: {symbol}\n新闻数据 (最近 {window_days} 天):\n共找到 {len(result)} 条新闻\n\n"
    output += "-" * 80 + "\n"

    for idx, news in enumerate(result, 1):
        title = news.get("title", "无标题")
        summary = news.get("summary", "")
        source = news.get("source", "未知来源")
        published_at = news.get("published_at", "")
        url = news.get("url", "")

        # 格式化日期
        date_str = (
            published_at[:10]
            if published_at and len(published_at) >= 10
            else "未知日期"
        )

        output += f"【新闻 {idx}】\n"
        output += f"标题: {title}\n"
        if summary:
            # 限制摘要长度，避免输出过长
            summary_short = summary[:200] + "..." if len(summary) > 200 else summary
            output += f"摘要: {summary_short}\n"
        output += f"来源: {source}\n"
        output += f"发布时间: {date_str}\n"
        if url:
            output += f"链接: {url}\n"
        output += "-" * 80 + "\n"

    return output
