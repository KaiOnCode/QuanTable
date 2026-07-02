from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class BrokerConfig(BaseSettings):
    initial_cash: float = 100_000.0
    # Rates use decimal fractions: 0.001 = 0.1% = 10 bps.
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    # close_bar fills market orders from the current close reference; next_open
    # queues market orders until the next bar's open. Both modes are deterministic.
    execution_timing: Literal["close_bar", "next_open"] = "close_bar"
    max_position_pct: float = 1.0
    # Reserved for portfolio-level caps once multi-ticker execution is added.
    max_total_position_pct: float = 1.0
    allow_short: bool = True
