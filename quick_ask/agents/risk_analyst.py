# [LEGACY] Track 1 — Do NOT add features. See: docs/codebase-tracks.md
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def risk_analyst_agent(llm):
    def run(state):
        # 如果 risk_report 已存在，说明已经执行过了，直接返回（避免重复执行）
        if state.get("risk_report", "") != "":
            return {
                "risk_analyst_messages": state.get("risk_analyst_messages", []),
                "risk_report": state.get("risk_report", ""),
            }

        # 检查三个报告是否都存在
        market_report = state.get("market_report", "")
        fundamental_report = state.get("fundamental_report", "")
        news_report = state.get("news_report", "")

        # 只有当三个报告都存在时才执行
        if market_report and fundamental_report and news_report:
            ticker = state["ticker"]
            date = state["date"]
            current_position_pct = state["current_position_pct"]

            # 使用独立的 messages 列表
            messages = state.get("risk_analyst_messages", [])
            # 如果是第一次调用，添加初始消息
            if not messages:
                from langchain_core.messages import HumanMessage

                messages = [
                    HumanMessage(
                        content=f"请分析股票 {ticker} 的风险，当前分析日期为 {date}，你的结论只能基于该日及之前的数据，当前持仓百分比为 {current_position_pct}。"
                    )
                ]

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "你是风险分析师（仓位/止损止盈/风险分）。你需要基于当前持仓百分比和三份报告（Market/Fundamental/News），"
                        "将上游要点转译为可执行的仓位、止损止盈与时间窗建议。"
                        "最大可以承受100%的回撤。"
                        "按以下四行开头输出（每行独立、不要加序号或代码块围栏）："
                        "方向: Bullish | Bearish | Neutral"
                        "时间范围: intraday | 1-3d | 1-4w"
                        "置信度: 0.00~1.00"
                        "一句话结论: ≤80字的一句话结论"
                        "正文自由发挥，建议包含：当前暴露与限额检查、场景—动作对（价格/事件/时间三类触发）、分批与止损/止盈口径。"
                        '提供"Reasoning Outline（高层）"：新鲜事件折扣规则、触发矩阵与缺失项的保守假设。'
                        '只使用输入事实；未知项以"Unknown: …"标注并说明影响；'
                        "上游报告 (MARKET_REPORT 文本):\n"
                        "{market_report}\n"
                        "上游报告 (FUNDAMENTAL_REPORT 文本):\n"
                        "{fundamental_report}\n"
                        "上游报告 (NEWS_REPORT 文本):\n"
                        "{news_report}\n",
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            prompt = prompt.partial(market_report=market_report)
            prompt = prompt.partial(fundamental_report=fundamental_report)
            prompt = prompt.partial(news_report=news_report)

            chain = prompt | llm
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
                "risk_analyst_messages": updated_messages,
                "risk_report": report,
            }
        else:
            # 如果三个报告还没都准备好，返回空状态（不修改任何东西）
            # 这样节点会被调用，但不会执行实际逻辑，等待其他报告完成
            return {}

    return run
