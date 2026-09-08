"""Sentiment Analyst — news + social sentiment analysis.

Follows old agent pattern: bind_tools for tool calling, reads per-agent
messages from state, returns per-agent messages for the tool loop.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from quick_ask.agents.utils.agent_tools import get_news, get_sector, get_sentiment


SENTIMENT_SYSTEM = """你是情绪分析师。使用工具获取新闻和情绪数据，评估市场对该股票的整体情绪。

分析维度：
1. 新闻情绪 — 调用 get_news 获取新闻，分析正面/负面倾向
2. 社交媒体情绪 — 调用 get_sentiment 获取情绪评分
3. 行业背景 — 调用 get_sector 获取行业信息

先严格按以下四行开头输出（每行独立、不要加序号、前缀或代码块围栏）：
方向: Bullish | Bearish | Neutral
时间范围: intraday | 1-3d | 1-4w
置信度: 0.00~1.00
一句话结论: ≤80字的一句话结论

正文自由发挥，需包含：情绪评分、关键新闻事件、情绪一致性分析。
只使用工具获取的数据，不要虚构。未知项以"Unknown: …"标注。
"""


def sentiment_analyst_agent(llm):
    """Create the sentiment analyst — old agent pattern with bind_tools."""
    tools = [get_sentiment, get_news, get_sector]
    llm_with_tools = llm.bind_tools(tools)

    prompt = ChatPromptTemplate.from_messages([
        ("system", SENTIMENT_SYSTEM),
        ("system", "你可以使用以下工具: {tool_names}"),
        MessagesPlaceholder(variable_name="messages"),
    ])

    chain = prompt | llm_with_tools

    def run(state: dict) -> dict:
        ticker = state["ticker"]
        date = state["date"]
        msgs = state.get("sentiment_analyst_messages", [])
        if not msgs:
            msgs = [
                SystemMessage(content=f"当前股票: {ticker}, 分析日期: {date}"),
                HumanMessage(content=f"请获取 {ticker} 的情绪数据、新闻和行业信息，写一份情绪分析报告。"),
            ]
        result = chain.invoke({
            "messages": msgs,
            "tool_names": ", ".join(t.name for t in tools),
        })
        return {"messages": [result], "sentiment_analyst_messages": [result]}

    return run
