"""HITL Rule Engine.

Evaluates whether a PM decision requires human approval.
"""

from __future__ import annotations

from hitl.models import HITLRuleConfig, PMDecision


class HITLRuleEngine:
    """Evaluates PM decisions against configured rules to determine if human approval is needed.

    Example:
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
        """Evaluate whether a decision needs approval.

        Args:
            decision: PM output decision
            current_position_pct: Current position percentage for this ticker (0-100)

        Returns:
            (needs_approval, triggered_rule_names)
            - needs_approval: True if at least one rule was triggered
            - triggered_rule_names: List of triggered rule names
        """
        if not self.config.enabled:
            return False, []

        # HOLD with zero target position -- no approval needed
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
        """Check if position change exceeds threshold.

        Example: current 10%, target 60% -> change 50% > threshold 20% -> triggered
        """
        change = abs(decision.target_position_pct - current_pct)
        # Ignore negligible changes (floating point precision)
        return change > self.config.position_change_threshold_pct + 1e-6

    def _check_confidence(self, decision: PMDecision) -> bool:
        """Check if confidence is below threshold."""
        return decision.confidence < self.config.min_confidence_threshold - 1e-6

    def _check_concentration(self, decision: PMDecision) -> bool:
        """Check if single-ticker target position is too high."""
        return decision.target_position_pct > self.config.max_single_ticker_pct + 1e-6
