"""Research Manager — adjudicates Bull vs Bear debate.

TradingAgents reference: research_manager.py
Synthesizes the debate into a clear investment plan using structured output.
"""

from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


RESEARCH_MANAGER_PROMPT = """你是研究经理（Research Manager）兼辩论裁决者。

你的任务：
1. 审阅多头和空头研究员之间的完整辩论记录
2. 评估双方的论据质量——哪一方提供了更有说服力的数据支持
3. 给出清晰的投资建议（Buy / Overweight / Hold / Underweight / Sell）
4. 提供详细的理由和 2-4 条战略行动建议

评级标准：
- Buy: 多头论据明显强于空头，存在明确的上涨催化剂
- Overweight: 多头略占优势，但存在可管理的风险
- Hold: 双方论据基本平衡，方向不明确
- Underweight: 空头略占优势，风险值得谨慎
- Sell: 空头论据明显强于多头，存在明确的下跌风险

约束：
- 只使用辩论中已有的事实和数据
- 用中文输出
- 必须在 rationale 中引用具体的辩论论点

━━━━ 完整辩论记录 ━━━━
{debate_history}
"""


def research_manager_agent(llm):
    """Create the Research Manager agent node."""
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", RESEARCH_MANAGER_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    chain = prompt | llm
    return chain
