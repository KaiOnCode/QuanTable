import os
import sys
from collections.abc import Callable, Mapping
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import SecretStr

from agentgraph.execution_node import create_execution_node
from agentgraph.state import AgentState
from agents.fundamentals_analyst import fundamentals_analyst_agent
from agents.market_analyst import market_analyst_agent
from agents.news_analyst import news_analyst_agent
from agents.PM import PM_agent
from agents.risk_analyst import risk_analyst_agent
from agents.utils.agent_tools import (
    get_fundamentals,
    get_indicators,
    get_news,
    get_price,
)
from broker.gateway import BrokerGateway
from broker.views import ExecutionReportView

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv("properties.env")
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2", "false")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY", "")


def create_tool_node_wrapper(node_name: str, tools):
    """创建工具节点包装器，使用各自的 messages 列表"""
    tool_node = ToolNode(tools)

    def wrapper(state: AgentState):
        # 获取对应的 messages 列表
        messages_key = f"{node_name}_messages"
        messages = state.get(messages_key, [])

        if not messages:
            return {messages_key: []}

        # 临时将各自的 messages 同步到 state["messages"]，供 ToolNode 使用
        temp_state = {**state, "messages": messages}

        # 执行工具节点
        result = tool_node.invoke(temp_state)

        # 将工具执行结果同步回各自的 messages
        # 确保消息列表是完整的
        updated_messages = result.get("messages", messages)

        return {
            messages_key: updated_messages,
        }

    return wrapper


def should_continue(node_name: str):
    def should_tool_node(state: AgentState):
        # 根据节点名称获取对应的 messages 列表
        messages_key = f"{node_name}_messages"
        messages = state.get(messages_key, [])

        # 如果 messages 为空，说明 agent 返回了空状态
        # 对于 risk_analyst：如果三个报告没齐，返回空状态，此时 messages 为空，直接结束
        # 对于三个分析师：如果 messages 为空，说明有问题，直接结束
        if not messages:
            return END

        last_message = messages[-1]
        # 检查是否有工具调用
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            # risk_analyst 没有工具节点，即使有工具调用也直接继续
            if node_name == "risk_analyst":
                return "PM_agent"
            return f"{node_name}_tool"

        # 如果没有工具调用，说明 agent 已经完成，继续到下一步
        if node_name == "risk_analyst":
            return "PM_agent"
        return "risk_analyst"

    return should_tool_node


