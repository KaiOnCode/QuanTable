from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from quick_ask.agents.utils.output_prase import TradingDecision

output_parser = PydanticOutputParser(pydantic_object=TradingDecision)


def _format_memories(memories: list, limit: int = 3) -> str:
    """Format OWM-scored memories for injection into the PM prompt."""
    if not memories:
        return "（无相关历史记忆）"

    lines = []
    for i, m in enumerate(memories[:limit], 1):
        owm = m.owm_score if hasattr(m, 'owm_score') else m.get("owm_score", 0)
        episodic = m.episodic if hasattr(m, 'episodic') else m.get("episodic", "")
        trade = m.trade_record if hasattr(m, 'trade_record') else m.get("trade_record", {})
        action = trade.get("action", "HOLD") if isinstance(trade, dict) else getattr(trade, "action", "HOLD")
        lines.append(
            f"  {i}. [OWM={owm:.2f}] {action} — {str(episodic)[:200]}"
        )
    return "\n".join(lines)


def PM_agent(llm):
    def run(state):
        # 使用 .get() 安全访问，避免 KeyError
        ticker = state.get("ticker", "")
        date = state.get("date", "")
        current_position_pct = state.get("current_position_pct", 0.0)
        market_report = state.get("market_report", "")
        fundamental_report = state.get("fundamental_report", "")
        news_report = state.get("news_report", "")
        risk_report = state.get("risk_report", "")

        # 检查必需字段，注意 current_position_pct 为 0.0 时也是有效值（空仓）
        if (
            not ticker
            or not date
            or current_position_pct is None
            or not market_report
            or not fundamental_report
            or not news_report
            or not risk_report
        ):
            return {}

        # ── Memory recall ──
        memory_context = _format_memories(state.get("relevant_memories", []) or [])

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是「PM Agent」（最终裁决）。"
                    "所有数据均为今日收盘数据，请你为单一股票给出明日开盘的交易决策。"
                    "最大可以承受100%的回撤。"
                    "请你综合四份报告（MARKET_REPORT 文本/FUNDAMENTAL_REPORT 文本/NEWS_REPORT 文本/RISK_REPORT 文本），给出最终动作（BUY/HOLD/SELL）、入场节奏（enter/scale_in/wait）、目标仓位与目标价/区间，并明确失效条件,作为一份人类可读的中文报告。\n"
                    "报告按以下四行开头输出（每行独立、不要加序号或代码块围栏）：\n"
                    "方向: Bullish | Bearish | Neutral\n"
                    "时间范围: intraday | 1-3d | 1-4w | long-term\n"
                    "置信度: 0.00~1.00\n"
                    "一句话结论: ≤80字的一句话结论\n"
                    "然后撰写正文：\n"
                    "- 清楚说明：你的决策（BUY/HOLD/SELL、目标仓位）、主要理由（各 Agent 的一句话要点）、\n"
                    "  Technical/Fundamental/News 的相对权重，以及 Risk 的负向约束作用（文字描述即可），\n"
                    "- 给出简要的 IF–THEN 逻辑：在什么价格/事件/时间条件下，你会改变当前结论及对应动作。\n"
                    "提供“Reasoning Outline（高层）”：权重如何映射到最终动作、哪些触发会改变结论及优先级。\n"
                    "只使用输入事实；未知项以“Unknown: …”标注并说明影响；\n "
                    "━━━━ 历史相关决策（OWM 加权记忆）━━━━\n"
                    "{memory_context}\n"
                    "━━━━ 当前分析报告 ━━━━\n"
                    "MARKET_REPORT 文本:\n"
                    "{market_report}\n"
                    "FUNDAMENTAL_REPORT 文本:\n"
                    "{fundamental_report}\n"
                    "NEWS_REPORT 文本:\n"
                    "{news_report}\n"
                    "RISK_REPORT 文本:\n"
                    "{risk_report}\n",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(market_report=market_report)
        prompt = prompt.partial(fundamental_report=fundamental_report)
        prompt = prompt.partial(news_report=news_report)
        prompt = prompt.partial(risk_report=risk_report)
        prompt = prompt.partial(memory_context=memory_context)

        # 使用独立的 messages 列表
        messages = state.get("PM_agent_messages", [])
        # 如果是第一次调用，添加初始消息
        if not messages:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(
                    content=f"当前持仓百分比为 {current_position_pct}，负数代表做空持仓，请综合所有报告和记忆，用json格式输出股票 {ticker} 在当前分析日期 {date} 下的最终动作,目标仓位百分比，如果是做空输出负数百分比,以及人类可读的中文报告。json格式：{output_parser.get_format_instructions()}"
                )
            ]

        chain = prompt | llm | output_parser
        result = chain.invoke({"messages": messages})

        # result 是 TradingDecision 对象（Pydantic 模型），不是消息对象
        # PM agent 是最终节点，不需要将 Pydantic 对象添加到 messages
        # 保持 messages 不变即可
        updated_messages = messages

        return {
            "PM_agent_messages": updated_messages,
            "Action": result.action,
            "Target_position_pct": result.target_position_pct,
            "PM_report": result.report,
        }

    return run
