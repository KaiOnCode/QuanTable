"""Query planner — produces structured analysis plans.

Replaces the old is_complex() boolean with actual plan generation.
Claude Code pattern: plan-before-execute — agent decides what data
it needs before calling any tools, not during.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AnalysisPlan:
    """What data the agent needs and in what order."""

    tickers: list[str] = field(default_factory=list)
    data_types: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)   # specific tool names
    phases: list[str] = field(default_factory=list)   # "get data", "analyze", "report"
    is_simple: bool = True                           # skip plan for simple queries

    def to_prompt_text(self) -> str:
        """Generate the plan instruction injected into the system prompt."""
        if self.is_simple:
            return ""

        ticker_str = ", ".join(self.tickers) if self.tickers else "the mentioned stocks"
        tools_str = ", ".join(self.tools[:6]) if self.tools else "get_price, get_news, get_fundamentals"

        return (
            f"## Analysis Plan\n"
            f"1. Get data for: {ticker_str}. Tools to use: {tools_str}.\n"
            f"2. Analyze the results and provide your findings.\n"
            f"Call all data-gathering tools in one batch, then answer.\n"
        )

    @classmethod
    def from_query(cls, query: str) -> "AnalysisPlan":
        """Create a plan from a user query."""
        import re

        plan = cls()
        q = query.lower()

        # Simple queries: just one tool
        simple_patterns = [
            r"^(what is|get|show|how much|股价|价格|多少钱).*(price|价格|股价)",
            r"^(what is|get|show).*(rsi|macd|indicator|technicals)",
            r"^(what is|get|show).*(pe|pb|fundamental)",
            r"^(latest|recent|what).*(news|新闻)",
        ]
        for pat in simple_patterns:
            if re.search(pat, q):
                plan.is_simple = True
                if "price" in q or "价格" in q or "股价" in q:
                    plan.tickers = _extract_tickers(query)
                    plan.tools = ["get_price"]
                elif "rsi" in q or "macd" in q or "technicals" in q:
                    plan.tickers = _extract_tickers(query)
                    plan.tools = ["get_indicators"]
                elif "news" in q or "新闻" in q:
                    plan.tickers = _extract_tickers(query)
                    plan.tools = ["get_news"]
                return plan

        # Complex queries: need multiple data types
        plan.is_simple = False
        plan.tickers = _extract_tickers(query)

        # Determine needed data types from query
        if any(w in q for w in ('price', '价格', '股价', '行情', '多少钱')):
            plan.data_types.append("price")
            plan.tools.append("get_price")
        if any(w in q for w in ('rsi', 'macd', 'technicals', 'indicators', '技术', '指标', '均线')):
            plan.data_types.append("technicals")
            plan.tools.append("get_indicators")
        if any(w in q for w in ('pe', 'pb', 'fundamentals', '基本面', '财务', '估值')):
            plan.data_types.append("fundamentals")
            plan.tools.append("get_fundamentals")
        if any(w in q for w in ('news', '新闻', '最新')):
            plan.data_types.append("news")
            plan.tools.append("get_news")
        if any(w in q for w in ('sentiment', '情绪')):
            plan.data_types.append("sentiment")
            plan.tools.append("get_sentiment")

        # Comprehensive analysis: get everything
        if any(w in q for w in ('分析', 'analyze', 'research', '评估', 'compare', '对比', 'vs')):
            plan.tools = ["get_price", "get_fundamentals", "get_indicators", "get_news"]
            plan.data_types = ["price", "fundamentals", "technicals", "news"]
            plan.phases = ["gather_data", "analyze", "report"]

        # Comparison: needs data for multiple tickers
        if any(w in q for w in ('compare', 'comparison', '对比', '比较', 'vs')):
            plan.phases = ["gather_data_both", "compare", "report"]

        return plan


def _extract_tickers(text: str) -> list[str]:
    """Extract stock symbols from text."""
    import re
    stop = {'A', 'I', 'OK', 'AI', 'US', 'HK', 'PE', 'PB', 'ROE', 'THE',
            'AND', 'FOR', 'ALL', 'NEW', 'TOP', 'BEST', 'NOW', 'FED'}
    tickers = re.findall(r'\b[A-Z]{2,5}\b', text.upper())
    return list(dict.fromkeys(t for t in tickers if t not in stop))
