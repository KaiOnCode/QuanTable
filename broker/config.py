from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class BrokerConfig(BaseSettings):
    initial_cash: float = 100_000.0
    # Rates use decimal fractions: 0.001 = 0.1% = 10 bps.
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    # Phase 1 only defines the switch. Fill-timing behavior lands in Phase 2.
    execution_timing: Literal["close_bar", "next_open"] = "close_bar"
    max_position_pct: float = 1.0
    # Reserved for portfolio-level caps once multi-ticker execution is added.
    max_total_position_pct: float = 1.0
    allow_short: bool = True
