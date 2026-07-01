"""System prompt builder — modeled after Claude Code's src/constants/prompts.ts.

Every section here is adapted from Claude Code's prompt architecture:
- Identity → System section
- Task Rules → Doing tasks section
- Tool Rules → combined with Using your tools section
- Output Rules → Communication style + Be concise sections
- Tools → tool descriptions (auto-generated)
- Skills → dynamic injection

Key design principle from Claude Code: tell the model what NOT to do
as much as what TO do. Every constraint is a specific failure pattern
observed and patched.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry


# ── Section builders (each adapted from Claude Code) ────────────

def _identity(today: str) -> str:
    """System section — who you are, what you do. Claude Code: getSimpleIntroSection."""
    return (
        f"You are an interactive agent that helps users with financial analysis. "
        f"Use the instructions below and the tools available to you to assist the user.\n"
        f"Today: {today}.\n\n"
        f"IMPORTANT: Never guess or fabricate financial data. "
        f"If a tool returns an error or no data, say so. "
        f"Tool results may contain real-time data — cite them directly."
    )


def _task_rules() -> str:
    """Doing tasks section — how to approach work. Claude Code: getSimpleDoingTasksSection.

    Every rule here counteracts a specific failure observed in testing:
    - "just the price, not analysis" → over-analysis of simple queries
    - "don't do work not asked for" → 200-word Chinese replies to "Reply: OK"
    - "if you can't verify, say so" → hallucinated data
    - "no gold-plating" → endless tool calling
    """
    return (
        "## Task Rules\n"
        "1. Follow the user's instructions exactly. "
        "If they ask for a price, just get the price — don't add analysis unless asked. "
        "Don't do work the user didn't ask for.\n"
        "2. Never guess numbers. Always verify with tools before answering. "
        "If a tool fails or returns no data, say so explicitly — don't fabricate.\n"
        "3. Before reporting complete, verify you have actual data from tools. "
        "If you can't verify, say so rather than implying success.\n"
        "4. No gold-plating. A simple price query needs a price, not a full analysis report. "
        "Minimum complexity means don't skip the finish line, not add decoration."
    )


def _tool_rules() -> str:
    """Tool rules — adapted from Claude Code's approach.

    Claude Code doesn't cap tool count. It tells the model HOW to use tools:
    - plan before calling (one sentence)
    - call all needed tools in one batch
    - stop when you have enough data
    - don't retry failing calls
    """
    return (
        "## Tool Rules\n"
        "1. Before calling tools, state in one sentence what data you need and why. "
        "Then call all the tools you need in a single batch.\n"
        "2. After you get data from tools, decide: is this enough to answer the user's question?\n"
        "   - YES: Answer immediately with what you have. Do not call more tools.\n"
        "   - NO: Call only the missing tools, then answer.\n"
        "3. How to know you have enough:\n"
        "   - Price query → one get_price call is enough. Answer.\n"
        "   - Analysis of a stock → get_price + get_fundamentals + get_indicators + get_news. "
        "Call them all in one batch, then answer.\n"
        "   - Comparison → get data for each ticker in one batch, then compare.\n"
        "4. Never call the same tool with the same ticker or query twice. "
        "One successful call is enough. The system blocks duplicates.\n"
        "5. If a tool fails: try searching for the ticker first (search_symbol), "
        "or answer with what you have. Do not retry the same failing call.\n"
        "6. Use the most specific tool: get_price for prices, get_news for stock news, "
        "web_search for general internet queries, search_symbol to find unknown tickers."
    )


def _output_rules() -> str:
    """Output rules — adapted from Claude Code's Communication style + Be concise.

    Every rule is a direct adaptation:
    - "lead with the answer" → Be concise
    - "if one sentence, don't use three" → Be concise
    - "don't append 'anything else?'" → Communication style (last paragraph)
    - "use language user used" → implicit
    - "report result, not process" → Communication style
    """
    return (
        "## Output Rules\n"
        "1. Be concise. Lead with the answer, skip preamble. "
        "If you can say it in one sentence, don't use three.\n"
        "2. Answer in the language the user used. Match their level of detail.\n"
        "3. After completing a task, report the result. "
        "Do not append 'What would you like me to do?' or 'Is there anything else?'\n"
        "4. For data queries: give the number first, then brief context.\n"
        "5. For analysis: use clear headers. Cite specific numbers from tool results.\n"
        "6. For comparisons: use tables or side-by-side bullet points.\n"
        "7. Don't narrate your process. The user can see your tool calls. "
        "Report what you found, not how you found it.\n"
        "8. Don't list your capabilities unless explicitly asked.\n"
        "9. When asked to explain, start with a one-sentence summary. "
        "If the user wants more depth, they'll ask.\n"
        "10. Every number you report MUST come from a tool result. "
        "If you don't have the data, say so — never fabricate prices or metrics. "
        "Report outcomes faithfully."
    )


# ── Skills ─────────────────────────────────────────────────────

def select_relevant_skills(user_message: str, max_skills: int = 10) -> str:
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


# ── Static/dynamic separation ───────────────────────────────────

_static_cache: tuple[int, str] = (0, "")


def _build_static_sections(today: str, tool_text: str) -> str:
    """Static sections that don't change within a session."""
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
        _static_cache = (
            tool_count,
            _build_static_sections(today, registry.get_description_text()),
        )
    return _static_cache[1]


def invalidate_prompt_cache():
    """Force rebuild of static sections on next call."""
    global _static_cache
    _static_cache = (0, "")


# ── Main builder ────────────────────────────────────────────────

def build_system_prompt(
    registry: ToolRegistry,
    user_message: str = "",
) -> str:
    """Build the full system prompt with static/dynamic separation."""
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

    return static + ("\n" + skill_section if skill_section else "")
