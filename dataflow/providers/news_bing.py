"""Bing News RSS provider — reliable XML-based news search.

Uses Bing News RSS feed (format=rss) which returns structured XML.
No HTML scraping needed. Much more reliable than Google News.
"""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import timezone

import requests

logger = logging.getLogger(__name__)

BING_RSS_URL = "https://www.bing.com/news/search"


def get_company_news_bing(
    query: str,
    days: int = 7,
    max_items: int = 20,
    lang: str = "en",
) -> list[dict]:
    """Search Bing News RSS for articles matching the query.

    Args:
        query: Search query (company name, ticker, keyword, etc.)
        days: How far back to search (Bing's 'interval' filter)
        max_items: Maximum number of articles to return
        lang: Language preference (affects market for Bing)

    Returns:
        List of dicts with: title, url, summary, source_name, published_at
    """
    market = "zh-hk" if lang.startswith("zh") else "en-us"
    params = {
        "q": query,
        "format": "rss",
        "qft": f"interval=%22{max(days, 1)}%22",  # e.g. interval="7"
        "setmkt": market,
    }

    try:
        resp = requests.get(
            BING_RSS_URL,
            params=params,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            },
            timeout=15,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            return []

        items = channel.findall("item")
        articles: list[dict] = []

        for item in items[:max_items]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text if title_el is not None and title_el.text else ""
            url = link_el.text if link_el is not None and link_el.text else ""
            summary = desc_el.text if desc_el is not None and desc_el.text else ""

            # Parse published date
            published_at = ""
            if pub_el is not None and pub_el.text:
                try:
                    from email.utils import parsedate_to_datetime

                    dt = parsedate_to_datetime(pub_el.text)
                    published_at = dt.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                except Exception:
                    published_at = pub_el.text

            # Source from <source> element or infer from URL
            source_name = ""
            if source_el is not None and source_el.text:
                source_name = source_el.text
            elif url:
                parsed = urllib.parse.urlparse(url)
                source_name = parsed.netloc.replace("www.", "")

            if title and url:
                articles.append(
                    {
                        "title": title,
                        "url": url,
                        "summary": summary,
                        "source_name": source_name,
                        "published_at": published_at,
                    }
                )

        logger.info(
            "Bing News: '%s' → %d articles (lang=%s, days=%d)",
            query,
            len(articles),
            lang,
            days,
        )
        return articles

    except Exception as exc:
        logger.warning("Bing News failed for '%s': %s", query, exc)
        return []
