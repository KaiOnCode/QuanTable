"""Recovery pipeline — error classification, termination decision, recovery execution.

Claude Code references:
- query/transitions.ts  — Terminal (10 types) + Continue (7 types)
- query.ts Phase 4       — 8-step decision tree (lines 1349-1647)
- services/compact/      — reactiveCompact, autoCompact

Design: every recovery action returns (modified_messages, should_retry).
Cheapest recovery first (free → 1 API call → surface error).
RecoveryState tracks attempts to prevent infinite loops.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent.state import TerminalReason


class ErrorType(Enum):
    """Error types that can trigger recovery. 参照 Claude Code Phase 4 checks."""
    PROMPT_TOO_LONG = "prompt_too_long"        # 413 / context overflow
    MAX_OUTPUT_TOKENS = "max_output_tokens"    # Hit output token cap
    EMPTY_RESPONSE = "empty_response"          # Model produced no content
    RATE_LIMIT = "rate_limit"                  # Rate limited
    MODEL_ERROR = "model_error"                # Unrecoverable API error


@dataclass
class RecoveryState:
    """Tracks recovery attempts to prevent infinite loops.

    参照 Claude Code query.ts State fields:
    - hasAttemptedReactiveCompact
    - maxOutputTokensRecoveryCount
    - maxOutputTokensOverride
    - maxOutputTokensRecoveryCount
    """

    # prompt_too_long recovery
    collapse_drain_attempted: bool = False
    reactive_compact_attempted: bool = False

    # max_output_tokens recovery
    max_tokens_escalated: bool = False
    max_tokens_recovery_count: int = 0

    # empty_response recovery
    empty_response_count: int = 0

    # rate_limit recovery
    rate_limit_retries: int = 0

    # model fallback
    fallback_attempted: bool = False

    def reset_soft_counters(self):
        """Reset counters after a successful turn — keeps hard blockers.
        参照 Claude Code: some counters reset on success, some don't."""
        self.empty_response_count = 0
        self.rate_limit_retries = 0


# ── Error classification ──────────────────────────────────────

def classify_error(content: str, last_error: str | None) -> ErrorType | None:
    """Classify what kind of error/recovery situation we're in.

    参照 Claude Code Phase 4 error checks:
    - isWithheld413 / isPromptTooLongMessage
    - isWithheldMaxOutputTokens
    - isApiErrorMessage
    """
    if last_error:
        err_str = str(last_error).lower()
        if "413" in err_str or "prompt_too_long" in err_str or "context_length" in err_str:
            return ErrorType.PROMPT_TOO_LONG
        if "max_output_tokens" in err_str or "max_tokens" in err_str:
            return ErrorType.MAX_OUTPUT_TOKENS
        if "rate_limit" in err_str or "too many requests" in err_str or "429" in err_str:
            return ErrorType.RATE_LIMIT
        if "auth" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
            return ErrorType.MODEL_ERROR
        # Unknown error
        return ErrorType.MODEL_ERROR

    if not content or not str(content).strip():
        return ErrorType.EMPTY_RESPONSE

    return None


# ── Termination decision tree ─────────────────────────────────

def evaluate_termination(
    content: str,
    tool_calls: list,
    error_type: ErrorType | None,
    recovery: RecoveryState,
) -> tuple[bool, str | None, str | None]:
    """Complete termination decision tree.

    参照 Claude Code query.ts Phase 4 (lines 1349-1647):

    Decision order (cheapest recovery first):
    1. prompt_too_long  → collapse_drain (free) → reactive_compact (1 API call) → terminal
    2. max_output_tokens → escalate to 64k → inject recovery msg (max 3x) → terminal
    3. empty_response   → inject continue_prompt (max 2x) → terminal
    4. rate_limit       → exponential backoff retry (max 3x) → terminal
    5. model_error      → terminal (unrecoverable)
    6. no error + content + no tool_calls → COMPLETED
    7. has tool_calls   → do not stop (needsFollowUp = true)

    Returns:
        (should_stop, terminal_reason_value, recovery_action)
    """
    # If model called tools → needsFollowUp = true, don't terminate
    if tool_calls:
        return False, None, None

    # Step 1: prompt_too_long recovery
    # Claude Code: collapse drain (free, no API call) → reactive compact (1 API) → surface
    if error_type == ErrorType.PROMPT_TOO_LONG:
        if not recovery.collapse_drain_attempted:
            return False, TerminalReason.PROMPT_TOO_LONG.value, "collapse_drain"
        if not recovery.reactive_compact_attempted:
            return False, TerminalReason.PROMPT_TOO_LONG.value, "reactive_compact"
        # Both recovery stages exhausted → surface error
        return True, TerminalReason.PROMPT_TOO_LONG.value, None

    # Step 2: max_output_tokens recovery
    # Claude Code: escalate default 8k → 64k (once) → multi-turn recovery msg (up to 3)
    if error_type == ErrorType.MAX_OUTPUT_TOKENS:
        if not recovery.max_tokens_escalated:
            return False, None, "escalate_max_tokens"
        if recovery.max_tokens_recovery_count < 3:
            return False, None, "inject_recovery_message"
        return True, TerminalReason.MODEL_ERROR.value, None

    # Step 3: empty_response recovery
    if error_type == ErrorType.EMPTY_RESPONSE:
        if recovery.empty_response_count < 2:
            return False, None, "continue_prompt"
        return True, TerminalReason.MODEL_ERROR.value, None

    # Step 4: rate_limit recovery
    if error_type == ErrorType.RATE_LIMIT:
        if recovery.rate_limit_retries < 3:
            return False, None, "retry_with_backoff"
        return True, TerminalReason.MODEL_ERROR.value, None

    # Step 5: model_error → terminal (unrecoverable)
    # Claude Code: "Skip stop hooks when last message is an API error"
    if error_type == ErrorType.MODEL_ERROR:
        return True, TerminalReason.MODEL_ERROR.value, None

    # Step 6: normal completion
    # Claude Code: return { reason: 'completed' }
    if content and str(content).strip():
        return True, TerminalReason.COMPLETED.value, None

    # Fallback: no content, no tool calls, no error → inject continue prompt
    return False, None, "continue_prompt"


