# dataflow/portfolio_manager.py
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from broker.gateway import BrokerGateway


class PortfolioManager:
    """
    负责维护当前的持仓状态和风险限额。
    这是一个有状态的类，供 DataService 调用。

    它管理两种模式:
    1. 咨询模式 (Advisory): 默认状态，不提供仓位建议。
    2. 仓位模式 (Sizing): 当用户提供了具体的风险参数时。
    """

    def __init__(self):
        # 1. 维护持仓状态
        self._positions: Dict[str, Dict[str, Any]] = {}

        # 2. 维护风险限额
        #    默认使用“中性默认/咨询模式”的配置
        self._risk_limits = self.get_advisory_defaults()

    def get_advisory_defaults(self) -> Dict[str, Any]:
        """
        返回“中性默认”配置，用于咨询模式
        """
        return {
            "max_pos_pct": 1.0,  # 占位
            "max_drawdown_pct": 1.0,  # 占位
            "meta": {"ignore_in_analysis": True, "advisory": True},
        }

    def get_position(self, ticker: str) -> Dict[str, Any]:
        """
        获取指定 ticker 的持仓。
        - 如果未找到，返回规范要求的“中性默认”。
        - 如果找到，返回真实持仓并附上 meta (ignore=false)。
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        position_data = self._positions.get(ticker)

        if not position_data:
            # 返回“中性默认” (Neutral Default)
            return {
                "side": "flat",
                "qty_pct": 0.0,
                "avg_cost": None,
                "meta": {
                    "ignore_in_analysis": True,  # 忽略对分析的影响
                    "asof": now_iso,
                },
            }

        # 否则，返回真实持仓
        real_position = position_data.copy()
        real_position["meta"] = {
            "ignore_in_analysis": False,  # 这是一个真实持仓，必须分析
            "asof": now_iso,
        }
        return real_position

    def get_risk_limits(self) -> Dict[str, Any]:
        """
        获取风险限额。
        (它会根据当前模式返回“中性默认”或“客户指定”的限额)
        """
        return self._risk_limits

    # --- 模式切换方法 ---

    def update_position(self, ticker: str, side: str, qty_pct: float, avg_cost: float):
        """
        供外部（如回测模块或用户输入）更新持仓。
        """
        if qty_pct == 0 or side == "flat":
            if ticker in self._positions:
                del self._positions[ticker]
        else:
            self._positions[ticker] = {
                "side": side,
                "qty_pct": qty_pct,
                "avg_cost": avg_cost,
            }
        print(
            f"[PortfolioManager] Position updated for {ticker}: {self._positions.get(ticker)}"
        )

    def sync_from_broker(self, broker: "BrokerGateway"):
        """
        从 broker 的公共账户/持仓接口刷新当前状态。
        """
        account = broker.get_account()
        next_positions: Dict[str, Dict[str, Any]] = {}

        for position in broker.get_positions():
            position_value = (
                position.shares * position.avg_cost + position.unrealized_pnl
            )
            qty_pct = position_value / account.equity if account.equity != 0 else 0.0
            next_positions[position.ticker] = {
                "side": position.side.lower(),
                "qty_pct": qty_pct,
                "avg_cost": position.avg_cost,
            }

        self._positions = next_positions

    def update_risk_limits(self, max_pos_pct: float, max_drawdown_pct: float):
        """
        供外部更新风险限额。
        调用此方法会使系统进入“仓位模式 (Sizing Mode)”。
        (对应您说的“问客户最大能接受的亏损”)
        """
        self._risk_limits = {
            "max_pos_pct": max_pos_pct,
            "max_drawdown_pct": max_drawdown_pct,  # 这就是客户能接受的最大亏损
            "meta": {
                "ignore_in_analysis": False,  # 必须分析
                "advisory": False,  # 必须进行 sizing
            },
        }
        print(
            f"[PortfolioManager] Risk limits updated (Sizing Mode): {self._risk_limits}"
        )

    def reset_to_advisory_mode(self):
        """
        将会话重置回“咨询模式”。
        """
        self._risk_limits = self.get_advisory_defaults()
        print("[PortfolioManager] Reset to Advisory Mode.")
