"""AkShare news provider — mainland China accessible, no VPN needed.

Uses East Money (东方财富) as the underlying source via AkShare's
stock_news_em() function. Returns news in Chinese.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any


def get_company_news_akshare(
    ticker: str,
    days: int = 7,
    max_items: int = 20,
) -> list[dict[str, Any]]:
    """Fetch news articles for a ticker via AkShare (East Money).

    Args:
        ticker: Stock symbol (works with US tickers like AAPL, MSFT)
        days: Lookback window in days
        max_items: Maximum articles to return

    Returns:
        List of dicts with keys: title, summary, source, url, published_at
    """
    try:
        import akshare as ak
    except ImportError:
        return []

    try:
        df = ak.stock_news_em(symbol=ticker.upper())
    except Exception:
        return []

    if df is None or df.empty:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    articles = []
    for _, row in df.iterrows():
        try:
            pub_str = str(row.get("发布时间", ""))
            if pub_str:
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d %H:%M:%S")
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                published_at = pub_dt.isoformat()
            else:
                published_at = ""

            articles.append({
                "title": str(row.get("新闻标题", "")),
                "summary": str(row.get("新闻内容", ""))[:500],
                "source": str(row.get("文章来源", "东方财富")),
                "url": str(row.get("新闻链接", "")),
                "published_at": published_at,
            })
        except Exception:
            continue

        if len(articles) >= max_items:
            break

    return articles
