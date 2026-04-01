from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.utils.agent_tools import get_fundamentals


def fundamentals_analyst_agent(llm):
    def run(state):
        ticker = state["ticker"]
        date = state["date"]

        tools = [get_fundamentals]

        # 使用独立的 messages 列表
        messages = state.get("fundamentals_analyst_messages", [])
        # 如果是第一次调用，添加初始消息
        if not messages:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(
                    content=f"请分析股票 {ticker} 的基本面，使用工具获取基本面数据，当前分析日期为 {date}，你的结论只能基于该日及之前的数据。"
                )
            ]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是长期基本面首席分析师。基于基本面数据（你需要利用工具获取）进行长期倾向判断；盈利质量/增长优先于估值，估值用于修正。"
                    "按以下四行开头输出（每行独立、不要加序号或代码块围栏）："
                    "方向: Bullish | Bearish | Neutral"
                    "时间范围: long-term"
                    "置信度: 0.00~1.00"
                    "一句话结论: ≤80字的一句话结论"
                    "正文自由发挥，建议涵盖：关键财务与质量（EPS/营收与毛利增速/现金流/杠杆）、相对估值（对比行业给出溢/折价%，并简述合理性）、护城河与主要风险、后续需验证的2–3件事。"
                    '提供"Reasoning Outline（高层）"：列出引用数据、溢价计算口径/阈值、当"高估值 vs 高质量增长"冲突时如何仲裁，以及"若…则…"触发。'
                    '只使用输入事实；未知项以"Unknown: …"标注并说明影响；'
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
        if not messages or messages[-1] != result:
            updated_messages = messages + [result]
        else:
            updated_messages = messages

        return {
            "fundamentals_analyst_messages": updated_messages,
            "fundamental_report": report,
        }

    return run
