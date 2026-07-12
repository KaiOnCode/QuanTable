from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrategyConfigPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    name: str = "Untitled Strategy"
    description: str = ""
    type: Literal["agent", "quant", "hitl"] = "agent"
    status: Literal["draft", "active", "paused", "stopped", "archived"] = "draft"
    tickers: list[str] = Field(default_factory=list)
    beliefs: list[str] = Field(default_factory=list)
    belief_weights: dict[str, float] = Field(default_factory=dict)
    active_agents: list[str] = Field(
        default_factory=lambda: ["market", "news", "fundamentals", "pm"]
    )
    debate_rounds: int = 2
    risk_debate_rounds: int = 2
    agent_model: str = "deepseek-chat"
    deep_think_model: str = "deepseek-chat"
    agent_temperature: float = 0.0
    enable_debate_mode: bool = True
    enable_cross_review: bool = False
    quant_strategy_name: str | None = None
    quant_params: dict[str, JsonValue] = Field(default_factory=dict)
    alpha_zoo_factors: list[str] = Field(default_factory=list)
    execution_frequency: str = "daily"
    execution_time: str = "09:30"
    initial_capital: float = 100_000.0
    max_position_pct: float = 80.0
    max_drawdown_pct: float = 100.0
    hitl_enabled: bool = False
    hitl_trigger_position_change_pct: float = 20.0
    hitl_trigger_signal_conflict: bool = True
    hitl_trigger_confidence_below: float = 0.6
    hitl_timeout_hours: float = 2.0
    memory_enabled: bool = True
    memory_recall_limit: int = 5
    weekly_reflection: bool = True
    tags: list[str] = Field(default_factory=list)
    creator: str = ""
    parent_strategy_id: str | None = None
