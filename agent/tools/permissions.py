"""Permission framework for tool execution.

Inspired by Claude Code's 16-step permission pipeline (Tool.ts).
For now: allow/deny rules + mode check + hook placeholders.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable

from .base import BaseTool


class PermissionDecision(Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionMode(Enum):
    """Agent operation modes."""
    DEFAULT = "default"       # Normal operation — ask for write tools
    PLAN = "plan"             # Read-only — deny all write tools
    ACCEPT_EDITS = "accept"   # Auto-allow file edits
    BYPASS = "bypass"         # Allow everything (use carefully)


# Hook types — placeholder for future hook system
HookCallback = Callable[[BaseTool, dict, PermissionDecision], PermissionDecision | None]


class PermissionManager:
    """Manages tool permissions with rules + mode checks.

    Rule priority (low to high): deny_rules → allow_rules → mode → hooks
    """

    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT):
        self.mode = mode
        self._deny_rules: list[Callable[[str, dict], bool]] = []
        self._allow_rules: list[Callable[[str, dict], bool]] = []
        self._hooks: list[HookCallback] = []

    def add_deny_rule(self, rule: Callable[[str, dict], bool]):
        """Add a deny rule. If it returns True, the tool is denied."""
        self._deny_rules.append(rule)

    def add_allow_rule(self, rule: Callable[[str, dict], bool]):
        """Add an allow rule. If it returns True, bypass other checks."""
        self._allow_rules.append(rule)

    def add_hook(self, hook: HookCallback):
        """Add a permission hook. Called with (tool, params, decision)."""
        self._hooks.append(hook)

    def check(self, tool: BaseTool, params: dict) -> PermissionDecision:
        """Check if a tool can be executed. Returns the permission decision.

        Pipeline: deny_rules → allow_rules → mode_check → tool_specific → hooks
        """
        name = tool.meta.name

        # 1. Deny rules (highest priority after allow)
        for rule in self._deny_rules:
            if rule(name, params):
                return PermissionDecision.DENY

        # 2. Allow rules (override everything)
        for rule in self._allow_rules:
            if rule(name, params):
                return PermissionDecision.ALLOW

        # 3. Mode check
        decision = self._check_mode(tool)
        if decision:
            return decision

        # 4. Tool-specific checks
        decision = self._check_tool(tool, params)
        if decision:
            return decision

        # 5. Hooks
        for hook in self._hooks:
            result = hook(tool, params, PermissionDecision.ALLOW)
            if result:
                return result

        # Default: allow read-only, ask for write
        if tool.meta.is_readonly:
            return PermissionDecision.ALLOW
        return PermissionDecision.ASK

    def _check_mode(self, tool: BaseTool) -> PermissionDecision | None:
        """Mode-based permission check."""
        if self.mode == PermissionMode.PLAN:
            if not tool.meta.is_readonly:
                return PermissionDecision.DENY
            return PermissionDecision.ALLOW

        if self.mode == PermissionMode.BYPASS:
            return PermissionDecision.ALLOW

        if self.mode == PermissionMode.ACCEPT_EDITS:
            if tool.meta.name in ("write_file", "save_skill"):
                return PermissionDecision.ALLOW

        return None  # mode has no opinion

    def _check_tool(self, tool: BaseTool, params: dict) -> PermissionDecision | None:
        """Tool-specific safety checks."""
        # Destructive tools always ask
        if tool.meta.is_destructive:
            return PermissionDecision.ASK

        # Write tools outside workspace → ask
        if not tool.meta.is_readonly and tool.meta.name in ("write_file",):
            return PermissionDecision.ASK

        return None


# ── Pre-built rule factories ────────────────────────────────────

def deny_tool_names(*names: str) -> Callable[[str, dict], bool]:
    """Deny specific tools by name."""
    denied = set(names)
    return lambda name, params: name in denied


def allow_tool_names(*names: str) -> Callable[[str, dict], bool]:
    """Allow specific tools by name."""
    allowed = set(names)
    return lambda name, params: name in allowed
