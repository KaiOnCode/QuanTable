"""Task tracker — tells the agent what step it's on.

Claude Code pattern: TodoWrite / TaskCreate gives the agent
situational awareness. This is a lightweight version that tracks:
- What's been done (tools called, tickers covered)
- What remains
- Whether the analysis is complete
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCallRecord:
    tool: str
    ticker: str = ""
    status: str = "ok"  # ok / error
    when: str = ""  # iteration when called


@dataclass
class TaskTracker:
    """Tracks analysis progress across iterations."""

    tickers_seen: set[str] = field(default_factory=set)
    tools_called: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    errors: list[str] = field(default_factory=list)

    def record(self, tool_name: str, ticker: str = "", status: str = "ok"):
        self.tools_called.append(
            ToolCallRecord(
                tool=tool_name, ticker=ticker, status=status, when=str(self.iterations)
            )
        )
        if ticker:
            self.tickers_seen.add(ticker)
        if status == "error":
            self.errors.append(f"{tool_name}({ticker})")

    def next_iteration(self):
        self.iterations += 1

    def summary(self) -> str:
        """One-line summary for system prompt injection."""
        if not self.tools_called:
            return ""

        ticker_str = (
            ", ".join(sorted(self.tickers_seen)) if self.tickers_seen else "none"
        )
        tool_names = set(tc.tool for tc in self.tools_called)
        error_count = len(self.errors)

        parts = [f"Data collected for: {ticker_str}"]
        parts.append(f"Tools used: {', '.join(sorted(tool_names))}")
        if error_count > 0:
            parts.append(f"Errors: {error_count}")

        return " | ".join(parts)
