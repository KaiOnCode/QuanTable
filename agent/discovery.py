"""Agent-driven data discovery for Tier 4 governance.

Periodically calls LLM to review user context (watchlist, recent decisions,
hot news) and suggest new tickers to collect data for.

This implements the user's Plan B: "定期调用agent来查看之前的历史对话、watchlist，
自动判断什么相关"

Design: constrained prompt → structured JSON output → add to collector pool.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def discover_related_tickers(
    interests: list[dict],
    recent_headlines: list[str],
    max_suggestions: int = 5,
) -> list[dict]:
    """Call LLM to discover new tickers related to user interests.

    Args:
        interests: list of {ticker, source} from watchlists + recent decisions
        recent_headlines: list of news title strings
        max_suggestions: max tickers to return

    Returns:
        list of {ticker, reason, priority}
    """
    if not interests:
        return []

    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage

    api_base = os.getenv("OPENAI_API_BASE", "")
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=api_base if api_base else None,
        temperature=0.0,
        max_tokens=512,
    )

    # Build compact context
    interest_str = "\n".join(
        f"- {i['ticker']} (from {i.get('source', 'unknown')})"
        for i in interests[:20]
    )
    headlines_str = "\n".join(f"- {h}" for h in recent_headlines[:15])

    prompt = f"""你是数据发现代理。根据用户当前的关注和最新新闻，发现{max_suggestions}个值得关注的股票代码。

用户关注:
{interest_str or "无"}

最新新闻:
{headlines_str or "无"}

输出严格 JSON 数组，每个元素含 ticker（股票代码）、reason（≤20字中文理由）、priority（1-3, 1=高）：
[
  {{"ticker": "AAPL", "reason": "用户频繁分析", "priority": 1}},
  ...
]

只输出 JSON，不要其他文字。"""

    try:
        response = llm.invoke([
            SystemMessage(content="你是数据发现代理。只输出JSON，不要任何解释。"),
            HumanMessage(content=prompt),
        ])
        content = response.content if hasattr(response, "content") else str(response)
        # Extract JSON array from response
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
        results = json.loads(content)
        return [
            {
                "ticker": r["ticker"].upper(),
                "reason": r.get("reason", ""),
                "priority": r.get("priority", 2),
            }
            for r in results
            if isinstance(r, dict) and "ticker" in r
        ]
    except Exception as exc:
        logger.warning("Discovery agent failed: %s", exc)
        return []


def gather_user_interests(
    watchlist_tickers: list[str],
    decision_tickers: list[str],
) -> list[dict]:
    """Combine watchlist and decision history into unified interest list."""
    seen: set[str] = set()
    interests: list[dict] = []

    for t in decision_tickers:  # decisions first = higher interest
        if t not in seen:
            seen.add(t)
            interests.append({"ticker": t, "source": "recent_decision"})
    for t in watchlist_tickers:
        if t not in seen:
            seen.add(t)
            interests.append({"ticker": t, "source": "watchlist"})

    return interests
