# dataflow/providers/YFinance.py
import math
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd
import pandas_ta as ta
import yfinance as yf


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_price_history(
    ticker: str,
    lookback_days: int,
    interval: str = "1d",
    # 更改：接受一个可选的 datetime 对象
    end_date_dt: Optional[datetime] = None,
) -> pd.DataFrame:
    """辅助函数：获取原始价格历史并清理"""
    t = yf.Ticker(ticker)

    # 更改：如果未提供 end_date_dt，则默认为 "now"
    end_date = end_date_dt or datetime.utcnow()
    start_date = end_date - timedelta(days=lookback_days)

    # +100天是为了给技术指标计算留足缓冲期
    df = t.history(
        start=start_date - timedelta(days=100), end=end_date, interval=interval
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df[["open", "high", "low", "close", "volume"]].reset_index(names="date")
    return df


def df_get_prices(
    ticker: str,
    lookback_days: int,
    # 更改：添加可选的 end_date 参数 (ISO 格式字符串)
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    在线获取OHLCV - 匹配 agent_design v1.0 规范 [cite: 127, 138]
    """
    t = yf.Ticker(ticker)
    try:
        tz = t.info.get("exchangeTimezoneName", "America/New_York")
    except Exception:
        tz = "America/New_York"  # 兜底

    # 更改：解析 end_date 字符串
    end_date_dt: Optional[datetime] = None
    if end_date:
        try:
            # 假设 end_date 是 "YYYY-MM-DDTHH:MM:SSZ" 格式
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError:
            print(f"[yfinance] 无法解析 end_date: {end_date}. 回退到最新时间。")

    df = _get_price_history(ticker, lookback_days, end_date_dt=end_date_dt)
    if df.empty:
        return {}

    # 更改：cutoff_date 现在基于 end_date
    cutoff_date = (end_date_dt or datetime.utcnow()) - timedelta(days=lookback_days)
    df = df[df["date"] >= cutoff_date]

    rows = []
    for row in df.itertuples():
        rows.append(
            {
                "ts": row.date.isoformat() + "Z",  # 匹配规范 [cite: 144]
                "o": row.open,
                "h": row.high,
                "l": row.low,
                "c": row.close,
                "v": row.volume,
            }
        )

    return {"ticker": ticker, "tz": tz, "rows": rows}


def df_get_indicators(
    ticker: str,
    lookback_days: int,
    # 更改：添加可选的 end_date 参数
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    计算并获取技术指标 - 匹配 agent_design v1.0 规范
    """
    # 更改：解析 end_date 字符串
    end_date_dt: Optional[datetime] = None
    if end_date:
        try:
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError:
            print(f"[yfinance] 无法解析 end_date: {end_date}. 回退到最新时间。")

    # 更改：传递 end_date_dt
    df_prices = _get_price_history(ticker, lookback_days + 100, end_date_dt=end_date_dt)
    if df_prices.empty or len(df_prices) < 50:  # 确保有足够数据
        return {}

    # 显式调用 pandas_ta，避免依赖 DataFrame.ta accessor 的隐式注册。
    df_prices["RSI_14"] = ta.rsi(df_prices["close"], length=14)
    df_prices["SMA_20"] = ta.sma(df_prices["close"], length=20)
    df_prices["SMA_50"] = ta.sma(df_prices["close"], length=50)
    df_prices["ATRr_20"] = ta.atr(
        high=df_prices["high"],
        low=df_prices["low"],
        close=df_prices["close"],
        length=20,
    )

    macd = ta.macd(df_prices["close"], fast=12, slow=26, signal=9)
    if macd is not None:
        df_prices = df_prices.join(macd)

    # 2. 获取最近的值
    latest = df_prices.iloc[-1]
    prev = df_prices.iloc[-2]

    # 3. 计算支撑/阻力 (简易实现)
    # TODO: 替换为更复杂的算法，例如 pivot points
    window_df = df_prices.iloc[-30:]  # 近30天
    support = window_df["low"].min()
    resistance = window_df["high"].max()

    # 4. 检查 MACD 信号线交叉 [cite: 50]
    signal_cross = False
    if not (
        math.isnan(latest["MACD_12_26_9"])
        or math.isnan(latest["MACDs_12_26_9"])
        or math.isnan(prev["MACD_12_26_9"])
        or math.isnan(prev["MACDs_12_26_9"])
    ):
        # 简易金叉检测
        if (
            latest["MACD_12_26_9"] > latest["MACDs_12_26_9"]
            and prev["MACD_12_26_9"] < prev["MACDs_12_26_9"]
        ):
            signal_cross = True  # Bullish cross
        # 简易死叉检测
        # if latest['MACD_12_26_9'] < latest['MACDs_12_26_9'] and prev['MACD_12_26_9'] > prev['MACDs_12_26_9']:
        #    signal_cross = "Bearish" # 规范未定义，暂用 True/False

    # 5. 组装成规范要求的JSON [cite: 48-55]
    indicators = {
        "rsi14": latest.get("RSI_14"),
        "macd": {"hist": latest.get("MACDh_12_26_9"), "signal_cross": signal_cross},
        "ma": {"sma20": latest.get("SMA_20"), "sma50": latest.get("SMA_50")},
        "atr20": latest.get("ATRr_20"),
        "levels": {"support": support, "resistance": resistance},
        "breakout": {
            "level": None,
            "distance_pct": None,
        },
    }
    # 清理 None 和 NaN
    indicators = {
        k: v
        for k, v in indicators.items()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }

    # Include raw OHLCV rows so callers can store to DB
    ohlcv_rows = []
    for idx, row in df_prices.iterrows():
        idx_value: Any = idx
        date_value = (
            idx_value.strftime("%Y-%m-%d")
            if hasattr(idx_value, "strftime")
            else str(idx_value)[:10]
        )
        ohlcv_rows.append(
            {
                "date": date_value,
                "open": _to_float(row.get("open")),
                "high": _to_float(row.get("high")),
                "low": _to_float(row.get("low")),
                "close": _to_float(row.get("close")),
                "volume": _to_float(row.get("volume")),
            }
        )
    indicators["_ohlcv_rows"] = ohlcv_rows

    return indicators


def df_get_fundamentals(ticker: str) -> dict:
    """
    在线获取核心基本面数据（Yahoo Finance）
    主要用于支持 FundAnalyst。
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info

        if not info:
            return {}

        # 辅助函数，安全地转换百分比
        def to_pct(key, default=None):
            val = info.get(key)
            return val * 100 if isinstance(val, (int, float)) else default

        data = {
            "ttm": {
                "pe": info.get("trailingPE"),
                "pb": info.get("priceToBook"),
                "ps": info.get("priceToSalesTrailing12Months"),
                "ev_ebitda": info.get("enterpriseToEbitda"),
                "eps": info.get("trailingEps"),
                "market_cap": info.get("marketCap"),
                "roe": to_pct("returnOnEquity"),
                "dividend_yield": to_pct("dividendYield"),
                "profit_margin": to_pct("profitMargins"),
                "gross_margin": to_pct("grossMargins"),
                "op_margin": to_pct("operatingMargins"),
            },
            "growth": {
                # 'earningsGrowth' 对应 EPS YOY, 'revenueGrowth' 对应 Rev YOY
                "eps_yoy": to_pct("earningsGrowth"),
                "rev_yoy": to_pct("revenueGrowth"),
            },
            "balance": {"net_debt_to_ebitda": info.get("netDebtToEbitda")},
            "sector_bench": {
                "pe": info.get("sectorPERatio")  # yfinance 似乎没有行业 PB/PS
            },
        }

        # 清理空字典
        data = {k: v for k, v in data.items() if v}
        return data

    except Exception as e:
        print(f"[yfinance] Error fetching fundamentals for {ticker}: {e}")
        return {}


def df_get_news_yahoo(ticker: str, limit: int = 20) -> list[dict]:
    """Fetch news from Yahoo Finance via yf.Ticker.news.

    Returns structured JSON directly — no HTML scraping needed.
    Each article has: title, link, publisher, providerPublishTime, thumbnail.
    """
    try:
        t = yf.Ticker(ticker)
        raw = t.news or []
        articles = []
        for item in raw[:limit]:
            content = item.get("content", {}) or {}
            pub_time = (
                content.get("pubDate") or content.get("providerPublishTime") or ""
            )
            if pub_time and isinstance(pub_time, (int, float)):
                from datetime import datetime, timezone

                pub_time = datetime.fromtimestamp(pub_time, tz=timezone.utc).isoformat()
            articles.append(
                {
                    "title": content.get("title", "") or item.get("title", ""),
                    "summary": content.get("summary", "") or "",
                    "url": content.get("canonicalUrl", {}) or {},
                    "source_name": content.get("provider", {}).get("displayName", "")
                    if isinstance(content.get("provider"), dict)
                    else "",
                    "published_at": str(pub_time) if pub_time else "",
                }
            )
            # Normalize url field
            if isinstance(articles[-1]["url"], dict):
                articles[-1]["url"] = articles[-1]["url"].get("url", "") or ""
        return [a for a in articles if a["title"]]
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.warning("[yfinance] News fetch failed for %s: %s", ticker, exc)
        return []


def df_get_sector_context(ticker: str) -> Dict[str, Any]:
    """
    获取行业与风格标签 - 匹配 agent_design v1.0 规范
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info:
            return {}

        return {
            "industry": info.get("industry"),
            "style": None,  # 'style' (e.g., "growth_duration") 不是 yfinance 的标准字段
        }
    except Exception as e:
        print(f"[yfinance] Error fetching sector context for {ticker}: {e}")
        return {}
