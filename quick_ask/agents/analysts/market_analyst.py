from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from quick_ask.agents.utils.agent_tools import get_indicators, get_price


def market_analyst_agent(llm):
    def run(state):
        ticker = state["ticker"]
        date = state["date"]

        tools = [get_price, get_indicators]

        # 使用独立的 messages 列表
        messages = state.get("market_analyst_messages", [])
        # 如果是第一次调用，添加初始消息
        if not messages:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(
                    content=f"请分析股票 {ticker} 的技术面，使用工具获取价格和技术指标数据，当前分析日期为 {date}，你的结论只能基于该日及之前的数据。"
                )
            ]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是技术面首席分析师,只基于价格与技术指标（你需要利用工具获取）给出方向与交易计划；不得引入外部信息或自行虚构数据。"
                    "输出为中文纯文本，先严格按以下四行开头（每行独立、不要加序号、前缀或代码块围栏）："
                    "方向: Bullish | Bearish | Neutral"
                    "时间范围: intraday | 1-3d | 1-4w | long-term"
                    "置信度: 0.00~1.00"
                    "一句话结论: ≤80字的一句话结论"
                    '正文自由发挥，但需包含：关键信号（量化数值/阈值/关键位/突破距离/ATR口径）、可执行的入场/加减仓/风控触发，以及"若…则…"边界。'
                    "出现信号冲突时必须解释仲裁逻辑（建议优先级：趋势(均线/结构) > 动量(MACD/RSI) > 位阶(支撑/阻力/突破) > 价量）。"
                    '给出一个"Reasoning Outline（高层）"概述所用输入、阈值/规则、仲裁依据与关键触发。'
                    '未知项以"Unknown: …"标注并说明影响；'
                    "你必须使用工具获取数据，不能直接回答。你可以访问以下工具：{tool_names}。\n",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke({"messages": messages})

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        # 只有当 result 不在 messages 中时才添加
        # 避免重复添加相同的消息
        if not messages or messages[-1] != result:
            updated_messages = messages + [result]
        else:
            updated_messages = messages

        return {
            "market_analyst_messages": updated_messages,
            "market_report": report,
        }

    return run
