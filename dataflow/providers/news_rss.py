"""Google News RSS provider — reliable XML-based news aggregation.

Uses Google News RSS feed which returns structured XML with up to 100 articles
per query. No HTML scraping needed. Much higher volume than Bing RSS.

Combined with Bing RSS (news_bing.py) and Yahoo Finance (YFinance.py),
covers 1000+ articles per full scan for comprehensive market intelligence.
"""

from __future__ import annotations

import logging
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from datetime import timezone

import requests

logger = logging.getLogger(__name__)

GOOGLE_RSS_URL = "https://news.google.com/rss/search"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

# 50 queries covering all major market angles — ~5000 raw articles per scan
MORNING_BRIEF_QUERIES = [
    # ── US Macro & Policy (6) ──
    ("macro_fed", "Federal Reserve interest rate monetary policy decision"),
    ("macro_economy", "US economy GDP inflation jobs employment consumer spending"),
    ("macro_fiscal", "US fiscal policy tax reform legislation budget debt ceiling"),
    ("macro_wall_street", "Wall Street stock market Dow Nasdaq SP500 Russell"),
    ("macro_global", "global economy IMF World Bank growth outlook forecast"),
    ("macro_central_banks", "ECB BOJ BOE PBOC central bank policy rate decision"),

    # ── Sector: Technology (6) ──
    ("tech_ai", "artificial intelligence AI LLM foundation model regulation"),
    ("tech_semiconductor", "semiconductor chip foundry Nvidia AMD Intel TSMC ASML"),
    ("tech_cloud", "cloud computing AWS Azure Google Cloud SaaS enterprise software"),
    ("tech_cyber", "cybersecurity data breach ransomware hack vulnerability"),
    ("tech_consumer", "Apple iPhone Samsung smartphone wearable device consumer tech"),
    ("tech_startup", "tech startup unicorn venture capital funding IPO"),

    # ── Sector: Finance & Banking (4) ──
    ("fin_banks", "bank earnings financial sector JPMorgan Goldman Sachs Morgan Stanley"),
    ("fin_fintech", "fintech payment blockchain stablecoin digital currency regulation"),
    ("fin_insurance", "insurance underwriting claims climate risk reinsurance"),
    ("fin_real_estate", "real estate housing market mortgage rates commercial property REIT"),

    # ── Sector: Energy & Commodities (6) ──
    ("energy_oil", "crude oil OPEC shale production refining gasoline price"),
    ("energy_renewable", "solar wind renewable energy clean power grid battery storage"),
    ("energy_ev", "electric vehicle EV battery lithium Tesla BYD NIO charging"),
    ("energy_nuclear", "nuclear power uranium SMR small modular reactor"),
    ("commodity_metals", "copper iron ore steel aluminum lithium rare earth mining"),
    ("commodity_agri", "wheat corn soybeans agriculture food prices weather crop"),

    # ── Sector: Healthcare & Biotech (4) ──
    ("health_pharma", "pharmaceutical drug approval FDA clinical trial vaccine"),
    ("health_biotech", "biotech gene therapy CRISPR mRNA precision medicine immunology"),
    ("health_insurance", "health insurance Medicare Medicaid healthcare policy reform"),
    ("health_services", "hospital healthcare provider telemedicine medical device"),

    # ── Sector: Industrials & Infrastructure (4) ──
    ("indus_defense", "defense spending military contractor weapons Pentagon NATO"),
    ("indus_transport", "airlines shipping logistics freight trucking railroad aviation"),
    ("indus_construction", "construction infrastructure building materials engineering"),
    ("indus_manufacturing", "manufacturing factory automation robotics reshoring supply chain"),

    # ── Fixed Income & FX (4) ──
    ("bond_treasury", "US Treasury bond yield curve auction debt market"),
    ("bond_corporate", "corporate bond credit spread investment grade junk default risk"),
    ("fx_dollar", "US dollar DXY foreign exchange currency war forex intervention"),
    ("fx_emerging", "emerging market currency yuan rupee real peso devaluation outflow"),

    # ── Geopolitics & Policy (4) ──
    ("geo_trade", "trade war tariff sanction export control supply chain reshoring"),
    ("geo_us_china", "US China relations Taiwan South China Sea chip war decoupling"),
    ("geo_europe", "European Union EU policy regulation Germany France economy"),
    ("geo_global_south", "BRICS Global South developing country development bank IMF"),

    # ── China & Asia (8) — mixed English + Chinese queries ──
    ("china_macro", "China economy GDP PBOC stimulus property market deflation"),
    ("china_stock", "A-share stock market CSI 300 Shanghai Shenzhen IPO reform"),
    ("china_tech", "China technology Huawei Baidu Alibaba Tencent semiconductor AI"),
    ("china_policy", "China policy regulation economic work conference reform"),
    ("china_zh", "中国 经济 A股 政策 央行 降息 房地产"),
    ("china_zh2", "A股 沪深 创业板 科创板 北向资金 涨停"),
    ("asia_japan", "Japan economy BOJ Nikkei yen carry trade Topix"),
    ("asia_em", "India Korea Taiwan Southeast Asia emerging market growth reform"),

    # ── Crypto & Digital Assets (2) ──
    ("crypto_market", "Bitcoin Ethereum cryptocurrency price rally crash regulation"),
    ("crypto_defi", "DeFi Web3 NFT stablecoin blockchain smart contract adoption"),

    # ── Corporate & Deals (4) ──
    ("corp_earnings", "earnings report quarterly results revenue profit guidance beat miss"),
    ("corp_ipo", "IPO listing direct SPAC stock exchange NYSE Nasdaq offering"),
    ("corp_ma", "merger acquisition takeover buyout antitrust regulatory approval deal"),
    ("corp_buyback", "stock buyback dividend shareholder activist investor return capital"),
]


