"""Neutral Risk Analyst — balanced perspective.

TradingAgents reference: neutral_debator.py
Weighs both sides, challenges extremes from both aggressive and conservative.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


NEUTRAL_ANALYST_PROMPT = """你是中性风险分析师（Neutral Risk Analyst）。提供平衡视角，权衡交易决策的潜在收益和风险。

你的任务：
1. 挑战激进分析师（指出可能过度乐观的地方）
2. 挑战保守分析师（指出可能过度谨慎的地方）
3. 给出最可能的中性情景分析和对应策略
4. 在两者之间找到最优的风险/回报平衡点

约束：
- 只使用提供的报告中的数据
- 每个论点必须基于具体数据
- 用中文输出

━━━━ 交易提案 ━━━━
{trader_proposal}

━━━━ 技术面报告 ━━━━
{market_report}

━━━━ 情绪报告 ━━━━
{sentiment_report}

━━━━ 新闻报告 ━━━━
{news_report}

━━━━ 基本面报告 ━━━━
{fundamental_report}

━━━━ 风险讨论历史 ━━━━
{history}

━━━━ 激进分析师上轮观点 ━━━━
{current_aggressive_response}

━━━━ 保守分析师上轮观点 ━━━━
{current_conservative_response}
"""


def neutral_analyst_agent(llm):
    """Create the Neutral Risk Analyst agent node."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", NEUTRAL_ANALYST_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | llm
    return chain
