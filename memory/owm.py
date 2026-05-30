"""OWM (Outcome-Weighted Memory) scoring functions.

Inspired by TradeMemory Protocol (MIT License).
Five factors: outcome quality, context similarity, recency, confidence, affective state.
"""

from __future__ import annotations

from datetime import datetime, timezone


def compute_owm_score(
    outcome_quality: float,
    context_similarity: float,
    recency: float,
    confidence: float,
    affective_weight: float = 1.0,
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute the OWM composite score for memory relevance ranking.

    Args:
        outcome_quality: -1.0 (total loss) to 1.0 (max profit), PnL-based.
        context_similarity: 0.0 to 1.0, feature match between current and past context.
        recency: 0.0 to 1.0, exponential decay over time.
        confidence: 0.0 to 1.0, original decision confidence.
        affective_weight: 1.0 = neutral, <1.0 = stressed, >1.0 = calm/confident.
        weights: Override default OWM factor weights.

    Returns:
        Composite score from -1.0 to 1.0.
    """
    if weights is None:
        weights = {
            "outcome": 0.35,
            "similarity": 0.25,
            "recency": 0.20,
            "confidence": 0.15,
            "affective": 0.05,
        }

    score = (
        weights["outcome"] * outcome_quality
        + weights["similarity"] * context_similarity
        + weights["recency"] * recency
        + weights["confidence"] * confidence
        + weights["affective"] * affective_weight
    )
    return max(-1.0, min(1.0, score))


def compute_recency(
    timestamp: str,
    current_time: str | None = None,
    half_life_days: float = 30.0,
) -> float:
    """Exponential decay recency score.

    Args:
        timestamp: ISO 8601 string of the past event.
        current_time: ISO 8601 string of now (defaults to UTC now).
        half_life_days: Days after which the score halves.

    Returns:
        0.0 to 1.0, where 1.0 means "just happened".
    """
    t = _parse_iso(timestamp)
    now = _parse_iso(current_time) if current_time else datetime.now(timezone.utc)
    days_elapsed = (now - t).total_seconds() / 86400.0
    if days_elapsed < 0:
        days_elapsed = 0
    return 2.0 ** (-days_elapsed / half_life_days)


def compute_context_similarity(
    current: dict,
    past: dict,
) -> float:
    """Feature-based context similarity between current and past market conditions.

    Features compared: ticker (exact match), sector, market_cap_bucket, market_trend.

    Args:
        current: Current market context dict.
        past: Past market context dict from memory.

    Returns:
        0.0 to 1.0 similarity score.
    """
    score = 0.0
    features_checked = 0

    # Ticker exact match: strong signal
    if current.get("ticker") and past.get("ticker"):
        features_checked += 1
        if current["ticker"] == past["ticker"]:
            score += 1.0

    # Categorical features: exact match
    for key in ("sector", "market_cap_bucket", "market_trend"):
        if current.get(key) and past.get(key):
            features_checked += 1
            if current[key] == past[key]:
                score += 1.0

    if features_checked == 0:
        return 0.5  # Neutral when no features to compare

    return score / features_checked


def _parse_iso(ts: str) -> datetime:
    """Parse ISO 8601, handling Z suffix and fractional seconds."""
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)
