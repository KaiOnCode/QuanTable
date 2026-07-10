from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, NotRequired, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from scanner.models import ScanCondition, ScanResponse

if TYPE_CHECKING:
    from agent.loop import AgentLoop


class ScannerCompilationError(RuntimeError):
    pass


class LoopMessage(TypedDict):
    role: str
    name: NotRequired[str]
    content: NotRequired[str]


class AgentRunResult(TypedDict, total=False):
    messages: list[LoopMessage]


class ScannerLoopProtocol(Protocol):
    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AgentRunResult: ...


class ScannerToolPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["ok"]
    conditions: tuple[ScanCondition, ...] = Field(min_length=1)
    result: ScanResponse


class ScannerCompilationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    conditions: tuple[ScanCondition, ...]
    result: ScanResponse


class _AgentLoopInvoker:
    def __init__(self, loop: AgentLoop) -> None:
        self._loop = loop

    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AgentRunResult:
        result = self._loop.run(
            user_message,
            session_id=session_id,
            system_prompt=system_prompt,
        )
        raw_messages = result.get("messages", [])
        if not isinstance(raw_messages, list):
            raise ScannerCompilationError("scanner loop returned invalid messages")
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


class ScannerCompilationService:
    def __init__(
        self,
        loop_factory: Callable[[], ScannerLoopProtocol] | None = None,
        llm_available: bool = True,
    ) -> None:
        self._loop_factory = loop_factory or self._default_loop
        self._llm_available = llm_available

    @property
    def can_compile(self) -> bool:
        return self._llm_available

    def compile(self, prompt: str, session_id: str) -> ScannerCompilationResult:
        if not self.can_compile:
            raise ScannerCompilationError("scanner LLM is not configured")
        try:
            response = self._loop_factory().run(
                prompt,
                session_id=session_id,
                system_prompt=(
                    "Compile the request into frozen scanner conditions. You must call "
                    "scan_tracked_universe exactly once. Do not produce scanner results "
                    "in prose and do not call any other data or workspace tool."
                ),
            )
        except (OSError, RuntimeError, TimeoutError, ValueError) as error:
            raise ScannerCompilationError("scanner agent execution failed") from error
        tool_messages = [
            message
            for message in response.get("messages", [])
            if message.get("role") == "tool"
            and message.get("name") == "scan_tracked_universe"
        ]
        if len(tool_messages) != 1:
            raise ScannerCompilationError(
                "scanner must call scan_tracked_universe exactly once"
            )
        content = tool_messages[0].get("content")
        if not isinstance(content, str):
            raise ScannerCompilationError("scanner tool returned invalid content")
        try:
            payload = ScannerToolPayload.model_validate_json(content)
        except ValidationError as error:
            raise ScannerCompilationError(
                "scanner tool returned invalid structured result"
            ) from error
        return ScannerCompilationResult(
            conditions=payload.conditions,
            result=payload.result,
        )

    @staticmethod
    def _default_loop() -> ScannerLoopProtocol:
        from agent.loop import AgentConfig, AgentLoop

        allowed_tools = frozenset({"scan_tracked_universe", "search_skills"})
        return _AgentLoopInvoker(
            AgentLoop(config=AgentConfig(allowed_tools=allowed_tools))
        )
