from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class BrokerConfig(BaseSettings):
    initial_cash: float = 100_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    execution_timing: Literal["close_bar", "next_open"] = "close_bar"
    max_position_pct: float = 1.0
    max_total_position_pct: float = 1.0
    allow_short: bool = True
