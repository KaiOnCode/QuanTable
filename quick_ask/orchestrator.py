"""IntelliFin_Assistant — TradingAgents-style 12-agent LangGraph pipeline."""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from quick_ask.agents.analysts.fundamentals_analyst import (
    fundamentals_analyst_agent,
)
from quick_ask.agents.analysts.market_analyst import market_analyst_agent
from quick_ask.agents.analysts.news_analyst import news_analyst_agent
from quick_ask.agents.analysts.risk_analyst import risk_analyst_agent
from quick_ask.agents.analysts.sentiment_analyst import sentiment_analyst_agent
from quick_ask.agents.managers.PM import PM_agent
from quick_ask.agents.researchers.bear_researcher import bear_researcher_agent
from quick_ask.agents.researchers.bull_researcher import bull_researcher_agent
from quick_ask.agents.researchers.research_manager import (
    research_manager_agent,
)
from quick_ask.agents.risk_mgmt.aggressive_analyst import aggressive_analyst_agent
from quick_ask.agents.risk_mgmt.conservative_analyst import (
    conservative_analyst_agent,
)
from quick_ask.agents.risk_mgmt.neutral_analyst import neutral_analyst_agent
from quick_ask.agents.trader.trader import trader_agent
from quick_ask.agents.utils.agent_tools import (
    get_balance_sheet,
    get_cashflow,
    get_fundamentals,
    get_global_news,
    get_income_statement,
    get_indicators,
    get_macro,
    get_macro_indicators,
    get_news,
    get_price,
    get_sector,
    get_sentiment,
    get_verified_market_snapshot,
)
from quick_ask.state import AgentState
from server.llm_defaults import DEFAULT_QUICK_THINK_MODEL

load_dotenv("properties.env")
logger = logging.getLogger(__name__)

MARKET_TOOLS = [get_price, get_indicators, get_verified_market_snapshot]
SENTIMENT_TOOLS = [get_sentiment, get_news, get_sector]
NEWS_TOOLS = [get_news, get_global_news, get_macro_indicators, get_macro]
FUNDAMENTALS_TOOLS = [
    get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement,
]


# ── Core helpers ────────────────────────────────────────────

def _invoke(fn, state):
    """Call agent — supports plain fn, LangChain Runnable, raw AIMessage."""
    result = fn.invoke(state) if hasattr(fn, "invoke") else fn(state)
    if not isinstance(result, dict):
        result = {"messages": [result]}
    return result


def _last_msg(result, key):
    """Get last message from result dict, trying per-agent key then shared."""
    for k in (key, "messages"):
        msgs = result.get(k, [])
        if msgs:
            return msgs[-1]
    return None


def _has_tc(state, key):
    """Check if last per-agent message has pending tool calls."""
    msgs = state.get(key, [])
    return bool(msgs and getattr(msgs[-1], "tool_calls", None))


# ── Graph nodes ─────────────────────────────────────────────

def _msg_clear_node(label):
    """Clear shared messages, insert context anchor."""
    def _run(state):
        ops = [RemoveMessage(id=m.id) for m in state["messages"]]
        ops.append(HumanMessage(content=f"Proceed. {label}"))
        return {"messages": ops}
    return _run


def _tool_node(tools, msg_key):
    """ToolNode that reads/writes per-agent message list."""
    base = ToolNode(tools)
    def _run(state):
        state["messages"] = state.get(msg_key, [])
        r = base.invoke(state)
        return {msg_key: r["messages"]}
    return _run


