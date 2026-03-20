from pydantic import BaseModel, Field
from typing import Literal

class TradingDecision(BaseModel):
    """
    - PM Agent的最终裁决，包括交易动作和目标仓位百分比，以及人类可读的中文报告
    - action: 只能是 BUY / SELL / HOLD（全大写）
    - target_position_pct: 0~100 的数字，表示该股票在总资产中的"目标仓位比例"，比如50就是50%
    - 如果应当平仓，则 action="SELL", target_position_pct为减少后的目标持仓比例
    - 如果应当维持当前仓位，则通常应输出 action="HOLD"，并让 target_position_pct不变
    - 如果应该加仓, 则action="BUY", 让target_position为增加后的目标持仓比例
    """
    action: Literal["BUY", "SELL", "HOLD"] = Field(description="交易动作：BUY（买入/加仓）、SELL（卖出/减仓）、HOLD（持有/维持）")
    target_position_pct: float = Field(description="目标仓位百分比，范围 0~100，表示该股票在总资产中的目标仓位比例，比如50就是50%")
    report: str = Field(description="人类可读的中文报告")   