from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.utils.agent_tools import get_news


def news_analyst_agent(llm):
    def run(state):
        ticker = state["ticker"]
        date = state["date"]
        tools = [get_news]

        # 使用独立的 messages 列表
        messages = state.get("news_analyst_messages", [])
        # 如果是第一次调用，添加初始消息
        if not messages:
            from langchain_core.messages import HumanMessage

            messages = [
                HumanMessage(
                    content=f"请分析股票 {ticker} 的新闻，使用工具获取新闻数据，当前分析日期为 {date}，你的结论只能基于该日及之前的数据 。"
                )
            ]

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    '你是新闻研究员。仅基于"新闻列表"（你需要利用工具获取）进行评估：先看"数据面"（新闻中出现的明确数据/财报数字/官方声明等可验证事实），再看"情绪面"（标题/措辞倾向、报道密度、一致性），给出融合倾向与大致价格影响区间。'
                    "按以下四行开头输出（每行独立、不要加序号或代码块围栏）："
                    "方向: Bullish | Bearish | Neutral"
                    "时间范围: intraday | 1-3d | 1-4w"
                    "置信度: 0.00~1.00"
                    "一句话结论: ≤80字的一句话结论"
                    "正文自由发挥，但需给出：发生了什么/为何重要；影响量化（Data score / Sentiment score / Net impact，口径 -1~1，文本表达即可；以及价格影响区间如 -0.3% ~ +1.6%；若无法判断则写 Unknown 并说明原因）；新鲜度与可信度；下一步跟踪点。"
                    '提供"Reasoning Outline（高层）"：标注所引新闻条目索引，说明如何从新闻内容提取数据面与情绪面、权重说明（如 data 0.6 / sentiment 0.4；和=1）、冲突仲裁规则（数据面优先），以及"若…则…"触发（如后续报道反转/更多权威来源出现）。'
                    '只使用输入事实；传闻/未证实内容必须标注折扣逻辑；未知项以"Unknown: …"标注并说明影响；'
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
            "news_analyst_messages": updated_messages,
            "news_report": report,
        }

    return run
