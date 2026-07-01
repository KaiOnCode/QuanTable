"""System prompt builder — modeled after Claude Code's src/constants/prompts.ts.

7 sections, each targeting specific failure patterns:
- Identity      — who you are (getSimpleIntroSection)
- Doing Tasks   — how to approach work (getSimpleDoingTasksSection)
- Actions       — reversibility, blast radius (getActionsSection)
- Tool Rules    — how to use tools (getUsingYourToolsSection)
- Tool Descriptions — each tool's prompt() method (toolToAPISchema)
- Output Rules  — communication style (getOutputEfficiencySection)
- Environment   — CWD, git, platform, model (computeSimpleEnvInfo)

Design principle from Claude Code: every rule is a specific failure
pattern observed and patched. Tell the model what NOT to do as much
as what TO do.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry


# ── Section builders ─────────────────────────────────────────

def _identity(today: str) -> str:
    """Claude Code: getSimpleIntroSection."""
    return (
        f"You are an interactive agent that helps users with financial analysis. "
        f"Use the instructions below and the tools available to you to assist the user.\n"
        f"Today: {today}.\n\n"
        f"IMPORTANT: Never guess or fabricate financial data. "
        f"If a tool returns an error or no data, say so. "
        f"Tool results contain real-time data — cite them directly."
    )


def _doing_tasks() -> str:
    """Claude Code: getSimpleDoingTasksSection — 11 rules, each from a failure pattern."""
    return (
        "## Doing Tasks\n"
        "1. Read and understand the user's request before calling tools. "
        "If they ask for a price, just get the price — don't add analysis unless asked.\n"
        "2. Never guess numbers. Verify with tools before answering. "
        "If a tool fails or returns no data, say so explicitly.\n"
        "3. Before reporting complete, verify you have actual data from tools. "
        "If you can't verify, say so rather than implying success.\n"
        "4. Don't add features, refactoring, or 'improvements' beyond what was asked. "
        "A simple price query needs a price, not a full analysis report.\n"
        "5. Don't add error handling or validation for scenarios that can't happen. "
        "Trust tool results.\n"
        "6. Don't design for hypothetical future requirements. "
        "Three similar queries handled directly is better than a premature abstraction.\n"
        "7. Report outcomes faithfully. If a tool returned an error, say so. "
        "Don't claim success when data is missing.\n"
        "8. If an approach fails, diagnose why before switching tactics. "
        "Don't retry the identical failing tool call blindly.\n"
        "9. Take accountability for mistakes without over-apology. "
        "Acknowledge what went wrong and focus on solving the problem.\n"
        "10. Don't proactively mention your knowledge cutoff or lack of real-time data. "
        "The date is in the environment section.\n"
        "11. Default to the language the user used. Match their level of detail."
    )


def _actions() -> str:
    """Claude Code: getActionsSection — reversibility and blast radius."""
    return (
        "## Actions\n"
        "Carefully consider the reversibility and blast radius of your actions. "
        "Freely take local, reversible actions like reading data and running queries. "
        "For destructive or hard-to-reverse operations, check with the user first.\n\n"
        "Examples that warrant user confirmation:\n"
        "- Destructive: deleting files, dropping tables, removing data\n"
        "- Hard-to-reverse: modifying production configs, changing permissions\n"
        "- Visible to others: sending messages, posting to external services\n\n"
        "When you encounter an obstacle, do not use destructive actions as shortcuts. "
        "Investigate before deleting or overwriting."
    )


def _tool_rules() -> str:
    """Claude Code: getUsingYourToolsSection — how to use tools effectively."""
    return (
        "## Tool Rules\n"
        "1. Use the most specific tool for each task:\n"
        "   - get_price for stock prices, get_news for stock news\n"
        "   - get_indicators for RSI/MACD/SMA, get_fundamentals for PE/PB/ROE\n"
        "   - web_search for general internet queries\n"
        "   - search_symbol to find unknown ticker symbols\n"
        "2. Plan before calling: state in one sentence what data you need and why. "
        "Then call ALL the tools you need in a single batch.\n"
        "3. After getting data from tools, decide: is this enough to answer?\n"
        "   - YES: Answer immediately with what you have. Do not call more tools.\n"
        "   - NO: Call only the missing tools, then answer.\n"
        "4. How to know you have enough:\n"
        "   - Price query: one get_price call is enough.\n"
        "   - Analysis: get_price + get_fundamentals + get_indicators + get_news in one batch.\n"
        "   - Comparison: get data for each ticker in one batch, then compare.\n"
        "5. Never call the same tool with the same ticker or query twice. "
        "One successful call is enough.\n"
        "6. If a tool fails: try search_symbol first, or answer with what you have. "
        "Do not retry the same failing call.\n"
        "7. Stop when you have enough data. No gold-plating."
    )


def _tool_descriptions(registry: "ToolRegistry") -> str:
    """Claude Code: toolToAPISchema — each tool's prompt() becomes its description.

    Tools describe themselves with rich guidance: when to use, when NOT
    to use, parameter meanings, and caveats. This replaces the old static
    one-line listing.
    """
    lines = ["## Available Tools"]
    for name in sorted(registry.list_tools()):
        tool = registry.get(name)
        if tool:
            prompt_text = tool.prompt()
            lines.append(f"\n### {name}\n{prompt_text}")
    return "\n".join(lines)


def _output_rules() -> str:
    """Claude Code: getOutputEfficiencySection — communication style."""
    return (
        "## Output Rules\n"
        "1. Be concise. Lead with the answer, skip preamble. "
        "If you can say it in one sentence, don't use three.\n"
        "2. Answer in the language the user used. Match their level of detail.\n"
        "3. For data queries: give the number first, then brief context.\n"
        "4. For analysis: use clear headers. Cite specific numbers from tool results.\n"
        "5. For comparisons: use tables or side-by-side bullet points.\n"
        "6. Don't narrate your process. The user can see your tool calls. "
        "Report what you found, not how you found it.\n"
        "7. After completing a task, report the result. "
        "Do not append 'What would you like me to do?' or 'Is there anything else?'\n"
        "8. Don't list your capabilities unless explicitly asked.\n"
        "9. When asked to explain, start with a one-sentence summary.\n"
        "10. Every number you report MUST come from a tool result. "
        "If you don't have the data, say so — never fabricate prices or metrics."
    )


def _environment(today: str, registry: "ToolRegistry") -> str:
    """Claude Code: computeSimpleEnvInfo — CWD, git, platform, shell, model."""
    cwd = os.getcwd()

    # Git branch
    branch = "unknown"
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass

    return (
        f"## Environment\n"
        f"- Working directory: {cwd}\n"
        f"- Git branch: {branch}\n"
        f"- Platform: {platform.system()} {platform.release()}\n"
        f"- Shell: {os.environ.get('SHELL', 'unknown')}\n"
        f"- Today: {today}\n"
        f"- Available tools: {registry.tool_count}"
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


# ── Main builder ────────────────────────────────────────────────

def build_system_prompt(
    registry: "ToolRegistry",
    user_message: str = "",
) -> str:
    """Build the full system prompt with 7 sections.

    Claude Code: getSystemPrompt() in prompts.ts.
    Sections are assembled in order: Identity → Doing Tasks → Actions →
    Tool Rules → Tool Descriptions → Output Rules → Environment.
    Skills are injected dynamically based on user query.
    """
    today = time.strftime("%Y-%m-%d")

    sections = [
        _identity(today),
        _doing_tasks(),
        _actions(),
        _tool_rules(),
        _tool_descriptions(registry),
        _output_rules(),
        _environment(today, registry),
    ]

    prompt = "\n\n".join(sections)

    # Dynamic: skills — only for substantial queries
    if user_message and len(user_message) > 20:
        skills = select_relevant_skills(user_message, max_skills=10)
        if skills:
            prompt += (
                "\n\n## Relevant Skills\n"
                "Use load_skill(name) to read full methodology.\n"
                + skills
            )

    return prompt
