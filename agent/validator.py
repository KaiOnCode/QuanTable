"""Output validator — checks agent responses against tool results.

Detects fabricated data by cross-referencing numbers in the answer
with data from tool results. Adds warnings when data can't be verified.

Inspired by Claude Code's output validation patterns.
"""

from __future__ import annotations

import json
import re


def extract_numbers(text: str) -> list[float]:
    """Extract all dollar amounts and percentages from text."""
    numbers = []
    # $123.45, 123.45, -12.3%
    for m in re.finditer(r"\$?\s*([\d,]+\.?\d*)\s*%?", text):
        try:
            n = float(m.group(1).replace(",", ""))
            if n > 0.01 and n < 1_000_000:  # filter obvious non-prices
                numbers.append(n)
        except ValueError:
            pass
    return numbers


def extract_tool_numbers(messages: list[dict]) -> dict[str, set[float]]:
    """Extract all numbers from tool results, keyed by ticker."""
    data = {}
    for m in messages:
        if m.get("role") != "tool":
            continue
        content = m.get("content", "")
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        ticker = parsed.get("ticker", "?")
        if ticker not in data:
            data[ticker] = set()

        # Extract numbers from tool result
        def _walk(obj):
            if isinstance(obj, (int, float)):
                if 0.01 < obj < 1_000_000:
                    data[ticker].add(round(float(obj), 2))
            elif isinstance(obj, dict):
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for v in obj[-10:]:  # only recent data
                    _walk(v)

        _walk(parsed)

    return data


def validate_answer(answer: str, messages: list[dict]) -> str | None:
    """Check if numbers in the answer appear in tool results.
    Returns a warning message if data seems fabricated, None if OK.
    """
    tool_data = extract_tool_numbers(messages)
    if not tool_data:
        return None  # no tool results to validate against

    answer_numbers = set(round(n, 2) for n in extract_numbers(answer))
    if not answer_numbers:
        return None

    # Check if any answer number exists in ANY tool result
    all_tool_numbers = set()
    for nums in tool_data.values():
        all_tool_numbers.update(nums)

    unmatched = answer_numbers - all_tool_numbers
    if len(unmatched) >= 3 and len(answer_numbers) >= 5:
        # Multiple numbers don't match any tool result — possible fabrication
        return (
            f"\n\n[Warning: Some numbers in this response "
            f"({len(unmatched)} values) could not be verified against tool results. "
            f"Verify data before relying on it.]"
        )

    return None
