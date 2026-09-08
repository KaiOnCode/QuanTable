# dataflow/portfolio_manager.py
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from broker.gateway import BrokerGateway


class PortfolioManager:
    """
    Manages current position state and risk limits.
    This is a stateful class called by DataService.

    It manages two modes:
    1. Advisory mode (default): does not provide position sizing suggestions.
    2. Sizing mode: activated when the user provides specific risk parameters.
    """

    def __init__(self):
        # 1. Maintain position state
        self._positions: Dict[str, Dict[str, Any]] = {}

        # 2. Maintain risk limits
        #    Default: neutral defaults / advisory mode
        self._risk_limits = self.get_advisory_defaults()

    def get_advisory_defaults(self) -> Dict[str, Any]:
        """
        Return "neutral default" configuration for advisory mode.
        """
        return {
            "max_pos_pct": 1.0,  # placeholder
            "max_drawdown_pct": 1.0,  # placeholder
            "meta": {"ignore_in_analysis": True, "advisory": True},
        }

    def get_position(self, ticker: str) -> Dict[str, Any]:
        """
        Get position for a given ticker.
        - If not found, return spec-required "neutral default".
        - If found, return real position with meta (ignore=false).
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        position_data = self._positions.get(ticker)

        if not position_data:
            # Return neutral default
            return {
                "side": "flat",
                "qty_pct": 0.0,
                "avg_cost": None,
                "meta": {
                    "ignore_in_analysis": True,
                    "asof": now_iso,
                },
            }

        # Return real position
        real_position = position_data.copy()
        real_position["meta"] = {
            "ignore_in_analysis": False,
            "asof": now_iso,
        }
        return real_position

    def get_risk_limits(self) -> Dict[str, Any]:
        """
        Get risk limits.
        Returns neutral defaults (advisory) or user-specified limits (sizing).
        """
        return self._risk_limits

    # --- Mode switching ---

    def update_position(self, ticker: str, side: str, qty_pct: float, avg_cost: float):
        """
        Update position externally (e.g. from backtest module or user input).
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
        Sync current state from broker's account/positions API.
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
        Update risk limits externally.
        Calling this method switches the system to Sizing Mode.
        """
        self._risk_limits = {
            "max_pos_pct": max_pos_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "meta": {
                "ignore_in_analysis": False,
                "advisory": False,
            },
        }
        print(
            f"[PortfolioManager] Risk limits updated (Sizing Mode): {self._risk_limits}"
        )

    def reset_to_advisory_mode(self):
        """
        Reset session back to Advisory Mode.
        """
        self._risk_limits = self.get_advisory_defaults()
        print("[PortfolioManager] Reset to Advisory Mode.")