def _agent_node(fn, msg_key, report_key="", on_start=None, node_name=""):
    """Agent node — pass through all result keys. Inject debate/risk state."""
    def _run(state):
        if on_start:
            on_start(node_name)
        state["messages"] = state.get(msg_key, [])
        # Flatten debate state for agents that need it as template vars
        db = state.get("investment_debate_state", {})
        if db:
            state.setdefault("debate_history", db.get("history", ""))
        rb = state.get("risk_debate_state", {})
        if rb:
            state.setdefault("current_aggressive_response", rb.get("current_aggressive_response", ""))
            state.setdefault("current_conservative_response", rb.get("current_conservative_response", ""))
            state.setdefault("current_neutral_response", rb.get("current_neutral_response", ""))
        r = _invoke(fn, state)
        # If result already has the per-agent key, pass everything through
        if msg_key in r:
            out = dict(r)
            out.setdefault("messages", out.get(msg_key, []))
            # Extract report from last per-agent message if no tool_calls
            per_msgs = out.get(msg_key, [])
            if report_key and per_msgs:
                last = per_msgs[-1]
                if not getattr(last, "tool_calls", None):
                    out[report_key] = str(last.content)
            return out
        # Bare message result — wrap
        msg = _last_msg(r, msg_key) or _last_msg(r, "messages")
        if msg is None:
            return {}
        out = {msg_key: [msg], "messages": [msg]}
        if report_key and not getattr(msg, "tool_calls", None):
            out[report_key] = str(msg.content)
        return out
    return _run


def _debate_node(fn, msg_key, prefix, on_start=None, node_name=""):
    """Debate agent — injects debate state into top-level keys for template vars."""
    def _run(state):
        if on_start:
            on_start(node_name)
        state["messages"] = state.get(msg_key, [])
        db = state.get("investment_debate_state", {})
        # Flatten debate state so {{history}} and {{current_response}} work
        state["history"] = db.get("history", "")
        state["current_response"] = db.get("current_response", "")
        r = _invoke(fn, state)
        msg = _last_msg(r, msg_key) or _last_msg(r, "messages")
        if msg is None:
            return {}
        content = str(msg.content)
        return {
            msg_key: [msg], "messages": [msg],
            "investment_debate_state": {
                **db, "count": db.get("count", 0) + 1,
                "history": db.get("history", "") + f"\n{prefix}: {content[:500]}\n",
                "current_response": f"{prefix}: {content[:500]}",
            },
        }
    return _run


def _risk_node(fn, msg_key, name, on_start=None, node_name=""):
    """Risk debate agent — flattens risk state for template vars."""
    def _run(state):
        if on_start:
            on_start(node_name)
        state["messages"] = state.get(msg_key, [])
        rb = state.get("risk_debate_state", {})
        state["history"] = rb.get("history", "")
        # Map response keys: store each speaker's last response
        resp_key = {
            "Aggressive": "current_aggressive_response",
            "Conservative": "current_conservative_response",
            "Neutral": "current_neutral_response",
        }
        for spk, key in resp_key.items():
            state[key] = rb.get(key, "")
        r = _invoke(fn, state)
        msg = _last_msg(r, msg_key) or _last_msg(r, "messages")
        if msg is None:
            return {}
        content = str(msg.content)
        # Save THIS speaker's response into the risk state for others to read
        updates = {
            **rb, "count": rb.get("count", 0) + 1,
            "history": rb.get("history", "") + f"\n{name}: {content[:500]}\n",
            "latest_speaker": name,
        }
        if name in resp_key:
            updates[resp_key[name]] = content[:500]
        return {
            msg_key: [msg], "messages": [msg],
            "risk_debate_state": updates,
        }
    return _run


# ── Conditionals ────────────────────────────────────────────

def _debate_next(state):
    c = state.get("investment_debate_state", {}).get("count", 0)
    return "research_manager" if c >= 2 * state.get("max_debate_rounds", 1) else "bull_researcher"

def _risk_next(state):
    c = state.get("risk_debate_state", {}).get("count", 0)
    return "risk_analyst" if c >= 3 * state.get("max_risk_rounds", 1) else "aggressive_analyst"

# Tool-loop conditional: agent → tool or next
def _tc_a(state, mk, tn, nn):
    return tn if _has_tc(state, mk) else nn

# Tool-loop conditional: tool → agent or next
def _tc_t(state, mk, tn, an):
    return tn if _has_tc(state, mk) else an


