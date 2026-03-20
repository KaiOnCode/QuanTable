import os
import sys
from dotenv import load_dotenv
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv("properties.env")
os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2","false")
os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY","")

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph,START,END
from agents.utils.agent_tools import *
from agentgraph.state import AgentState
from agents.market_analyst import market_analyst_agent
from agents.news_analyst import news_analyst_agent
from agents.fundamentals_analyst import fundamentals_analyst_agent
from agents.risk_analyst import risk_analyst_agent
from agents.PM import PM_agent
from langgraph.checkpoint.memory import MemorySaver

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
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
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
    def __init__(self):
        # self.llm = ChatOpenAI(
        #     model="deepseek-v3-250324",
        #     openai_api_key="",
        #     openai_api_base="",
        #     )
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY")
            )

        self.tool_nodes = self._create_tool_nodes()
        self.agent_nodes = self._create_agent_nodes()

        wf=StateGraph(AgentState)

        for node_name, node in self.tool_nodes.items():
            # market, news, fundamentals 分析师的可能路径
            path_map = {
                f"{node_name}_tool": f"{node_name}_tool",
                "risk_analyst": "risk_analyst",
                END: END
            }
            
            wf.add_node(f"{node_name}_tool", node) # 工具节点
            wf.add_node(node_name, self.agent_nodes[node_name]) # 代理节点
            wf.add_conditional_edges(
                node_name,
                should_continue(node_name),
                path_map
                ) # 条件边（工具节点或下一步代理节点）三个分析节点到风险分析师
            wf.add_edge(f"{node_name}_tool", node_name) # 工具节点到代理节点的边

        # 单独添加 risk_analyst 节点（没有工具节点）
        wf.add_node("risk_analyst", self.agent_nodes["risk_analyst"])
        wf.add_conditional_edges(
            "risk_analyst",
            should_continue("risk_analyst"),
            {
                "PM_agent": "PM_agent",
                END: END
            }
        ) # risk_analyst 的条件边：直接到 PM_agent 或结束

        wf.add_node("PM_agent", self.agent_nodes["PM_agent"]) # PM节点

        wf.add_edge(START, "market_analyst")
        wf.add_edge(START, "news_analyst")
        wf.add_edge(START, "fundamentals_analyst")
        wf.add_edge("PM_agent", END)

        # 初始化内存，在图运行时存储状态（状态持久化）
        checkpoint=MemorySaver() # 可拓展redis,mongoDB
        self.wf=wf.compile(checkpointer=checkpoint)

    def run(self, ticker: str, date: str = None, current_position_pct: float = 0.0):
        # 初始化状态
        initial_state = {
            "ticker": ticker,
            "date": date,
            "current_position_pct": current_position_pct,
        }
        return self.wf.invoke(
            initial_state,
            config={"configurable": {"thread_id": "42"}}  # 相当于会话id
        ) 
    def visualize(self):
        with open("graph.png", "wb") as f:
            f.write(self.wf.get_graph().draw_mermaid_png())

    def _create_tool_nodes(self):
        return {
            "market_analyst": create_tool_node_wrapper("market_analyst", [get_price, get_indicators]),
            "news_analyst": create_tool_node_wrapper("news_analyst", [get_news]),
            "fundamentals_analyst": create_tool_node_wrapper("fundamentals_analyst", [get_fundamentals]),
        }

    def _create_agent_nodes(self):
        return {
            "market_analyst": market_analyst_agent(self.llm),
            "news_analyst": news_analyst_agent(self.llm),
            "fundamentals_analyst": fundamentals_analyst_agent(self.llm),
            "risk_analyst": risk_analyst_agent(self.llm),
            "PM_agent": PM_agent(self.llm),
        }


if __name__ == "__main__":
    tradeagent = IntelliFin_Assistant()
    result = tradeagent.run("AAPL",date="2024-01-15T00:00:00Z",current_position_pct=20)
    tradeagent.visualize()
    print(result.get("PM_report"))
    print(result.get("Action"))
    print(result.get("Target_position_pct"),"%")