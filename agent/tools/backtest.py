from __future__ import annotations

from math import floor
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from broker.models import Order, OrderSide, OrderType

from agent.run_context import current_agent_run_context

from .base import BaseTool, ToolMeta


class BacktestDecisionInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=4000)


class SubmitBacktestDecisionTool(BaseTool):
    meta = ToolMeta(
        name="submit_backtest_decision",
        description="Submit exactly one validated backtest decision through the scoped broker.",
        is_readonly=False,
        repeatable=False,
        category="financial",
        input_schema={
            "properties": {
                "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                "target_position_pct": {"type": "number", "minimum": 0, "maximum": 100},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "rationale": {"type": "string"},
            },
            "required": ["action", "target_position_pct", "confidence", "rationale"],
        },
    )

    def execute(
        self,
        action: str = "",
        target_position_pct: float = 0.0,
        confidence: float = 0.0,
        rationale: str = "",
        **unused: str | float,
    ) -> str:
        del unused
        context = current_agent_run_context()
        if context is None:
            return self._error(
                "backtest decision tool is unavailable outside a scoped run"
            )
        try:
            decision = BacktestDecisionInput.model_validate(
                {
                    "action": action,
                    "target_position_pct": target_position_pct,
                    "confidence": confidence,
                    "rationale": rationale,
                }
            )
        except ValidationError as error:
            return self._error(f"invalid backtest decision: {error.errors()[0]['msg']}")
        if decision.action == "HOLD":
            return self._ok(
                {
                    "action": decision.action,
                    "target_position_pct": decision.target_position_pct,
                    "confidence": decision.confidence,
                    "rationale": decision.rationale,
                    "execution": "held",
                }
            )
        latest_price = context.broker.get_latest_price(context.ticker)
        if latest_price is None or latest_price <= 0:
            return self._error("scoped broker has no current market price")
        account = context.broker.get_account(account_id=context.account_id)
        position = context.broker.get_position(
            context.ticker, account_id=context.account_id
        )
        current_shares = position.shares if position is not None else 0.0
        direction = 1.0 if decision.action == "BUY" else -1.0
        target_shares = float(
            floor(
                account.equity
                * (decision.target_position_pct / 100.0)
                * direction
                / latest_price
            )
        )
        delta_shares = target_shares - current_shares
        if delta_shares == 0:
            return self._ok(
                {
                    "action": decision.action,
                    "target_position_pct": decision.target_position_pct,
                    "confidence": decision.confidence,
                    "rationale": decision.rationale,
                    "execution": "held",
                }
            )
        order = context.broker.place_order(
            Order(
                ticker=context.ticker,
                side=OrderSide.BUY if delta_shares > 0 else OrderSide.SELL,
                type=OrderType.MARKET,
                qty=abs(delta_shares),
                strategy_id=context.strategy_id,
                account_id=context.account_id,
                session_id=context.session_id,
                decision_id=uuid4().hex,
            )
        )
        return self._ok(
            {
                "action": decision.action,
                "target_position_pct": decision.target_position_pct,
                "confidence": decision.confidence,
                "rationale": decision.rationale,
                "execution": order.status.value.lower(),
                "order_id": order.id,
            }
        )
