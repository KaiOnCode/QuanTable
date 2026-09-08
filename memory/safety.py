"""Pre-trade safety gate.

Inspired by TradeMemory Protocol (MIT License).
Checks drawdown, losing streaks, concentration, and memory history
before allowing a trade to execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from memory.store import MemoryStore


@dataclass
class SafetyResult:
    passed: bool = True
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def pre_trade_check(
    *,
    strategy_id: str,
    ticker: str,
    proposed_size_pct: float,
    current_drawdown_pct: float,
    max_drawdown_pct: float,
    max_position_pct: float,
    current_position_pct: float,
    memory_store: MemoryStore,
) -> SafetyResult:
    """Run the 5-factor pre-trade safety gate.

    Returns a SafetyResult with passed=False if any blocking condition fires.
    """
    blocking: list[str] = []
    warnings: list[str] = []

    # 1. Drawdown check
    if current_drawdown_pct >= max_drawdown_pct:
        blocking.append(
            f"Max drawdown exceeded: {current_drawdown_pct:.1f}% >= {max_drawdown_pct:.1f}%"
        )

    # 2. Concentration check
    new_weight = current_position_pct + proposed_size_pct
    if new_weight > max_position_pct:
        blocking.append(
            f"Position {new_weight:.0f}% exceeds max {max_position_pct:.0f}% for {ticker}"
        )

    # 3. Losing streak check
    recent = memory_store.recall(strategy_id=strategy_id, limit=10)
    if len(recent) >= 5:
        last_5_pnls = []
        for m in recent[:5]:
            pnl = m.trade_record.get("pnl_pct", 0)
            last_5_pnls.append(pnl)
        if all(p < 0 for p in last_5_pnls):
            blocking.append("5 consecutive losses — strategy may be broken")

    # 4. Recent similar-ticker losses
    ticker_memories = memory_store.recall(
        ticker=ticker, strategy_id=strategy_id, limit=5
    )
    recent_losses = [m for m in ticker_memories if m.outcome_quality < 0]
    if len(recent_losses) >= 3:
        warnings.append(
            f"3+ recent losses for {ticker} in similar conditions — consider reducing size"
        )

    # 5. Size anomaly check
    if proposed_size_pct > 30:
        avg_size = _avg_position_size(recent)
        if avg_size > 0 and proposed_size_pct > avg_size * 3:
            warnings.append(
                f"Proposed size {proposed_size_pct:.0f}% is 3x the historical average "
                f"({avg_size:.0f}%) — verify conviction"
            )

    return SafetyResult(
        passed=len(blocking) == 0,
        blocking_reasons=blocking,
        warnings=warnings,
    )


def _avg_position_size(memories: list) -> float:
    sizes = [
        abs(m.trade_record.get("position_delta_pct", 0))
        for m in memories
        if m.trade_record.get("position_delta_pct")
    ]
    return sum(sizes) / len(sizes) if sizes else 0.0
