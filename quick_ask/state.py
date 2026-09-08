"""AgentState for the TradingAgents-style multi-agent pipeline.

12 agents across 5 stages: Analysts → Debate → Trader → Risk → PM.
Supports 3 modes: fast (no debate), standard (1 round), deep (3 rounds).
"""

from __future__ import annotations

from typing import Annotated, Any, List, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState, add_messages


class AgentState(MessagesState):
    """Full state for the 12-agent pipeline."""

    # ── Input ──────────────────────────────────────────────
    ticker: str = ""
    date: str = ""
    current_position_pct: float = 0.0
    mode: str = "standard"  # fast | standard | deep
    max_debate_rounds: int = 1
    max_risk_rounds: int = 1

    # ── Per-agent message lists ───────────────────────────
    market_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    sentiment_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    news_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    fundamentals_analyst_messages: Annotated[List[BaseMessage], add_messages] = []
    bull_researcher_messages: Annotated[List[BaseMessage], add_messages] = []
    bear_researcher_messages: Annotated[List[BaseMessage], add_messages] = []
    research_manager_messages: Annotated[List[BaseMessage], add_messages] = []
    trader_messages: Annotated[List[BaseMessage], add_messages] = []
    aggressive_messages: Annotated[List[BaseMessage], add_messages] = []
    conservative_messages: Annotated[List[BaseMessage], add_messages] = []
    neutral_messages: Annotated[List[BaseMessage], add_messages] = []
    risk_analyst_messages: Annotated[List[BaseMessage], add_messages] = []  # legacy
    PM_agent_messages: Annotated[List[BaseMessage], add_messages] = []

    # ── Stage 1: Analyst reports ──────────────────────────
    market_report: str = ""
    sentiment_report: str = ""
    news_report: str = ""
    fundamental_report: str = ""

    # ── Stage 2: Investment debate ────────────────────────
    investment_debate_state: dict[str, Any] = {}
    investment_plan: str = ""  # Research Manager output

    # ── Stage 3: Trader proposal ──────────────────────────
    trader_proposal: str = ""

    # ── Stage 4: Risk discussion ──────────────────────────
    risk_debate_state: dict[str, Any] = {}
    risk_report: str = ""  # legacy

    # ── Stage 5: PM final decision ────────────────────────
    PM_report: str = ""
    Action: str = ""
    Target_position_pct: float = 0.0

    # ── Memory ────────────────────────────────────────────
    relevant_memories: list = []
    memory_context: str = ""
    memory_enabled: bool = True
    memory_record_id: str = ""
    session_id: str = ""
    account_id: str = ""
    decision_id: str = ""
    strategy_id: str = "default"
    started_at: str = ""

    # ── Instrument context (TradingAgents: deterministic identity) ──
    instrument_context: str = ""
