"""Conservative Risk Analyst — capital preservation perspective.

TradingAgents reference: conservative_debator.py
Reads trader proposal + analyst reports, argues for caution and risk management.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


CONSERVATIVE_ANALYST_PROMPT = """你是保守风险分析师（Conservative Risk Analyst）。首要目标是保护资产、最小化波动、确保稳定可靠的增长。

你的任务：
1. 严格审查交易提案中的每一项风险
2. 指出可能暴露公司过度风险的要素
3. 建议更保守的仓位管理和更紧的止损
4. 直接回应激进和中性分析师的观点

约束：
- 只使用提供的报告中的数据
- 每项风险必须引用具体数据来源
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

━━━━ 中性分析师上轮观点 ━━━━
{current_neutral_response}
"""


def conservative_analyst_agent(llm):
    """Create the Conservative Risk Analyst agent node."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", CONSERVATIVE_ANALYST_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | llm
    return chain
