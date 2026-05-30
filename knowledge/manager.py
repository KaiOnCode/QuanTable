"""Structured knowledge base for strategy learning.

Inspired by QuantGPT (MIT License).
Maintains three files per strategy: rules.md, findings.md, failures.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

KnowledgeType = Literal["rule", "finding", "failure"]


class KnowledgeManager:
    """File-based knowledge base for a single strategy.

    Directory layout:
        data/{strategy_id}/knowledge/
        ├── rules.md       # Verified stable rules (must follow)
        ├── findings.md    # Empirical discoveries (reference)
        └── failures.md    # Falsified paths (avoid repeating)
    """

    def __init__(self, strategy_id: str, data_dir: str = "data"):
        self.strategy_id = strategy_id
        self.kb_dir = Path(data_dir) / strategy_id / "knowledge"
        self.kb_dir.mkdir(parents=True, exist_ok=True)

    # ── write API ──────────────────────────────────────────────

    def add_rule(
        self, title: str, content: str, confidence: float = 1.0, source: str = ""
    ) -> None:
        """Add a verified rule (must follow)."""
        entry = _format_entry("Rule", title, content, confidence, source)
        _append_to_file(self.kb_dir / "rules.md", entry)

    def add_finding(
        self, title: str, content: str, confidence: float = 0.5, source: str = ""
    ) -> None:
        """Add an empirical finding (reference)."""
        entry = _format_entry("Finding", title, content, confidence, source)
        _append_to_file(self.kb_dir / "findings.md", entry)

    def add_failure(self, title: str, content: str, source: str = "") -> None:
        """Record a falsified approach (avoid repeating)."""
        entry = _format_entry("Failure", title, content, 0.0, source)
        _append_to_file(self.kb_dir / "failures.md", entry)

    # ── read API ───────────────────────────────────────────────

    def get_context_for_agent(self, ticker: str | None = None) -> str:
        """Build the context string to inject into an agent's prompt.

        Always includes rules. Optionally filters findings by ticker.
        Truncates failures to 1000 chars to avoid bloat.
        """
        parts: list[str] = []

        rules = _read_file(self.kb_dir / "rules.md")
        if rules.strip():
            parts.append("## 已验证规则 (必须遵守)\n\n" + rules)

        findings = _read_file(self.kb_dir / "findings.md")
        if findings.strip():
            if ticker:
                relevant = _filter_by_ticker(findings, ticker)
                if relevant:
                    parts.append("## 相关历史发现\n\n" + relevant)
            else:
                parts.append("## 历史发现\n\n" + findings[:2000])

        failures = _read_file(self.kb_dir / "failures.md")
        if failures.strip():
            parts.append("## 已证伪路径 (避免重复)\n\n" + failures[:1000])

        return "\n\n---\n\n".join(parts)

    def get_rules(self) -> str:
        return _read_file(self.kb_dir / "rules.md")

    def get_findings(self) -> str:
        return _read_file(self.kb_dir / "findings.md")

    def get_failures(self) -> str:
        return _read_file(self.kb_dir / "failures.md")


# ── internal helpers ──────────────────────────────────────────

def _format_entry(
    kind: KnowledgeType,
    title: str,
    content: str,
    confidence: float,
    source: str,
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"## {kind.capitalize()}: {title}"
    meta = (
        f"- **Confidence**: {confidence:.1f}\n"
        f"- **Source**: {source or 'manual'}\n"
        f"- **Date**: {ts}"
    )
    return f"{header}\n\n{meta}\n\n{content}\n"


def _append_to_file(filepath: Path, entry: str) -> None:
    filepath.touch(exist_ok=True)
    existing = filepath.read_text(encoding="utf-8")
    if entry.strip() in existing:
        return  # dedup
    with filepath.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write("\n" + entry)


def _read_file(filepath: Path) -> str:
    if not filepath.exists():
        return ""
    return filepath.read_text(encoding="utf-8")


def _filter_by_ticker(text: str, ticker: str) -> str:
    """Return sections of the markdown text that mention the ticker."""
    sections = text.split("\n## ")
    relevant = [s for s in sections if ticker.upper() in s.upper()]
    if not relevant:
        return ""
    return "\n## ".join(relevant)