def fetch_google_news_rss(
    query: str,
    hl: str = "en-US",
    gl: str = "US",
    ceid: str = "US:en",
    hours: int = 0,
) -> list[dict]:
    """Fetch news articles from Google News RSS for a given query.

    Returns up to 100 articles per query. Each article has:
    {title, url, source_name, published_at, summary}

    If hours > 0, appends 'when:{hours}h' to filter by recency (e.g. hours=24).
    Auto-detects Chinese characters in query → switches locale to zh-CN.
    """
    q = f"{query} when:{hours}h" if hours > 0 else query

    # Auto-detect Chinese → use zh-CN locale for Chinese queries
    has_chinese = any('\u4e00' <= c <= '\u9fff' for c in query)
    if has_chinese:
        hl, gl, ceid = "zh-CN", "CN", "CN:zh-Hans"

    params = {
        "q": q,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    }
    try:
        resp = requests.get(
            GOOGLE_RSS_URL,
            params=params,
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        channel = root.find("channel")
        if channel is None:
            return []

        items = channel.findall("item")
        articles: list[dict] = []

        for item in items:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            pub_el = item.find("pubDate")
            source_el = item.find("source")

            title = title_el.text if title_el is not None and title_el.text else ""
            url = link_el.text if link_el is not None and link_el.text else ""
            summary = desc_el.text if desc_el is not None and desc_el.text else ""

            # Parse RSS pubDate (RFC 2822 format, e.g. "Tue, 22 Jun 2026 08:00:00 GMT")
            published_at = ""
            if pub_el is not None and pub_el.text:
                try:
                    dt = parsedate_to_datetime(pub_el.text)
                    published_at = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    published_at = pub_el.text

            source_name = ""
            if source_el is not None and source_el.text:
                source_name = source_el.text
            elif url:
                parsed = urllib.parse.urlparse(url)
                source_name = parsed.netloc.replace("www.", "")

            if title and url:
                articles.append({
                    "title": title,
                    "url": url,
                    "source_name": source_name,
                    "published_at": published_at,
                    "summary": summary,
                })

        return articles

    except Exception as exc:
        logger.warning("Google RSS failed for '%s': %s", query[:40], exc)
        return []


def fetch_all_news(
    queries: list[tuple[str, str]] | None = None,
    max_workers: int = 10,
    delay: float = 0.2,
    hours: int = 0,
) -> dict[str, list[dict]]:
    """Fetch news concurrently for all queries. Returns {category: [articles]}.

    Args:
        queries: List of (category, query_string) tuples. Defaults to MORNING_BRIEF_QUERIES.
        max_workers: Concurrent thread count.
        delay: Seconds between requests (rate limiting).
        hours: If > 0, filter to last N hours (e.g. 24).
    """
    if queries is None:
        queries = MORNING_BRIEF_QUERIES

    results: dict[str, list[dict]] = {}
    total = 0

    def _fetch(category: str, query: str):
        time.sleep(delay * hash(query) % 10 * 0.1)  # stagger requests
        articles = fetch_google_news_rss(query, hours=hours)
        return category, articles

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, cat, q): cat for cat, q in queries}
        for future in as_completed(futures):
            try:
                category, articles = future.result()
                results[category] = articles
                total += len(articles)
            except Exception as exc:
                logger.warning("Future failed: %s", exc)

    logger.info("Fetched %d total articles across %d categories", total, len(results))
    return results


def dedup_articles(categorized: dict[str, list[dict]]) -> list[dict]:
    """Deduplicate articles by URL across all categories. Returns flat list."""
    seen: set[str] = set()
    unique: list[dict] = []
    for category, articles in categorized.items():
        for a in articles:
            url = a.get("url", "")
            if url and url not in seen:
                seen.add(url)
                a["_category"] = category
                unique.append(a)
    logger.info("Dedup: %d unique articles", len(unique))
    return unique