class IntelliFin_Assistant:
    def __init__(
        self,
        llm: Any | None = None,
        broker: BrokerGateway | None = None,
        enable_hitl: bool = False,
        hitl_approval_node: Any | None = None,
        tool_nodes: dict[str, Any] | None = None,
        agent_nodes: dict[str, Any] | None = None,
        execution_node: Any | None = None,
        on_execution_complete: (
            Callable[[ExecutionReportView, Mapping[str, object]], None] | None
        ) = None,
    ):
        self.llm = llm
        if self.llm is None and agent_nodes is None:
            api_key = os.getenv("OPENAI_API_KEY")
            # The default runtime still uses the configured chat model.
            self.llm = ChatOpenAI(
                model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
                api_key=SecretStr(api_key) if api_key else None,
                base_url=os.getenv("OPENAI_API_BASE"),
            )

        self.tool_nodes: dict[str, Any] = tool_nodes or self._create_tool_nodes()
        self.agent_nodes: dict[str, Any] = agent_nodes or self._create_agent_nodes()
        self.execution_node = execution_node
        self.on_execution_complete = on_execution_complete
        self.enable_hitl = enable_hitl
        self.hitl_approval_node = hitl_approval_node
        self.broker = broker
        wf = StateGraph(AgentState)

        for node_name, node in self.tool_nodes.items():
            # market, news, fundamentals 分析师的可能路径
            path_map = {
                f"{node_name}_tool": f"{node_name}_tool",
                "risk_analyst": "risk_analyst",
                END: END,
            }

            wf.add_node(f"{node_name}_tool", node)  # 工具节点
            wf.add_node(node_name, self.agent_nodes[node_name])  # 代理节点
            wf.add_conditional_edges(
                node_name, should_continue(node_name), path_map
            )  # 条件边（工具节点或下一步代理节点）三个分析节点到风险分析师
            wf.add_edge(f"{node_name}_tool", node_name)  # 工具节点到代理节点的边

        # 单独添加 risk_analyst 节点（没有工具节点）
        wf.add_node("risk_analyst", self.agent_nodes["risk_analyst"])
        wf.add_conditional_edges(
            "risk_analyst",
            should_continue("risk_analyst"),
            {"PM_agent": "PM_agent", END: END},
        )  # risk_analyst 的条件边：直接到 PM_agent 或结束

        wf.add_node("PM_agent", self.agent_nodes["PM_agent"])  # PM节点

        wf.add_edge(START, "market_analyst")
        wf.add_edge(START, "news_analyst")
        wf.add_edge(START, "fundamentals_analyst")
        if self.broker is None:
            wf.add_edge("PM_agent", END)
        else:
            execution_node_impl: Any = self.execution_node
            if execution_node_impl is None:
                execution_node_impl = create_execution_node(
                    self.broker,
                    on_execution_complete=self.on_execution_complete,
                )
            wf.add_node("execution_node", execution_node_impl)
            if self.enable_hitl:
                wf.add_node(
                    "hitl_approval",
                    self.hitl_approval_node or self._create_hitl_approval_placeholder(),
                )
                wf.add_edge("PM_agent", "hitl_approval")
                wf.add_edge("hitl_approval", "execution_node")
            else:
                wf.add_edge("PM_agent", "execution_node")
            wf.add_edge("execution_node", END)

        # 初始化内存，在图运行时存储状态（状态持久化）
        checkpoint = MemorySaver()  # 可拓展redis,mongoDB
        self.wf = wf.compile(checkpointer=checkpoint)

    def run(
        self,
        ticker: str,
        date: str | None = None,
        current_position_pct: float = 0.0,
        *,
        execution_enabled: bool = False,
        session_id: str = "",
    ):
        # 初始化状态
        initial_state = {
            "ticker": ticker,
            "date": date,
            "current_position_pct": current_position_pct,
            "execution_enabled": execution_enabled,
            "session_id": session_id,
        }
        thread_id = session_id or "42"
        return self.wf.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}},  # 相当于会话id
        )

    def visualize(self):
        with open("graph.png", "wb") as f:
            f.write(self.wf.get_graph().draw_mermaid_png())

    def _create_tool_nodes(self):
        return {
            "market_analyst": create_tool_node_wrapper(
                "market_analyst", [get_price, get_indicators]
            ),
            "news_analyst": create_tool_node_wrapper("news_analyst", [get_news]),
            "fundamentals_analyst": create_tool_node_wrapper(
                "fundamentals_analyst", [get_fundamentals]
            ),
        }

    def _create_agent_nodes(self):
        return {
            "market_analyst": market_analyst_agent(self.llm),
            "news_analyst": news_analyst_agent(self.llm),
            "fundamentals_analyst": fundamentals_analyst_agent(self.llm),
            "risk_analyst": risk_analyst_agent(self.llm),
            "PM_agent": PM_agent(self.llm),
        }

    def _create_hitl_approval_placeholder(self):
        def placeholder(state: AgentState):
            # Gap B will replace this with interrupt/resume approval logic later.
            del state
            return {}

        return placeholder


if __name__ == "__main__":
    tradeagent = IntelliFin_Assistant()
    result = tradeagent.run(
        "AAPL", date="2024-01-15T00:00:00Z", current_position_pct=20
    )
    tradeagent.visualize()
    print(result.get("PM_report"))
    print(result.get("Action"))
    print(result.get("Target_position_pct"), "%")
