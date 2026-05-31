"""HITL Rule Engine.

评估 PM 决策是否需要人工审批.
"""

from __future__ import annotations

from hitl.models import HITLRuleConfig, PMDecision


class HITLRuleEngine:
    """根据配置规则评估 PM 决策是否需要人工审批.

    使用示例:
        >>> config = HITLRuleConfig(position_change_threshold_pct=20)
        >>> engine = HITLRuleEngine(config)
        >>> decision = PMDecision(action="BUY", target_position_pct=60, confidence=0.8)
        >>> needs_approval, rules = engine.evaluate(decision, current_position_pct=0)
        >>> print(needs_approval, rules)
        True ['position_change']
    """

    def __init__(self, config: HITLRuleConfig | None = None):
        self.config = config or HITLRuleConfig()

    def evaluate(
        self,
        decision: PMDecision,
        current_position_pct: float = 0.0,
    ) -> tuple[bool, list[str]]:
        """评估决策是否需要审批.

        Args:
            decision: PM 的决策输出
            current_position_pct: 当前该票的持仓百分比 (0-100)

        Returns:
            (needs_approval, triggered_rule_names)
            - needs_approval: True 表示至少一条规则被触发
            - triggered_rule_names: 被触发的规则名称列表
        """
        if not self.config.enabled:
            return False, []

        # HOLD 且无目标仓位 → 无需审批
        if decision.is_noop:
            return False, []

        triggered: list[str] = []

        if self._check_position_change(decision, current_position_pct):
            triggered.append("position_change")

        if self._check_confidence(decision):
            triggered.append("low_confidence")

        if self._check_concentration(decision):
            triggered.append("high_concentration")

        return len(triggered) > 0, triggered

    def _check_position_change(self, decision: PMDecision, current_pct: float) -> bool:
        """仓位变化是否超过阈值.

        例: 当前 10%, 目标 60% → 变化 50% > 阈值 20% → 触发
        """
        change = abs(decision.target_position_pct - current_pct)
        # 忽略微小变化（浮点精度）
        return change > self.config.position_change_threshold_pct + 1e-6

    def _check_confidence(self, decision: PMDecision) -> bool:
        """置信度是否低于阈值."""
        return decision.confidence < self.config.min_confidence_threshold - 1e-6

    def _check_concentration(self, decision: PMDecision) -> bool:
        """单票目标仓位是否过高."""
        return decision.target_position_pct > self.config.max_single_ticker_pct + 1e-6
