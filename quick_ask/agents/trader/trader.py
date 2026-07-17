"""Trader — generates trading proposal from the Research Manager's investment plan.

TradingAgents reference: trader/trader.py
Uses structured output (TradeProposal).
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


TRADER_PROMPT = """你是交易员（Trader）。基于研究经理的投资计划和标的背景，生成具体的交易提案。

你的任务：
1. 将投资计划转化为可执行的交易行动（Buy / Hold / Sell）
2. 给出建议的进场价格（如果适用）
3. 给出止损价位
4. 描述仓位管理策略

约束：
- 基于研究经理的建议，但可以调整执行细节
- 给出具体的数字而不是模糊的建议
- 用中文输出

━━━━ 研究经理投资计划 ━━━━
{investment_plan}

━━━━ 标的背景 ━━━━
{instrument_context}
"""


def trader_agent(llm):
    """Create the Trader agent node."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", TRADER_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | llm
    return chain
