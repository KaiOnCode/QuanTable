"""System prompt builder — modeled after Claude Code's src/constants/prompts.ts.

Each function builds one section. build_system_prompt() assembles the full prompt.
Sections: Identity → Task Rules → Tool Rules → Output Rules → Tools → Skills
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry


# ── Section builders (pure functions, no side effects) ──────────

def _identity(today: str) -> str:
    return (
        f"You are an interactive agent that helps users with financial analysis. "
        f"Use the instructions below and the tools available to you to assist the user.\n"
        f"Today: {today}."
    )


def _task_rules() -> str:
    return (
        "## Task Rules\n"
        "1. Follow the user's instructions exactly. If they ask for a price, get the price — "
        "don't add analysis unless asked. Don't offer unsolicited services.\n"
        "2. Never guess numbers. Always verify with tools before answering. "
        "If a tool returns an error, explain what went wrong — don't silently fabricate data.\n"
        "3. Before reporting complete, verify you have the actual data you need. "
        "If you don't have data, say so explicitly rather than implying you do.\n"
        "4. Don't do work the user didn't ask for. "
        "A simple price query needs a price, not a full analysis report."
    )


def _tool_rules() -> str:
    return (
        "## Tool Rules (CRITICAL)\n"
        "1. Plan before calling. If you need multiple data points (price + news + fundamentals), "
        "call them ALL in ONE batch. Don't spread across multiple turns.\n"
        "2. Stop after getting data. Once your tools return results, ANALYZE THEM. "
        "Don't keep searching for more data 'just in case'.\n"
        "3. Never call the same tool with the same arguments twice. "
        "One successful call is enough. The system will block duplicate calls.\n"
        "4. If a tool fails with an error: try a different approach, or answer explaining "
        "what data is unavailable. Do NOT retry the exact same failing call.\n"
        "5. After 2-3 tool calls in total, you MUST answer. Even if some data is missing, "
        "provide what you have and note the gaps.\n"
        "6. Use the most specific tool: get_news for stock news, web_search for general queries, "
        "get_price for prices, get_fundamentals for financials."
    )


def _output_rules() -> str:
    return (
        "## Output Rules\n"
        "1. Be concise. Lead with the answer, skip preamble. "
        "If you can say it in one sentence, don't use three.\n"
        "2. Answer in the language the user used. Match their tone and level of detail.\n"
        "3. For data queries: give the number first, then brief context.\n"
        "4. For analysis: use clear section headers. Cite specific numbers from tool results.\n"
        "5. For comparisons: use tables or bullet points.\n"
        "6. Don't end with 'What would you like me to do?' or 'Is there anything else?' "
        "Just report the result.\n"
        "7. Don't list your capabilities unless explicitly asked."
    )


# ── Skills ─────────────────────────────────────────────────────

def select_relevant_skills(user_message: str, max_skills: int = 20) -> str:
    """Select top N skills relevant to user's query using keyword matching."""
    from skills.loader import get_loader

    loader = get_loader()
    loader.discover()

    if not loader.skills:
        return ""

    keywords = set(re.findall(r'[\u4e00-\u9fff]{2,}', user_message.lower()))
    keywords |= set(re.findall(r'[a-z]{3,}', user_message.lower()))

    scored = []
    for skill in loader.skills.values():
        text = f"{skill.name} {skill.description} {skill.category}".lower()
        score = sum(1 for kw in keywords if kw in text)
        scored.append((score, skill))

    scored.sort(key=lambda x: (-x[0], x[1].name))
    selected = scored[:max_skills]

    lines = []
    for score, skill in selected:
        marker = "**" if score > 0 else ""
        lines.append(
            f"- {marker}{skill.name}{marker} [{skill.category}]: "
            f"{skill.description[:120]}"
        )

    remaining = len(loader.skills) - len(selected)
    if remaining > 0:
        lines.append(
            f"\n(+{remaining} more skills. "
            f"Use list_skills to browse, search_skills(keyword) to find.)"
        )

    return "\n".join(lines)


def list_all_skills() -> str:
    """List all skills grouped by category in compact format."""
    from skills.loader import get_loader

    loader = get_loader()
    loader.discover()

    if not loader.skills:
        return ""

    cats: dict[str, list[str]] = {}
    for s in loader.skills.values():
        cats.setdefault(s.category, []).append(s.name)

    lines = []
    for cat in sorted(cats):
        names = sorted(cats[cat])
        lines.append(f"\n### {cat} ({len(names)})")
        for n in names:
            sk = loader.skills[n]
            tag = "" if sk.is_builtin else " [user]"
            lines.append(f"- {n}{tag}: {sk.description[:120]}")

    if len(loader.skills) > 50:
        lines.append(
            "\nTip: Use search_skills(query) to find skills, "
            "or list_skills to browse by category."
        )

    return "\n".join(lines)


# ── Static/dynamic separation ───────────────────────────────────

# Cached static sections — keyed by tool count (invalidated when tools change)
_static_cache: tuple[int, str] = (0, "")


def _build_static_sections(today: str, tool_text: str) -> str:
    """Build the prompt sections that don't change within a session.

    Static: identity, task_rules, tool_rules, output_rules, tool_text.
    Dynamic: skills section (depends on user_message).
    """
    return "\n\n".join([
        _identity(today),
        _task_rules(),
        _tool_rules(),
        _output_rules(),
        tool_text,
    ])


def _get_or_build_static(today: str, registry: ToolRegistry) -> str:
    """Return cached static sections, or rebuild if tools changed."""
    global _static_cache
    tool_count = registry.tool_count
    if _static_cache[0] != tool_count:
        _static_cache = (tool_count, _build_static_sections(today, registry.get_description_text()))
    return _static_cache[1]


def invalidate_prompt_cache():
    """Force rebuild of static sections on next call (e.g., after tool registration)."""
    global _static_cache
    _static_cache = (0, "")


# ── Main builder ────────────────────────────────────────────────

def build_system_prompt(
    registry: ToolRegistry,
    user_message: str = "",
) -> str:
    """Build the full system prompt with static/dynamic separation.

    Static sections are cached per tool count. Dynamic sections
    (skills) are recomputed each call based on user_message.
    """
    today = time.strftime("%Y-%m-%d")
    static = _get_or_build_static(today, registry)

    # Dynamic: skills — only for substantial queries
    skill_section = ""
    if user_message and len(user_message) > 20:
        skills = select_relevant_skills(user_message, max_skills=10)
        if skills:
            skill_section = (
                "\n## Relevant Skills\n"
                "Use load_skill(name) to read full methodology.\n"
                + skills
            )

    if skill_section:
        return static + "\n" + skill_section
    return static
