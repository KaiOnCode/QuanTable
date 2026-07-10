from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, NotRequired, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from broker.backtest_data import ToolDataService
from broker.gateway import BrokerGateway

from agent.run_context import AgentRunContext, bind_agent_run_context

if TYPE_CHECKING:
    from agent.loop import AgentLoop


class BacktestDecisionError(RuntimeError):
    pass


class LoopMessage(TypedDict):
    role: str
    name: NotRequired[str]
    content: NotRequired[str]


class AgentRunResult(TypedDict, total=False):
    messages: list[LoopMessage]


class BacktestDecisionResult(TypedDict):
    status: str
    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float
    confidence: float
    rationale: str
    execution: Literal["held", "filled", "new", "rejected"]


class BacktestDecisionPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)
    execution: Literal["held", "filled", "new", "rejected"]


class AgentLoopProtocol(Protocol):
    def run(self, user_message: str, **kwargs: str | None) -> AgentRunResult: ...


class _AgentLoopInvoker:
    def __init__(self, loop: "AgentLoop") -> None:
        self._loop = loop

    def run(self, user_message: str, **kwargs: str | None) -> AgentRunResult:
        session_id = kwargs.get("session_id")
        system_prompt = kwargs.get("system_prompt")
        if session_id is not None and not isinstance(session_id, str):
            raise BacktestDecisionError("backtest session_id must be a string")
        if system_prompt is not None and not isinstance(system_prompt, str):
            raise BacktestDecisionError("backtest system_prompt must be a string")
        result = self._loop.run(
            user_message,
            session_id=session_id,
            system_prompt=system_prompt,
        )
        raw_messages = result.get("messages", [])
        if not isinstance(raw_messages, list):
            raise BacktestDecisionError("backtest loop returned invalid messages")
        messages: list[LoopMessage] = []
        for raw_message in raw_messages:
            if not isinstance(raw_message, dict):
                continue
            role = raw_message.get("role")
            if not isinstance(role, str):
                continue
            message: LoopMessage = {"role": role}
            name = raw_message.get("name")
            content = raw_message.get("content")
            if isinstance(name, str):
                message["name"] = name
            if isinstance(content, str):
                message["content"] = content
            messages.append(message)
        return {"messages": messages}


class BacktestDecisionAdapter:
    def __init__(
        self,
        *,
        data_service: ToolDataService | None = None,
        broker: BrokerGateway | None = None,
        loop_factory: Callable[[], AgentLoopProtocol] | None = None,
    ) -> None:
        self._data_service = data_service
        self._broker = broker
        self._loop_factory = loop_factory or self._default_loop

    def run(
        self,
        ticker: str,
        *,
        date: str,
        as_of: str,
        current_position_pct: float,
        execution_enabled: bool,
        strategy_id: str,
        account_id: str,
        session_id: str,
        context: AgentRunContext | None = None,
    ) -> BacktestDecisionResult:
        del date, current_position_pct, execution_enabled
        run_context = context or self._build_context(
            ticker=ticker,
            as_of=as_of,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
        )
        loop = self._loop_factory()
        system_prompt = (
            "You are a point-in-time backtest decision agent. Use only the available "
            "scoped tools. You must call submit_backtest_decision exactly once with a "
            "structured BUY, SELL, or HOLD decision. Do not infer a decision in prose."
        )
        try:
            with bind_agent_run_context(run_context):
                result = loop.run(
                    f"Make the single decision for {ticker} as of {as_of}.",
                    session_id=session_id,
                    system_prompt=system_prompt,
                )
        except Exception as error:
            raise BacktestDecisionError("backtest agent execution failed") from error
        decision_messages: list[LoopMessage] = [
            message
            for message in result.get("messages", [])
            if message.get("role") == "tool"
            and message.get("name") == "submit_backtest_decision"
        ]
        if len(decision_messages) != 1:
            raise BacktestDecisionError(
                "backtest requires exactly one decision tool call"
            )
        content = decision_messages[0].get("content")
        if not isinstance(content, str):
            raise BacktestDecisionError(
                "backtest decision tool returned invalid content"
            )
        try:
            decision = BacktestDecisionPayload.model_validate_json(content)
        except (json.JSONDecodeError, ValidationError) as error:
            raise BacktestDecisionError(
                "backtest decision tool returned invalid structured decision"
            ) from error
        return {
            "status": decision.status,
            "action": decision.action,
            "target_position_pct": decision.target_position_pct,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
            "execution": decision.execution,
        }

    def _build_context(
        self,
        *,
        ticker: str,
        as_of: str,
        strategy_id: str,
        account_id: str,
        session_id: str,
    ) -> AgentRunContext:
        if self._data_service is None or self._broker is None:
            raise BacktestDecisionError(
                "backtest adapter requires scoped data and broker"
            )
        return AgentRunContext(
            data_service=self._data_service,
            as_of=as_of,
            broker=self._broker,
            strategy_id=strategy_id,
            account_id=account_id,
            session_id=session_id,
            ticker=ticker,
        )

    @staticmethod
    def _default_loop() -> AgentLoopProtocol:
        from agent.loop import AgentConfig, AgentLoop

        allowed_tools = frozenset(
            {
                "get_price",
                "get_indicators",
                "get_fundamentals",
                "get_news",
                "search_skills",
                "submit_backtest_decision",
            }
        )
        return _AgentLoopInvoker(
            AgentLoop(config=AgentConfig(allowed_tools=allowed_tools))
        )
