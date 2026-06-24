"""Context compression — prevents token overflow in long agent conversations.

L1: Micro-compact (zero-cost, every iteration) — keep last 3 tool_results,
    mark older ones as [cleared].
L2: Collapse large texts (zero-cost) — truncate >2000-char messages to
    head 900 + tail 500.
L3: LLM summary (1 LLM call when over threshold) — summarize head, protect
    tail (recent 20K tokens).

Design borrowed from Vibe-Trading's five-layer compression system.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds
TOKEN_THRESHOLD = 40_000       # Trigger L3 compression
TOKEN_WARN = 28_000            # Trigger L2 collapse
TAIL_TOKEN_BUDGET = 20_000     # Keep recent ~20K tokens uncompressed in L3
MAX_TEXT_LEN = 2_000           # L2: collapse text longer than this
HEAD_CHARS = 900               # L2: keep first N chars
TAIL_CHARS = 500               # L2: keep last N chars


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: ~4 chars per token."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += len(part["text"]) // 4
    return total


def micro_compact(messages: list[dict], keep_last: int = 3) -> list[dict]:
    """L1: Keep only the last N tool_result messages; mark older ones [cleared].

    Zero-cost. Runs every iteration. Prevents unbounded tool result accumulation.
    """
    result_indices = [i for i, m in enumerate(messages)
                      if m.get("role") == "tool"]
    if len(result_indices) <= keep_last:
        return messages

    to_clear = result_indices[:-keep_last]
    for i in to_clear:
        content = messages[i].get("content", "")
        if isinstance(content, str) and not content.startswith("[cleared]"):
            messages[i] = {
                **messages[i],
                "content": f"[cleared: {len(content)} chars]",
            }
    return messages


def collapse_large_texts(messages: list[dict]) -> list[dict]:
    """L2: Collapse very long text messages. Keep head + tail, fold middle.

    Zero-cost. Applied when token count exceeds TOKEN_WARN.
    """
    for i, m in enumerate(messages):
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > MAX_TEXT_LEN:
            if content.startswith("[cleared") or "..." in content[-100:]:
                continue
            head = content[:HEAD_CHARS]
            tail = content[-TAIL_CHARS:]
            collapsed = len(content) - HEAD_CHARS - TAIL_CHARS
            messages[i] = {
                **m,
                "content": f"{head}\n\n[...{collapsed} chars collapsed...]\n\n{tail}",
            }
    return messages


def llm_compress(messages: list[dict], llm,
                 trace_dir: Path | None = None,
                 focus_topic: str | None = None,
                 previous_summary: str | None = None) -> tuple[list[dict], str]:
    """L3: Use LLM to summarize conversation history.

    Preserves recent ~20K tokens (tail protection).
    Saves full transcript to trace_dir before compression.
    Returns (compressed_messages, summary_text).
    """
    # Save full transcript
    if trace_dir:
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup = trace_dir / f"transcript_{ts}.jsonl"
        backup.write_text(
            "\n".join(json.dumps(m, ensure_ascii=False, default=str) for m in messages),
            encoding="utf-8",
        )

    # Split: head (to compress) and tail (to protect)
    split_idx = _find_tail_split(messages, TAIL_TOKEN_BUDGET)
    head = messages[:split_idx]
    tail = messages[split_idx:]

    if not head:
        return messages, ""

    # Build compression prompt
    prompt = _COMPRESS_PROMPT.format(
        focus=focus_topic or "the conversation",
        previous=previous_summary or "None",
    )
    head_text = _messages_to_text(head)
    full_prompt = f"{prompt}\n\n## Conversation to summarize\n\n{head_text}"

    try:
        from langchain_openai import ChatOpenAI
        import os
        llm_instance = ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE") or None,
            temperature=0.0, max_tokens=1024,
        )
        result = llm_instance.invoke(full_prompt)
        summary = result.content if hasattr(result, "content") else str(result)

        # Fix tool_call ↔ tool_result pairs
        compressed = _fix_tool_pairs([{"role": "user", "content": f"[Conversation Summary]\n{summary}"}] + list(tail))

        logger.info("L3 compression: %d messages → %d messages + summary (%d chars)",
                     len(messages), len(compressed), len(summary))
        return compressed, summary
    except Exception as exc:
        logger.warning("L3 compression failed: %s", exc)
        return messages, ""


def _find_tail_split(messages: list[dict], token_budget: int) -> int:
    """Find the index where the tail (protected) part starts."""
    tokens = 0
    for i in range(len(messages) - 1, -1, -1):
        content = messages[i].get("content", "")
        if isinstance(content, str):
            tokens += len(content) // 4
        if tokens >= token_budget:
            return i
    return 0


def _messages_to_text(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", "")
        name = m.get("name", "")
        tool_id = m.get("tool_call_id", "")
        prefix = f"[{role}]"
        if name:
            prefix += f"({name})"
        if tool_id:
            prefix += f"({tool_id[:8]})"
        text = content if isinstance(content, str) else json.dumps(content)
        if len(text) > 2000:
            text = text[:2000] + "..."
        lines.append(f"{prefix} {text}")
    return "\n".join(lines)


def _fix_tool_pairs(messages: list[dict]) -> list[dict]:
    """After compression, fix orphaned tool_call/tool_result pairs."""
    # Remove tool_result messages that have no matching tool_call
    tool_call_ids = set()
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                tool_call_ids.add(tc.get("id", ""))
    fixed = []
    for m in messages:
        if m.get("role") == "tool":
            if m.get("tool_call_id") not in tool_call_ids:
                continue  # Orphaned tool_result
        fixed.append(m)
    return fixed


_COMPRESS_PROMPT = """You are a conversation summarizer. Summarize the following conversation segment into a structured summary.

Focus area: {focus}
Previous summary (for incremental update): {previous}

Output format:
1. **Key Decisions Made**: (bullet points)
2. **Data Collected**: (what tools were called, key results)
3. **Current State**: (what's in progress, what's pending)
4. **Important Findings**: (discoveries that must not be lost)

Keep the summary concise but complete. Only summarize what's in the provided text — do not fabricate.
"""
