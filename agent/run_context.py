from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Iterator

from broker.backtest_data import ToolDataService
from broker.gateway import BrokerGateway


@dataclass(frozen=True, slots=True)
class AgentRunContext:
    data_service: ToolDataService
    as_of: str
    broker: BrokerGateway
    strategy_id: str
    account_id: str
    session_id: str
    ticker: str


_CURRENT_AGENT_RUN_CONTEXT: ContextVar[AgentRunContext | None] = ContextVar(
    "agent_run_context", default=None
)


def current_agent_run_context() -> AgentRunContext | None:
    return _CURRENT_AGENT_RUN_CONTEXT.get()


@contextmanager
def bind_agent_run_context(context: AgentRunContext) -> Iterator[None]:
    token: Token[AgentRunContext | None] = _CURRENT_AGENT_RUN_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_AGENT_RUN_CONTEXT.reset(token)
