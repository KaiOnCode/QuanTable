# dataflow/service.py
import os
from typing import List, Dict, Any,Optional
from datetime import datetime, timezone

# 1. 导入新的 provider 函数
from .providers.YFinance import (
    df_get_prices,
    df_get_indicators,
    df_get_fundamentals as df_get_fundamentals_live,
    df_get_sector_context
)

from .providers.news_google import get_company_news
from .providers.news_akshare import get_company_news_akshare
from .portfolio_manager import PortfolioManager
from .providers.macro_calendar import df_get_macro_calendar
from .providers.fundamentals_akshare import df_get_fundamentals_pit
from .store import MarketDataStore

ONLINE = os.getenv("ONLINE_DATA", "true").lower() == "true"
STORE_ENABLED = os.getenv("MARKET_DATA_STORE", "true").lower() == "true"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class DataService:
    def __init__(self, fallback_local_root: str = "data"):
        self.local_root = fallback_local_root
        self.portfolio_manager = PortfolioManager()
        self._store: MarketDataStore | None = None

    @property
    def store(self) -> MarketDataStore:
        if self._store is None:
            self._store = MarketDataStore()
        return self._store

    # 2. 严格按照规范 v1.0 实现函数签名 [cite: 26-35]

    def df_get_prices(
            self,
            ticker: str,
            lookback_days: int = 180,
            # 更改：添加 end_date
            end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取价格
        """
        if ONLINE:
            data = df_get_prices(ticker, lookback_days, end_date=end_date)
            if data:
                # Persist to MarketDataStore for accumulation
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
        # 更改：添加 end_date
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取技术指标
        """
        if ONLINE:
            # 更改：传递 end_date
            data = df_get_indicators(ticker, lookback_days, end_date=end_date)
            if data:
                return data
        return {}

    # 3. (修改) df_get_fundamentals 现在是路由器
    def df_get_fundamentals(
            self,
            ticker: str,
            end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取基本面数据。
        - 实时 (end_date=None): 使用 YFinance t.info (快照) [cite: 173-174]
        - 历史 (end_date=...): 使用 AkShare TTM (回测)
        """
        if not ONLINE:
            return {}

        if end_date is None:
            # 路径 A: 实时交易，使用 YFinance 快照
            data = df_get_fundamentals_live(ticker)
        else:
            # 路径 B: 历史回测，使用 AkShare Point-in-Time
            data = df_get_fundamentals_pit(ticker, end_date)

        if data:
            # Persist to MarketDataStore
            if STORE_ENABLED:
                try:
                    as_of = end_date or _today_str()
                    self.store.upsert_fundamentals(ticker, as_of, data)
                except Exception:
                    pass
            return data
        return {}

    def df_get_sector_context(self, ticker: str) -> Dict[str, Any]:
        """
        获取行业背景 [cite: 33]
        """
        if ONLINE:
            data = df_get_sector_context(ticker)
            if data:
                return data
        return {}

    # --- 以下是规范中其他需要您实现的数据源 ---

    def df_get_news(
            self,
            ticker: str,
            window_days: int = 7,
            max_items: int = 20,
            # 更改：添加 end_date
            end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        获取新闻
        TODO: 您需要修改 news_google.py 来匹配这个签名和输出格式
        """
        lang = os.getenv("NEWS_LANG", "en")
        if ONLINE:
            # Try Google News first
            items = get_company_news(
                ticker,
                days=window_days,
                lang=lang,
                end_date=end_date
            )

            # Fallback to AkShare if Google News returns nothing
            if not items:
                items = get_company_news_akshare(
                    ticker,
                    days=window_days,
                    max_items=max_items,
                )

            # Persist to MarketDataStore for accumulation
            if STORE_ENABLED and items:
                try:
                    self.store.add_news_articles(ticker, items[:max_items])
                except Exception:
                    pass
            return items[:max_items]
        return []

    # 2. 添加新函数 (这个函数没有 ticker，它是全局的)
    def df_get_macro_calendar(self, window_days: int = 7) -> List[Dict]:
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
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
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

    def df_get_policy_expectations(self) -> Dict[str, Any]:
        """
        获取利率预期
        TODO: Integrate with CME FedWatch or similar source.
        """
        print("[DataService] df_get_policy_expectations not implemented.")
        return {}

    def df_get_position(self, ticker: str) -> Dict[str, Any]:
        """
        获取当前持仓 [cite: 34]
        TODO: 这可能需要连接到内部的持仓管理模块，暂时返回空仓
        """
        return self.portfolio_manager.get_position(ticker)

    def df_get_risk_limits(self) -> Dict[str, Any]:
        """
        获取风险限额
        TODO: 这应该从配置或上层读取，暂时硬编码
        """
        return self.portfolio_manager.get_risk_limits()