"""Sentiment data provider.

Aggregates news sentiment from Google News articles into a structured
-1.0 to 1.0 score. Used by the sentiment_analyst agent.

Implements the df_get_sentiment function referenced in docs/architecture.md
section 11 (DataService line 380-383).
"""

from __future__ import annotations

from typing import Any

from dataflow.cache import cache_key, read_cache, write_cache
from dataflow.utils import retry, now_iso

SENTIMENT_CACHE_TTL_HOURS = 4  # News sentiment ages faster than price data


def df_get_sentiment(
    ticker: str,
    window_days: int = 7,
    end_date: str | None = None,
    lang: str = "en",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Compute aggregated sentiment for a ticker from recent news.

    Returns a dict with:
        score: float in [-1.0, 1.0] where positive = bullish
        confidence: float in [0.0, 1.0]
        article_count: int
        top_keywords: list[str]
        articles: list[dict] (truncated)
        source: str (always "google_news_aggregation")
        generated_at: str (ISO timestamp)

    Uses cache with SHA256 integrity check. Falls back gracefully
    when news scraping fails (returns neutral with confidence=0).
    """
    ck = cache_key("sentiment", ticker, str(window_days), lang)
    if not force_refresh:
        cached = read_cache(ck, max_age_hours=SENTIMENT_CACHE_TTL_HOURS)
        if cached is not None:
            return cached

    # Import here to avoid circular dependency at module level
    try:
        from dataflow.providers.news_google import get_company_news

        articles = retry(
            lambda: get_company_news(
                ticker, days=window_days, lang=lang, end_date=end_date
            ),
            tries=2,
            base_delay=0.5,
        )
    except Exception:
        articles = []

    if not articles:
        result = {
            "score": 0.0,
            "confidence": 0.0,
            "article_count": 0,
            "top_keywords": [],
            "articles": [],
            "source": "google_news_aggregation",
            "generated_at": now_iso(),
            "note": "No news articles available for sentiment analysis",
        }
        write_cache(ck, result)
        return result

    # Simple keyword-based sentiment scoring (production would use NLP/LLM)
    bullish_words = [
        "beat",
        "raise",
        "upgrade",
        "growth",
        "strong",
        "positive",
        "buy",
        "outperform",
        "opportunity",
        "expansion",
        "record",
        "surge",
        "jump",
        "rally",
        "boost",
        "accelerate",
    ]
    bearish_words = [
        "miss",
        "cut",
        "downgrade",
        "decline",
        "weak",
        "negative",
        "sell",
        "underperform",
        "risk",
        "layoff",
        "loss",
        "drop",
        "fall",
        "plunge",
        "slowdown",
        "warning",
    ]

    scores: list[float] = []
    all_keywords: dict[str, int] = {}

    for article in articles:
        title = (article.get("title") or "").lower()
        summary = (article.get("summary") or "").lower()
        text = title + " " + summary

        bull_count = sum(1 for w in bullish_words if w in text)
        bear_count = sum(1 for w in bearish_words if w in text)

        # Per-article score
        total = bull_count + bear_count
        if total > 0:
            article_score = (bull_count - bear_count) / total
        else:
            article_score = 0.0
        scores.append(article_score)

        # Keyword tracking
        for word in bullish_words + bearish_words:
            if word in text:
                all_keywords[word] = all_keywords.get(word, 0) + 1

    # Aggregate
    avg_score = sum(scores) / len(scores) if scores else 0.0
    # Confidence based on article count and score consistency
    score_variance = (
        sum((s - avg_score) ** 2 for s in scores) / len(scores) if scores else 1.0
    )
    confidence = min(1.0, len(articles) / 10.0 * (1.0 - min(score_variance, 0.5)))

    top_keywords = sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
    top_kw_list = [kw for kw, _ in top_keywords]

    result = {
        "score": round(avg_score, 4),
        "confidence": round(confidence, 4),
        "article_count": len(articles),
        "top_keywords": top_kw_list,
        "articles": articles[:5],  # Truncated for cache size
        "source": "google_news_aggregation",
        "generated_at": now_iso(),
    }
    write_cache(ck, result)
    return result
