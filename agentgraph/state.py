from typing import Annotated, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState, add_messages


class AgentState(MessagesState):
    """
    多智能体系统的状态定义

    工作流程：
    1. 并行阶段：market_analyst, news_analyst, fundamentals_analyst 并行执行
    2. 风险分析阶段：risk_analyst 依赖三个分析师的报告
    3. 最终裁决阶段：PM_agent 依赖所有报告（包括风险报告）
    """

    # ========== 输入参数 ==========
    ticker: Annotated[str, "股票代码，例如 AAPL, TSM"]
    date: Annotated[str, "日期，例如 2024-01-15T00:00:00Z"]
    current_position_pct: Annotated[
        float, "当前持仓百分比，例如 20意为20%，范围为 0~100"
    ]

    # ========== 每个分析师的独立消息列表 ==========
    # 使用 add_messages reducer 来正确处理消息追加
    market_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    news_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    fundamentals_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    risk_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    PM_agent_messages: Annotated[List[BaseMessage], add_messages] = []

    # ========== 第一阶段：三个并行分析师（可并行执行）==========
    market_report: Annotated[
        Optional[str], "市场分析师（技术面）的报告，基于价格和技术指标"
    ] = ""
    news_report: Annotated[
        Optional[str], "新闻研究员的报告，基于新闻事件和情绪分析"
    ] = ""
    fundamental_report: Annotated[
        Optional[str], "基本面分析师的报告，基于财务数据和长期估值"
    ] = ""

    # ========== 第二阶段：风险分析师（依赖三个并行报告）==========
    risk_report: Annotated[
        Optional[str], "风险分析师的报告，基于持仓、风险限额和上游三个报告"
    ] = ""

    # ========== 第三阶段：最终裁决（依赖所有报告）==========
    PM_report: Annotated[
        Optional[str], "PM Agent的最终裁决报告，综合所有分析师的建议"
    ] = ""
    Action: Annotated[
        Optional[str], "PM Agent的最终裁决动作，只能为 BUY/HOLD/SELL 之一"
    ] = ""
    Target_position_pct: Annotated[
        Optional[float],
        "PM Agent的最终裁决目标持仓百分比，例如 50意为50%，范围为 0~100",
    ] = ""

    # ========== 可选：流程控制标记 ==========
    # 用于标记各阶段完成状态（可选，LangGraph会自动管理依赖）
    # market_analyst_done: Annotated[bool, "市场分析师是否完成"] = False
    # news_analyst_done: Annotated[bool, "新闻分析师是否完成"] = False
    # fundamentals_analyst_done: Annotated[bool, "基本面分析师是否完成"] = False
    # risk_analyst_done: Annotated[bool, "风险分析师是否完成"] = False
    # PM_done: Annotated[bool, "PM是否完成"] = False