# ── Orchestrator ────────────────────────────────────────────

class IntelliFin_Assistant:
    """12-agent TradingAgents-style analysis pipeline."""

    def __init__(self, on_node_start=None):
        self.llm = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", DEFAULT_QUICK_THINK_MODEL),
            openai_api_key=lambda: os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE") or None,
            temperature=0.0,
            max_retries=3,
            request_timeout=120,
        )
        self._on_node_start = on_node_start

    def _build(self) -> CompiledStateGraph:
        wf = StateGraph(AgentState)

        # ── Analysts ──────────────────────────────────────
        mk, mt, mcl = "market_analyst", "market_tool", "market_clear"
        sk, st, scl = "sentiment_analyst", "sentiment_tool", "sentiment_clear"
        nk, nt, ncl = "news_analyst", "news_tool", "news_clear"
        fk, ft, fcl = "fundamentals_analyst", "fundamentals_tool", "fundamentals_clear"

        wf.add_node(mk, _agent_node(market_analyst_agent(self.llm), "market_analyst_messages", "market_report", on_start=self._on_node_start, node_name="market_analyst"))
        wf.add_node(mt, _tool_node(MARKET_TOOLS, "market_analyst_messages"))
        wf.add_node(mcl, _msg_clear_node("market→sentiment"))

        wf.add_node(sk, _agent_node(sentiment_analyst_agent(self.llm), "sentiment_analyst_messages", "sentiment_report", on_start=self._on_node_start, node_name="sentiment_analyst"))
        wf.add_node(st, _tool_node(SENTIMENT_TOOLS, "sentiment_analyst_messages"))
        wf.add_node(scl, _msg_clear_node("sentiment→news"))

        wf.add_node(nk, _agent_node(news_analyst_agent(self.llm), "news_analyst_messages", "news_report", on_start=self._on_node_start, node_name="news_analyst"))
        wf.add_node(nt, _tool_node(NEWS_TOOLS, "news_analyst_messages"))
        wf.add_node(ncl, _msg_clear_node("news→fundamentals"))

        wf.add_node(fk, _agent_node(fundamentals_analyst_agent(self.llm), "fundamentals_analyst_messages", "fundamental_report", on_start=self._on_node_start, node_name="fundamentals_analyst"))
        wf.add_node(ft, _tool_node(FUNDAMENTALS_TOOLS, "fundamentals_analyst_messages"))
        wf.add_node(fcl, _msg_clear_node("fundamentals→next"))

        # ── Debate ────────────────────────────────────────
        buk, bek, rmk = "bull_researcher", "bear_researcher", "research_manager"
        wf.add_node(buk, _debate_node(bull_researcher_agent(self.llm), "bull_researcher_messages", "Bull", on_start=self._on_node_start, node_name="bull_researcher"))
        wf.add_node(bek, _debate_node(bear_researcher_agent(self.llm), "bear_researcher_messages", "Bear", on_start=self._on_node_start, node_name="bear_researcher"))
        wf.add_node(rmk, _agent_node(research_manager_agent(self.llm), "research_manager_messages", "investment_plan", on_start=self._on_node_start, node_name="research_manager"))

        # ── Trader ────────────────────────────────────────
        wf.add_node("trader", _agent_node(trader_agent(self.llm), "trader_messages", "trader_proposal", on_start=self._on_node_start, node_name="trader"))

        # ── Risk ──────────────────────────────────────────
        ak, ck, nuk = "aggressive_analyst", "conservative_analyst", "neutral_analyst"
        wf.add_node(ak, _risk_node(aggressive_analyst_agent(self.llm), "aggressive_messages", "Aggressive", on_start=self._on_node_start, node_name="aggressive_analyst"))
        wf.add_node(ck, _risk_node(conservative_analyst_agent(self.llm), "conservative_messages", "Conservative", on_start=self._on_node_start, node_name="conservative_analyst"))
        wf.add_node(nuk, _risk_node(neutral_analyst_agent(self.llm), "neutral_messages", "Neutral", on_start=self._on_node_start, node_name="neutral_analyst"))
        wf.add_node("risk_analyst", _agent_node(risk_analyst_agent(self.llm), "risk_analyst_messages", "risk_report", on_start=self._on_node_start, node_name="risk_analyst"))

        # ── PM ────────────────────────────────────────────
        wf.add_node("PM_agent", _agent_node(PM_agent(self.llm), "PM_agent_messages", "", on_start=self._on_node_start, node_name="PM_agent"))

        # ── Edges ─────────────────────────────────────────
        wf.set_entry_point(mk)
        # Market: agent ⇄ tool → clear → sentiment
        wf.add_conditional_edges(mk, lambda s: _tc_a(s, "market_analyst_messages", mt, mcl), {mt: mt, mcl: mcl})
        wf.add_edge(mt, mk)  # tool always back to agent — agent decides when done
        wf.add_edge(mcl, sk)
        # Sentiment: agent ⇄ tool → clear → news
        wf.add_conditional_edges(sk, lambda s: _tc_a(s, "sentiment_analyst_messages", st, scl), {st: st, scl: scl})
        wf.add_edge(st, sk)
        wf.add_edge(scl, nk)
        # News: agent ⇄ tool → clear → fundamentals
        wf.add_conditional_edges(nk, lambda s: _tc_a(s, "news_analyst_messages", nt, ncl), {nt: nt, ncl: ncl})
        wf.add_edge(nt, nk)
        wf.add_edge(ncl, fk)
        # Fundamentals: agent ⇄ tool → clear → mode routing
        wf.add_conditional_edges(fk, lambda s: _tc_a(s, "fundamentals_analyst_messages", ft, fcl), {ft: ft, fcl: fcl})
        wf.add_edge(ft, fk)
        # Mode routing: fast → PM, standard/deep → debate
        wf.add_conditional_edges(fcl, lambda s: "PM_agent" if s.get("mode") == "fast" else buk, {"PM_agent": "PM_agent", buk: buk})
        # Debate: bull → bear → (continue or research_manager) → trader
        wf.add_edge(buk, bek)
        wf.add_conditional_edges(bek, _debate_next, {buk: buk, rmk: rmk})
        wf.add_edge(rmk, "trader")
        # Trader → risk discussion
        wf.add_edge("trader", ak)
        wf.add_edge(ak, ck)
        wf.add_edge(ck, nuk)
        wf.add_conditional_edges(nuk, _risk_next, {ak: ak, "risk_analyst": "risk_analyst"})
        # PM
        wf.add_edge("risk_analyst", "PM_agent")
        wf.add_edge("PM_agent", END)

        return wf.compile()

    @property
    def wf(self):
        if not hasattr(self, "_wf"):
            self._wf = self._build()
        return self._wf

    def run(self, **kw):
        return self.wf.invoke(_init(**kw))

    def stream(self, **kw):
        yield from self.wf.stream(_init(**kw), stream_mode="updates")


def _init(**kw) -> dict:
    t, d, m = kw.get("ticker", ""), kw.get("date", ""), str(kw.get("mode", "standard"))
    return {
        "ticker": t, "date": d,
        "current_position_pct": kw.get("current_position_pct", 0.0),
        "mode": m,
        "max_debate_rounds": 0 if m == "fast" else (3 if m == "deep" else 1),
        "max_risk_rounds": 0 if m == "fast" else (3 if m == "deep" else 1),
        "instrument_context": f"Stock: {t}",
        "session_id": str(kw.get("session_id", "")),
        "strategy_id": str(kw.get("strategy_id", "default")),
        "account_id": str(kw.get("account_id", "default")),
        "decision_id": str(kw.get("decision_id", "")),
        "memory_enabled": kw.get("memory_enabled", True),
        "memory_context": str(kw.get("memory_context", "")),
        "relevant_memories": kw.get("relevant_memories", []),
        "messages": [HumanMessage(content=f"Analyze {t}")],
    }
