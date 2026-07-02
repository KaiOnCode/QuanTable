# dataflow/service.py
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .portfolio_manager import PortfolioManager
from .providers.fundamentals_akshare import df_get_fundamentals_pit
from .providers.macro_calendar import df_get_macro_calendar
from .providers.news_akshare import get_company_news_akshare
from .providers.news_google import get_company_news
from .providers.YFinance import (
    df_get_fundamentals as df_get_fundamentals_live,
)
from .providers.YFinance import (
    df_get_indicators,
    df_get_news_yahoo,
    df_get_prices,
    df_get_sector_context,
)
from .store import MarketDataStore

if TYPE_CHECKING:
    from broker.gateway import BrokerGateway
    from broker.models import Position

ONLINE = os.getenv("ONLINE_DATA", "true").lower() == "true"
STORE_ENABLED = os.getenv("MARKET_DATA_STORE", "true").lower() == "true"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class DataService:
    def __init__(
        self,
        fallback_local_root: str = "data",
        broker: "BrokerGateway | None" = None,
    ):
        self.local_root = fallback_local_root
        self.portfolio_manager = PortfolioManager()
        self._broker = broker
        self._store: MarketDataStore | None = None

    @property
    def store(self) -> MarketDataStore:
        if self._store is None:
            self._store = MarketDataStore()
        return self._store

    def df_get_prices(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        获取价格
        """
        if ONLINE:
            data = df_get_prices(ticker, lookback_days, end_date=end_date)
            if data:
                if STORE_ENABLED:
                    try:
                        rows = data.get("rows", [])
                        if rows:
                            self.store.upsert_ohlcv(ticker, rows)
                    except Exception:
                        pass
                return data
        return {}

    def df_get_indicators(
        self,
        ticker: str,
        lookback_days: int = 180,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        获取技术指标
        """
        if ONLINE:
            data = df_get_indicators(ticker, lookback_days, end_date=end_date)
            if data:
                return data
        return {}

    def df_get_fundamentals(
        self,
        ticker: str,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        获取基本面数据。
        - 实时 (end_date=None): 使用 YFinance t.info (快照)
        - 历史 (end_date=...): 使用 AkShare TTM (回测)
        """
        if not ONLINE:
            return {}

        if end_date is None:
            data = df_get_fundamentals_live(ticker)
        else:
            data = df_get_fundamentals_pit(ticker, end_date)

        if data:
            if STORE_ENABLED:
                try:
                    as_of = end_date or _today_str()
                    self.store.upsert_fundamentals(ticker, as_of, data)
                except Exception:
                    pass
            return data
        return {}

    def df_get_sector_context(self, ticker: str) -> dict[str, Any]:
        """
        获取行业背景
        """
        if ONLINE:
            data = df_get_sector_context(ticker)
            if data:
                return data
        return {}

    def df_get_news(
        self,
        ticker: str,
        window_days: int = 7,
        max_items: int = 20,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        获取新闻
        """
        lang = os.getenv("NEWS_LANG", "en")
        if ONLINE:
            items = get_company_news(
                ticker,
                days=window_days,
                lang=lang,
                end_date=end_date,
            )

            if not items:
                items = get_company_news_akshare(
                    ticker,
                    days=window_days,
                    max_items=max_items,
                )

            if not items:
                items = df_get_news_yahoo(ticker, limit=max_items)

            if STORE_ENABLED and items:
                try:
                    self.store.add_news_articles(ticker, items[:max_items])
                except Exception:
                    pass
            return items[:max_items]
        return []

    def df_get_macro_calendar(self, window_days: int = 7) -> list[dict[str, Any]]:
        """
        获取宏观日历 (来自 Finnhub)
        """
        if ONLINE:
            items = df_get_macro_calendar(window_days=window_days)
            if items:
                return items

        return []

    def df_get_sentiment(
        self,
        ticker: str,
        window_days: int = 7,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """
        获取新闻情绪评分 [-1.0, 1.0]。
        Uses cache (SHA256 integrity, 4h TTL) and keyword-based aggregation.
        """
        from .providers.sentiment import df_get_sentiment

        return df_get_sentiment(
            ticker,
            window_days=window_days,
            end_date=end_date,
        )

    def df_get_policy_expectations(self) -> dict[str, Any]:
        """
        获取利率预期
        TODO: Integrate with CME FedWatch or similar source.
        """
        print("[DataService] df_get_policy_expectations not implemented.")
        return {}

    def df_get_position(self, ticker: str) -> dict[str, Any]:
        """
        获取当前持仓
        """
        if self._broker is not None:
            position = self._broker.get_position(ticker)
            if position is not None:
                return self._convert_broker_position(position)
        return self.portfolio_manager.get_position(ticker)

    def df_get_risk_limits(self) -> dict[str, Any]:
        """
        获取风险限额
        """
        return self.portfolio_manager.get_risk_limits()

    def _convert_broker_position(self, position: "Position") -> dict[str, Any]:
        account = self._broker.get_account() if self._broker is not None else None
        position_value = position.shares * position.avg_cost + position.unrealized_pnl
        qty_pct = position_value / account.equity if account and account.equity else 0.0
        return {
            "side": position.side.lower(),
            "qty_pct": qty_pct,
            "avg_cost": position.avg_cost,
            "meta": {
                "ignore_in_analysis": False,
            },
        }

    # -- Unified API (single entry point) ---------------------

    def get_prices(
        self, ticker: str, start_date: str, end_date: str | None = None
    ) -> list[dict[str, Any]]:
        """Get OHLCV bars for a date range. Fetches live from YFinance directly."""
        del end_date
        days = (
            datetime.now(timezone.utc)
            - datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        ).days

        if days <= 35:
            period = "1mo"
        elif days <= 100:
            period = "3mo"
        elif days <= 200:
            period = "6mo"
        elif days <= 400:
            period = "1y"
        elif days <= 800:
            period = "2y"
        elif days <= 2000:
            period = "5y"
        else:
            period = "max"

        import yfinance as yf

        ticker_data = yf.Ticker(ticker)
        df = ticker_data.history(period=period, interval="1d")
        if df is None or df.empty:
            return []

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        df["date"] = [
            idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            for idx in df.index
        ]

        bars: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            date_value = str(row.get("date", ""))
            if date_value >= start_date:
                bars.append(
                    {
                        "date": date_value,
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]),
                    }
                )
        return bars

    def get_news(self, ticker: str, window_days: int = 7) -> list[dict[str, Any]]:
        """Get recent news for a ticker. Fetches live if DB is empty."""
        articles = self.store.get_news(ticker, window_days=window_days)
        if articles:
            return articles
        self.df_get_news(ticker, window_days=window_days, max_items=10)
        return self.store.get_news(ticker, window_days=window_days)

    def search_news(
        self, query: str, ticker: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """FTS5 full-text search across news. Never triggers live fetch."""
        return self.store.search_news(query, ticker=ticker, limit=limit)

    def get_fundamentals(
        self, ticker: str, as_of_date: str | None = None
    ) -> dict[str, Any] | None:
        """Get latest fundamentals. Fetches live if missing, stale, or incomplete."""
        data = self.store.get_fundamentals(ticker, as_of_date)

        needs_fetch = data is None
        if not needs_fetch and data:
            fetched_at = data.get("fetched_at", "")
            if fetched_at:
                try:
                    fetched_dt = datetime.strptime(fetched_at[:10], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    if (datetime.now(timezone.utc) - fetched_dt).days >= 30:
                        needs_fetch = True
                except (ValueError, IndexError):
                    needs_fetch = True
            key_fields = [
                "market_cap",
                "roe",
                "dividend_yield",
                "profit_margin",
                "pe",
                "pb",
            ]
            if any(data.get(field) is None for field in key_fields):
                needs_fetch = True

        if needs_fetch:
            self.df_get_fundamentals(ticker)
            data = self.store.get_fundamentals(ticker, as_of_date)
        return data

    def get_meta(self, ticker: str) -> dict[str, Any] | None:
        """Get ticker metadata (name, currency, country, etc.). Fetches once."""
        meta = self.store.get_ticker_meta(ticker)
        if meta is None:
            try:
                import yfinance as yf

                info = yf.Ticker(ticker).info
                self.store.upsert_ticker_meta(
                    ticker,
                    name=info.get("longName") or "",
                    short_name=info.get("shortName") or "",
                    sector=info.get("sector") or "",
                    industry=info.get("industry") or "",
                    market=info.get("market") or "",
                    exchange=info.get("exchange") or "",
                    currency=info.get("currency") or "",
                    country=info.get("country") or "",
                )
                meta = self.store.get_ticker_meta(ticker)
            except Exception:
                pass
        return meta

    def get_indicators(self, ticker: str, lookback_days: int = 100) -> dict[str, Any]:
        """Get technical indicators computed from OHLCV data."""
        result = df_get_indicators(ticker, lookback_days)
        rows = result.get("_ohlcv_rows", []) if isinstance(result, dict) else []
        if rows and STORE_ENABLED:
            try:
                self.store.upsert_ohlcv(ticker, rows)
            except Exception:
                pass
        return result
