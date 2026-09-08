"""Agent state — ReAct loop immutable state.

Inspired by Claude Code query.ts State pattern.
"""

from dataclasses import dataclass, field, replace
from enum import Enum


class TerminalReason(Enum):
    """Why the agent loop terminated.

    Inspired by Claude Code query.ts Terminal type — 10 terminal conditions
    checked at multiple points in the loop. Each reason maps to
    a specific exit path with different recovery behavior.
    """

    # Normal exits
    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    MAX_BUDGET_USD = "max_budget_usd"
    # User interrupt exits
    ABORTED_STREAMING = "aborted_streaming"
    ABORTED_TOOLS = "aborted_tools"
    # Recovery-failure exits
    PROMPT_TOO_LONG = "prompt_too_long"
    # Hook-prevented exits
    STOP_HOOK_PREVENTED = "stop_hook_prevented"
    HOOK_STOPPED = "hook_stopped"
    # Error exits
    MODEL_ERROR = "model_error"
    BLOCKING_LIMIT = "blocking_limit"

    @property
    def is_user_initiated(self) -> bool:
        return self in (TerminalReason.ABORTED_STREAMING, TerminalReason.ABORTED_TOOLS)

    @property
    def is_recoverable(self) -> bool:
        return self not in (TerminalReason.MODEL_ERROR, TerminalReason.BLOCKING_LIMIT)


class TransitionType(Enum):
    """Why the agent loop continued to the next iteration.
    Inspired by Claude Code query.ts transition field —
    prevents infinite recovery loops by tracking WHY each
    iteration happened."""

    TOOL_CALLS = "tool_calls"
    TEXT_RESPONSE = "text_response"
    COMPACT_TRIGGERED = "compact_triggered"
    ERROR_RECOVERY = "error_recovery"
    ATTACHMENT_INJECTED = "attachment_injected"
    CONTINUATION_PROMPT = "continuation_prompt"


@dataclass(frozen=True)
class AgentLoopState:
    """Immutable state for the ReAct agent loop.

    Each iteration creates a NEW instance via next_iteration()
    instead of mutating. This prevents stale references and
    makes all recovery paths explicit and auditable.

    Inspired by Claude Code's immutable State pattern in query.ts.
    """

    messages: tuple = ()  # tuple = immutable sequence
    iteration: int = 0
    transition: TransitionType | None = None
    cost_usd: float = 0.0
    started_at: float = 0.0
    tool_call_counts: dict = field(default_factory=dict)

    def next_iteration(self, **kwargs) -> "AgentLoopState":
        """Create a new state for the next iteration.
        Usage:
            state = state.next_iteration(
                transition=TransitionType.TOOL_CALLS,
                tool_call_counts={"get_price": 1},
            )
        """
        updates = {"iteration": self.iteration + 1}
        updates.update(kwargs)
        return replace(self, **updates)

    def with_messages(self, messages: tuple) -> "AgentLoopState":
        """Replace messages (immutable update)."""
        return replace(self, messages=messages)

    def record_tool_call(self, tool_name: str) -> "AgentLoopState":
        """Record a tool call count."""
        new_counts = dict(self.tool_call_counts)
        new_counts[tool_name] = new_counts.get(tool_name, 0) + 1
        return replace(self, tool_call_counts=new_counts)

    def add_cost(self, usd: float) -> "AgentLoopState":
        """Add to cumulative cost."""
        return replace(self, cost_usd=self.cost_usd + usd)
