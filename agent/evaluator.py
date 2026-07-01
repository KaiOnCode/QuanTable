"""Quality evaluator — checks if tool results are sufficient to answer.

Claude Code pattern: after each tool execution batch, evaluate whether
the data collected so far is enough to answer the user's question.
If not, tell the loop WHAT specific data is still needed.

This replaces the crude "how many tool calls" heuristic with
semantic evaluation of what data we have vs what we need.
"""

from __future__ import annotations

import json
import re

# Map of tool → what kind of data it provides
TOOL_DATA_TYPE = {
    "get_price": "price",
    "get_indicators": "technicals",
    "get_fundamentals": "fundamentals",
    "get_news": "news",
    "get_sentiment": "sentiment",
    "get_meta": "company_info",
    "web_search": "web_info",
    "search_symbol": "ticker_lookup",
    "generate_brief": "market_brief",
}


class DataGap:
    """Describes missing data the agent still needs."""

    def __init__(self, ticker: str = "", data_type: str = "", reason: str = ""):
        self.ticker = ticker
        self.data_type = data_type
        self.reason = reason

    def __repr__(self):
        if self.ticker and self.data_type:
            return f"missing {self.data_type} for {self.ticker}"
        return self.reason or "unknown gap"


def extract_tickers_from_query(query: str) -> list[str]:
    """Extract stock tickers mentioned in a query."""
    # Match ALLCAPS words (2-5 chars) that aren't common words
    stop = {'A', 'I', 'OK', 'AI', 'US', 'HK', 'PE', 'PB', 'ROE',
            'RSI', 'MACD', 'SMA', 'ETF', 'IPO', 'USD', 'CEO', 'THE',
            'AND', 'FOR', 'ALL', 'NEW', 'TOP', 'BEST', 'NOW'}
    tickers = re.findall(r'\b[A-Z]{2,5}\b', query.upper())
    return [t for t in tickers if t not in stop]


def extract_requested_data_types(query: str) -> set[str]:
    """Determine what data types the user is asking for."""
    wanted = set()
    q = query.lower()

    # Price
    if any(w in q for w in ('price', 'prices', 'cost', '股价', '价格', '多少钱', '行情')):
        wanted.add("price")
    # Technicals
    if any(w in q for w in ('rsi', 'macd', 'indicator', 'technical', 'sma', '均线', '技术', '指标')):
        wanted.add("technicals")
    # Fundamentals
    if any(w in q for w in ('pe', 'pb', 'roe', 'eps', 'fundamental', 'financial', '基本面', '估值', '财务')):
        wanted.add("fundamentals")
    # News
    if any(w in q for w in ('news', '新闻', '最新', '最近', '发生了什么')):
        wanted.add("news")
    # Sentiment
    if any(w in q for w in ('sentiment', '情绪', '看法')):
        wanted.add("sentiment")
    # General analysis
    if any(w in q for w in ('分析', 'analyze', 'analysis', 'research', '研究', '评估',
                              'compare', '对比', '比较', 'vs')):
        wanted.update({"price", "fundamentals", "news"})

    return wanted or {"price"}  # default: at least price


def evaluate(messages: list[dict], user_query: str) -> tuple[bool, str]:
    """Evaluate whether we have enough data to answer.

    Returns:
        (is_sufficient, guidance_message)

    Claude Code pattern: evaluator returns either "enough" or
    specific guidance on what's still missing.
    """
    # Extract what tools succeeded and for which tickers
    tool_results: dict[str, set] = {}  # ticker → set of data_types
    errors: list[str] = []

    for m in messages:
        if m.get("role") != "tool":
            continue
        content = m.get("content", "")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        status = parsed.get("status", "ok")
        ticker = parsed.get("ticker", "").upper()
        tool_name = m.get("name", "")
        data_type = TOOL_DATA_TYPE.get(tool_name)

        if status == "ok" and ticker and data_type:
            tool_results.setdefault(ticker, set()).add(data_type)
        elif status == "error":
            err = parsed.get("error", "")[:80]
            errors.append(f"{tool_name}({ticker}): {err}")

    # What does the user want?
    tickers = extract_tickers_from_query(user_query)
    wanted_types = extract_requested_data_types(user_query)

    gaps = []
    for ticker in tickers:
        have = tool_results.get(ticker, set())
        missing = wanted_types - have
        if missing:
            for dt in missing:
                gaps.append(DataGap(ticker=ticker, data_type=dt))

    if not gaps:
        # Enough data
        if errors:
            return True, f"Data collected. Some tools had errors: {'; '.join(errors[-2:])}"
        return True, ""

    # Still need more data
    gap_msg = "; ".join(str(g) for g in gaps[:3])
    if errors:
        gap_msg += f". Errors: {'; '.join(errors[-2:])}"
    return False, gap_msg
