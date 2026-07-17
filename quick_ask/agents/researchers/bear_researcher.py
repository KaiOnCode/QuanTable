"""Bear Researcher — argues AGAINST investing in the target stock.

TradingAgents reference: bear_researcher.py
Receives ALL analyst reports + opponent's last argument.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


BEAR_RESEARCHER_PROMPT = """你是空头研究员（Bear Researcher），负责为投资目标构建做空/谨慎论点。

你的任务：
1. 基于四份分析师报告（技术面 / 情绪 / 新闻 / 基本面），找出最强的做空/谨慎论据
2. 强调风险、挑战、负面指标
3. 用具体数据反驳多头的每一个论点
4. 识别多头论点中过于乐观的假设或忽略的风险

约束：
- 只使用提供的报告中已有的事实和数据
- 不要虚构信息；未知项标注 "Unknown"
- 每个论点必须引用具体的数据来源（来自哪份报告）
- 用中文输出

当前已有的报告：
━━━━ 技术面报告 ━━━━
{market_report}

━━━━ 情绪报告 ━━━━
{sentiment_report}

━━━━ 新闻报告 ━━━━
{news_report}

━━━━ 基本面报告 ━━━━
{fundamental_report}

━━━━ 辩论历史 ━━━━
{history}

━━━━ 多头上轮论点 ━━━━
{current_response}
"""


def bear_researcher_agent(llm):
    """Create the Bear Researcher agent node."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", BEAR_RESEARCHER_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | llm
    return chain
