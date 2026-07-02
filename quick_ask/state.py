# pyright: reportGeneralTypeIssues=false
"""AgentState for the LEGACY LangGraph 5-agent pipeline.

FROZEN — do not modify. Used only by quick_ask/orchestrator.py.
"""

from typing import Annotated, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState, add_messages


class AgentState(MessagesState):
    """Legacy LangGraph state for the 5-agent pipeline.

    Workflow: 3 parallel analysts → risk → PM → memory.
    """

    ticker: Annotated[str, "Stock ticker, e.g. AAPL"]
    date: Annotated[str, "Date, e.g. 2024-01-15T00:00:00Z"]
    current_position_pct: Annotated[float, "Current position % (0-100)"] = 0.0

    # Per-agent message lists
    market_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    news_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    fundamentals_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    risk_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    PM_agent_messages: Annotated[List[BaseMessage], add_messages] = []

    # Stage 1: parallel analysts
    market_report: Annotated[Optional[str], "Market analyst report"] = ""
    news_report: Annotated[Optional[str], "News analyst report"] = ""
    fundamental_report: Annotated[Optional[str], "Fundamentals analyst report"] = ""

    # Stage 2: risk analyst
    risk_report: Annotated[Optional[str], "Risk analyst report"] = ""

    # Stage 3: PM decision
    PM_report: Annotated[Optional[str], "PM final report"] = ""
    Action: Annotated[Optional[str], "BUY/HOLD/SELL"] = ""
    Target_position_pct: Annotated[Optional[float], "Target position % (0-100)"] = 0.0

    # Memory
    relevant_memories: list = []
    memory_context: str = ""
    memory_enabled: bool = True
    memory_record_id: str = ""
    session_id: str = ""
    account_id: str = ""
    decision_id: str = ""
    started_at: str = ""
    strategy_id: str = "default"
