from __future__ import annotations

from typing import Final, Literal


type BacktestDecisionErrorCode = Literal[
    "agent_failed",
    "decision_context_invalid",
    "decision_policy_invalid",
    "decision_transient_exhausted",
    "provider_failed",
    "decision_schema_invalid",
]
type BacktestDecisionErrorStage = Literal[
    "agent_execution",
    "context",
    "policy",
    "provider",
    "transient",
    "structured_output",
    "tool_call",
    "tool_payload",
]

_BACKTEST_DECISION_ERROR_MESSAGES: Final[dict[BacktestDecisionErrorCode, str]] = {
    "agent_failed": "Backtest agent execution failed",
    "decision_context_invalid": "Backtest decision context is unavailable",
    "decision_policy_invalid": "Backtest decision violates the frozen policy",
    "decision_transient_exhausted": "Backtest decision provider remained unavailable",
    "provider_failed": "Backtest decision provider failed",
    "decision_schema_invalid": "Backtest decision could not be validated",
}


class BacktestDecisionError(RuntimeError):
    def __init__(
        self,
        *,
        code: BacktestDecisionErrorCode,
        stage: BacktestDecisionErrorStage,
        decision_date: str,
        attempt: int,
    ) -> None:
        self.code: BacktestDecisionErrorCode = code
        self.stage: BacktestDecisionErrorStage = stage
        self.decision_date = decision_date
        self.attempt = attempt
        super().__init__(_BACKTEST_DECISION_ERROR_MESSAGES[code])

    @property
    def safe_message(self) -> str:
        return _BACKTEST_DECISION_ERROR_MESSAGES[self.code]