# ── Recovery execution ────────────────────────────────────────

def execute_recovery(
    action: str,
    messages: list,
    recovery: RecoveryState,
    max_tokens: int | None = None,
    run_dir: Path | None = None,
) -> tuple[list, bool, int | None]:
    """Execute a recovery action. 参照 Claude Code Phase 4 continue blocks.

    Each action maps to a specific Claude Code Continue reason:
    - collapse_drain  → { reason: 'collapse_drain_retry', committed: N }
    - reactive_compact → { reason: 'reactive_compact_retry' }
    - escalate_max_tokens → { reason: 'max_output_tokens_escalate' }
    - inject_recovery_message → { reason: 'max_output_tokens_recovery', attempt: N }
    - continue_prompt → generic continuation
    - retry_with_backoff → rate limit backoff

    Returns:
        (messages, should_retry_api, new_max_tokens)
    """
    if action == "collapse_drain":
        # Free context release — truncate tool_results. No API call.
        # Claude Code: contextCollapse.recoverFromOverflow()
        recovery.collapse_drain_attempted = True
        drained = _collapse_drain(messages)
        return drained, True, max_tokens

    if action == "reactive_compact":
        # Costs 1 API call — LLM summary of conversation.
        # Claude Code: reactiveCompact.tryReactiveCompact()
        recovery.reactive_compact_attempted = True
        try:
            from agent.compression import llm_compress
            compacted, _ = llm_compress(
                messages, llm=None, trace_dir=run_dir,
            )
            return compacted, True, max_tokens
        except Exception:
            # Compact failed → let the error surface next iteration
            return messages, False, max_tokens

    if action == "escalate_max_tokens":
        # Claude Code: escalate from default 8k to ESCALATED_MAX_TOKENS (64k)
        # No meta message, no extra turn — just retry with bigger budget.
        recovery.max_tokens_escalated = True
        return messages, True, 64000

    if action == "inject_recovery_message":
        # Claude Code: multi-turn max_output_tokens recovery (up to 3 attempts)
        recovery.max_tokens_recovery_count += 1
        messages.append({
            "role": "user",
            "content": (
                "Output token limit hit. Resume directly — no apology, "
                "no recap of what you were doing. Pick up mid-thought if "
                "that is where the cut happened. Break remaining work "
                "into smaller pieces."
            ),
        })
        return messages, True, max_tokens

    if action == "continue_prompt":
        recovery.empty_response_count += 1
        messages.append({"role": "user", "content": "Please continue."})
        return messages, True, max_tokens

    if action == "retry_with_backoff":
        recovery.rate_limit_retries += 1
        wait = min(2 ** recovery.rate_limit_retries, 60)
        time.sleep(wait)
        return messages, True, max_tokens

    # Unknown action
    return messages, False, max_tokens


# ── collapse_drain — free context release ─────────────────────

def _collapse_drain(messages: list, max_chars: int = 1000) -> list:
    """Free context release: truncate all tool_results aggressively.

    Claude Code: contextCollapse.recoverFromOverflow() — commits staged
    collapses without an API call. This is the first recovery step for
    prompt-too-long errors.

    Keeps head + tail of each tool_result, drops the middle. No API call.
    """
    head = max_chars // 2
    tail = max_chars // 2

    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            continue
        content = m.get("content", "")
        if isinstance(content, str) and len(content) > max_chars:
            messages[i] = {
                **m,
                "content": (
                    content[:head]
                    + f"\n\n[...collapse drain: {len(content) - head - tail} chars removed...]\n\n"
                    + content[-tail:]
                ),
            }
    return messages
