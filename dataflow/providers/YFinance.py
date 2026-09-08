# dataflow/providers/YFinance.py
import math
from datetime import datetime, timedelta, timezone
from typing import Any, cast, Dict, Hashable, Optional

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
    # Accept an optional datetime object for point-in-time queries
    end_date_dt: Optional[datetime] = None,
) -> pd.DataFrame:
    """Fetch raw price history and clean the DataFrame."""
    t = yf.Ticker(ticker)

    # Default to now if no end_date_dt provided
    end_date = end_date_dt or datetime.now(timezone.utc).replace(tzinfo=None)
    start_date = end_date - timedelta(days=lookback_days)

    # +100 days buffer for technical indicator warmup
    df = t.history(
        start=start_date - timedelta(days=100),
        end=end_date,
        interval="1d",
        auto_adjust=True,
        actions=False,
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
    df = cast(
        pd.DataFrame,
        df[["open", "high", "low", "close", "volume"]].reset_index(),
    )
    index_column = cast(Hashable, df.columns[0])
    df = df.rename(columns={index_column: "date"})
    return df


def df_get_prices(
    ticker: str,
    lookback_days: int,
    # Accept optional end_date parameter (ISO format string)
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch OHLCV data online — matches agent_design v1.0 spec [cite: 127, 138]
    """
    t = yf.Ticker(ticker)
    try:
        tz = t.info.get("exchangeTimezoneName", "America/New_York")
    except Exception:
        tz = "America/New_York"  # fallback

    # Parse end_date string
    end_date_dt: Optional[datetime] = None
    if end_date:
        try:
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError as error:
            raise ValueError("invalid historical end_date") from error

    df = _get_price_history(ticker, lookback_days, end_date_dt=end_date_dt)
    if df.empty:
        return {}

    # cutoff_date is now relative to end_date
    cutoff_date = (end_date_dt or datetime.utcnow()) - timedelta(days=lookback_days)
    df = cast(pd.DataFrame, df.loc[df["date"] >= cutoff_date])
    if end_date_dt is not None:
        df = cast(pd.DataFrame, df.loc[df["date"] < end_date_dt])

    rows: list[dict[str, Any]] = []
    for row in cast(list[dict[str, Any]], df.to_dict(orient="records")):
        trading_timestamp = cast(pd.Timestamp, pd.Timestamp(row["date"]))
        rows.append(
            {
                "ts": trading_timestamp.isoformat() + "Z",
                "o": row["open"],
                "h": row["high"],
                "l": row["low"],
                "c": row["close"],
                "v": row["volume"],
            }
        )

    return {"ticker": ticker, "tz": tz, "rows": rows}


def df_get_indicators(
    ticker: str,
    lookback_days: int,
    # Accept optional end_date parameter
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute and fetch technical indicators — matches agent_design v1.0 spec
    """
    # Parse end_date string
    end_date_dt: Optional[datetime] = None
    if end_date:
        try:
            end_date_dt = datetime.fromisoformat(end_date.rstrip("Z"))
        except ValueError:
            print(f"[yfinance] Cannot parse end_date: {end_date}. Falling back to latest.")

    # Pass end_date_dt through to price history
    df_prices = _get_price_history(ticker, lookback_days + 100, end_date_dt=end_date_dt)
    if df_prices.empty or len(df_prices) < 50:  # ensure sufficient data
        return {}

    close = cast(pd.Series, df_prices["close"])
    high = cast(pd.Series, df_prices["high"])
    low = cast(pd.Series, df_prices["low"])

    # Explicitly call pandas_ta to avoid relying on implicit DataFrame.ta accessor registration.
    df_prices["RSI_14"] = ta.rsi(close, length=14)
    df_prices["SMA_20"] = ta.sma(close, length=20)
    df_prices["SMA_50"] = ta.sma(close, length=50)
    df_prices["ATRr_20"] = ta.atr(
        high=high,
        low=low,
        close=close,
        length=20,
    )

    macd = ta.macd(close, fast=12, slow=26, signal=9)
    if macd is not None:
        df_prices = df_prices.join(macd)

    # Get latest values
    latest = df_prices.iloc[-1]
    prev = df_prices.iloc[-2]

    # Compute support/resistance (simple implementation)
    # TODO: replace with pivot points or more sophisticated algorithm
    window_df = df_prices.iloc[-30:]  # last 30 days
    support = window_df["low"].min()
    resistance = window_df["high"].max()

    # Check MACD signal line crossover [cite: 50]
    signal_cross = False
    if not (
        math.isnan(latest["MACD_12_26_9"])
        or math.isnan(latest["MACDs_12_26_9"])
        or math.isnan(prev["MACD_12_26_9"])
        or math.isnan(prev["MACDs_12_26_9"])
    ):
        # Bullish cross detection
        if (
            latest["MACD_12_26_9"] > latest["MACDs_12_26_9"]
            and prev["MACD_12_26_9"] < prev["MACDs_12_26_9"]
        ):
            signal_cross = True  # Bullish cross
        # Bearish cross detection (not yet implemented per spec)

    # Assemble JSON per spec [cite: 48-55]
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
    # Clean None and NaN values
    indicators = {
        k: v
        for k, v in indicators.items()
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    }

    # Include raw OHLCV rows so callers can store to DB
    ohlcv_rows = []
    for _, row in df_prices.iterrows():
        date_source: Any = row.get("date")
        date_value = (
            date_source.strftime("%Y-%m-%d")
            if hasattr(date_source, "strftime")
            else str(date_source)[:10]
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
    Fetch core fundamental data from Yahoo Finance.
    Primarily used to support FundAnalyst.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info

        if not info:
            return {}

        # Helper to safely convert percentage values
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
                # 'earningsGrowth' maps to EPS YOY, 'revenueGrowth' maps to Rev YOY
                "eps_yoy": to_pct("earningsGrowth"),
                "rev_yoy": to_pct("revenueGrowth"),
            },
            "balance": {"net_debt_to_ebitda": info.get("netDebtToEbitda")},
            "sector_bench": {
                "pe": info.get("sectorPERatio")  # yfinance does not have sector PB/PS
            },
        }

        # Remove empty sub-dicts
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
    Fetch sector and style labels — matches agent_design v1.0 spec
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        if not info:
            return {}

        return {
            "industry": info.get("industry"),
            "style": None,  # 'style' is not a standard yfinance field
        }
    except Exception as e:
        print(f"[yfinance] Error fetching sector context for {ticker}: {e}")
        return {}
