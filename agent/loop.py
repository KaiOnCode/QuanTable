"""ReActLoop — the core agent execution engine.

ReAct (Reasoning + Acting) loop: think → act → observe → repeat.
Supports tool calling, context compression, progress tracking, and streaming.

Design borrowed from Vibe-Trading's AgentLoop and Claude Code's agent harness.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from server.llm_defaults import DEFAULT_QUICK_THINK_MODEL

from .compression import (
    TOKEN_THRESHOLD,
    TOKEN_WARN,
    apply_tool_result_budget,
    collapse_large_texts,
    estimate_tokens,
    llm_compress,
    micro_compact,
)
from .progress import HeartbeatTimer
from .recovery import (
    RecoveryState,
    classify_error,
    evaluate_termination,
    execute_recovery,
)
from .tools.executor import StreamingToolExecutor

load_dotenv("properties.env")

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 25
DEFAULT_TIMEOUT = 600  # 10 minutes


@dataclass
class AgentConfig:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout_seconds: int = DEFAULT_TIMEOUT
    include_shell_tools: bool = False
    permission_mode: str = "default"  # default | plan | accept_edits | bypass
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    compress_threshold: int = TOKEN_THRESHOLD
    allowed_tools: frozenset[str] | None = None


@dataclass
class WorkspaceMemory:
    """Lightweight runtime memory — lives only for one AgentLoop.run() call."""

    session_id: str = ""
    run_dir: Path | None = None
    counters: dict[str, int] = field(default_factory=dict)
    called_keys: set[str] = field(default_factory=set)  # cross-iteration dedup
    artifacts: list[str] = field(default_factory=list)

    def increment(self, tool_name: str):
        self.counters[tool_name] = self.counters.get(tool_name, 0) + 1

    def to_summary(self) -> str:
        if not self.counters:
            return "No tools called yet."
        parts = [f"Tool calls: {sum(self.counters.values())} total"]
        for name, count in sorted(self.counters.items(), key=lambda x: -x[1])[:10]:
            parts.append(f"  {name}: {count}")
        if self.artifacts:
            parts.append(f"Artifacts: {len(self.artifacts)}")
            for a in self.artifacts[-5:]:
                parts.append(f"  - {a}")
        return "\n".join(parts)


class AgentLoop:
    """Core ReAct execution engine.

    Usage:
        loop = AgentLoop(config=AgentConfig())
        result = loop.run("分析 AAPL", session_id="abc123",
                          on_event=lambda evt: print(evt))
    """

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self._registry = None
        self._llm = None

    def _get_registry(self):
        if self._registry is None:
            from .tools.registry import get_registry

            self._registry = get_registry(
                include_shell=self.config.include_shell_tools,
                allowed_tools=self.config.allowed_tools,
            )
        return self._registry

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI

            model = self.config.model or os.getenv(
                "OPENAI_MODEL", DEFAULT_QUICK_THINK_MODEL
            )
            self._llm = ChatOpenAI(
                model=model,
                api_key=lambda: os.getenv("OPENAI_API_KEY") or "",
                base_url=os.getenv("OPENAI_API_BASE") or None,
                temperature=self.config.temperature,
            )
        return self._llm

    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        history: list[dict] | None = None,
        system_prompt: str | None = None,
        on_event: Callable[[str, dict], None] | None = None,
        run_dir: Path | None = None,
    ) -> dict:
        """Execute a ReAct loop.

        Args:
            user_message: The user's input text.
            session_id: Unique session ID (auto-generated if None).
            history: Previous conversation messages (optional).
            system_prompt: Custom system prompt (uses default if None).
            on_event: Callback for streaming events: on_event(type, payload).
            run_dir: Working directory for file artifacts.

        Returns:
            dict with keys: status, messages, iterations, tool_calls, run_dir
        """
        sid = session_id or str(uuid.uuid4())
        memory = WorkspaceMemory(session_id=sid, run_dir=run_dir)
        registry = self._get_registry()

        # Permission manager
        from agent.tools.permissions import (
            PermissionManager,
            PermissionMode,
        )

        mode_map = {
            "default": PermissionMode.DEFAULT,
            "plan": PermissionMode.PLAN,
            "accept_edits": PermissionMode.ACCEPT_EDITS,
            "bypass": PermissionMode.BYPASS,
        }
        perms = PermissionManager(
            mode_map.get(self.config.permission_mode, PermissionMode.DEFAULT)
        )

        started = time.time()

        def _emit(event_type: str, payload: dict | None = None):
            payload = payload or {}
            payload.setdefault("session_id", sid)
            payload.setdefault("ts", time.time())
            if on_event:
                on_event(event_type, payload)

        # ── Build initial messages ──
        tools = registry.get_definitions()
        sys_prompt = system_prompt or self._build_default_system_prompt(
            registry, user_message
        )
        messages = [{"role": "system", "content": sys_prompt}]

        # Inject user context as first user message only on session start
        # (Claude Code pattern: system-reminder injected once per session, not per turn)
        if not history:
            user_context = self._build_user_context(registry)
            if user_context:
                messages.append(
                    {
                        "role": "user",
                        "content": f"<system-reminder>\n{user_context}\n</system-reminder>",
                    }
                )

        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        previous_summary = ""

        # Tracker for quality evaluation
        from agent.tracker import TaskTracker

        tracker = TaskTracker()

        # ── Run the ReAct loop ──
        gen = self._query_loop(
            messages,
            tools,
            registry,
            memory,
            perms,
            tracker,
            sid,
            run_dir,
            started,
            previous_summary,
        )
        try:
            while True:
                event_type, payload = next(gen)
                _emit(event_type, payload)
        except StopIteration as e:
            return e.value

    def _query_loop(
        self,
        messages,
        tools,
        registry,
        memory,
        perms,
        tracker,
        sid,
        run_dir,
        started,
        previous_summary,
    ):
        """ReAct loop with 5-phase structure per iteration.

        Phases (inspired by Claude Code queryLoop):
        1. preprocess     — context compression
        2. call_model     — streaming LLM call
        3. execute_tools  — run tool calls
        4. inject_attach  — memory/skill injection (placeholder)
        5. check_terminate — decide whether to stop or continue
        """
        iteration = 0
        recovery = RecoveryState()

        while True:
            # ── Safety net: max_iterations (Claude Code: maxTurns) ──
            if iteration >= self.config.max_iterations:
                yield (
                    "error",
                    {"message": f"Max iterations ({self.config.max_iterations})"},
                )
                break

            # ── Timeout check ──
            if time.time() - started > self.config.timeout_seconds:
                yield (
                    "error",
                    {"message": f"Timeout after {self.config.timeout_seconds}s"},
                )
                break

            iteration += 1

            # ── Phase 1: preprocess ──
            messages, previous_summary = self._preprocess_messages(
                messages, previous_summary, run_dir
            )

            # ── Phase 2: call model with streaming tool execution ──
            # Claude Code pattern: StreamingToolExecutor starts tools during streaming.
            tool_events = []
            executor = StreamingToolExecutor(
                registry,
                lambda t, p: tool_events.append((t, p)),
            )

            # Use for loop instead of yield from so we can poll executor
            gen = self._call_model_streaming(
                messages, tools, iteration, executor=executor
            )
            content = ""
            tool_calls = []
            last_error = None
            try:
                while True:
                    event_type, payload = next(gen)
                    yield (event_type, payload)
                    if event_type == "error":
                        last_error = payload.get("message", "")
                    # Poll completed results during streaming
                    for idx, result in executor.get_completed_results().items():
                        yield (
                            "tool_result_early",
                            {
                                "index": idx,
                                "preview": result[:200],
                            },
                        )
            except StopIteration as e:
                content, tool_calls, last_error = e.value

            # Phase 2.5: error classification + recovery decision
            error_type = classify_error(content or "", last_error)
            should_stop, reason, recovery_action = evaluate_termination(
                content or "", tool_calls, error_type, recovery
            )

            if recovery_action:
                executor.abort_all()
                executor.shutdown()
                messages, should_retry, new_max_tokens = execute_recovery(
                    recovery_action,
                    messages,
                    recovery,
                    max_tokens=self.config.max_tokens,
                    run_dir=run_dir,
                )
                if new_max_tokens:
                    self.config.max_tokens = new_max_tokens
                if should_retry:
                    continue
                # Recovery exhausted — should_stop will be True, fall through

            if should_stop:
                executor.abort_all()
                executor.shutdown()
                if content:
                    messages.append({"role": "assistant", "content": str(content)})
                    validated = self._validate_output(str(content), messages)
                    yield ("answer", {"text": validated, "terminal_reason": reason})
                else:
                    yield (
                        "answer",
                        {
                            "text": reason or "completed",
                            "terminal_reason": reason or "completed",
                        },
                    )
                break

            # ── Model didn't call tools → needsFollowUp = false, loop back ──
            if not tool_calls:
                executor.shutdown()
                continue

            # ── needsFollowUp = true: model called tools, continue loop ──

            # Cross-iteration dedup: reject calls already made.
            # Key on tool name + ticker/query only (ignore days/limit params)
            deduped_calls = []
            for stream_index, tc in enumerate(tool_calls):
                tc["_stream_index"] = stream_index
                args = tc.get("args") or {}
                # Dedup key: name + primary identifier (ticker or query)
                primary = (
                    args.get("ticker")
                    or args.get("query")
                    or args.get("name")
                    or args.get("url")
                    or ""
                )
                key = f"{tc['name']}:{primary}"
                if key in memory.called_keys:
                    continue
                memory.called_keys.add(key)
                deduped_calls.append(tc)
            tool_calls = deduped_calls

            if not tool_calls:
                executor.shutdown()
                if content:
                    messages.append({"role": "assistant", "content": str(content)})
                    validated = self._validate_output(str(content), messages)
                    yield (
                        "answer",
                        {"text": validated, "terminal_reason": "completed"},
                    )
                    break
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Those tool calls were already completed. Use the existing "
                            "tool results. Do not repeat them; call a different required "
                            "tool or provide the final answer."
                        ),
                    }
                )
                continue

            # Build assistant message with ALL tool_calls
            messages.append(
                {
                    "role": "assistant",
                    "content": str(content) if content else None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            # ── Consecutive failure tracking (Claude Code circuit breaker) ──
            # If any tool+ticker has failed 2+ times, inject stop instruction
            failed = getattr(memory, "consecutive_failures", {})
            for tc in tool_calls:
                key = f"{tc['name']}:{tc.get('args', {}).get('ticker', '') or tc.get('args', {}).get('query', '')}"
                if failed.get(key, 0) >= 2:
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Tool {tc['name']} has failed {failed[key]} times already. "
                            "STOP retrying. Answer with what data you have, or say it's unavailable.",
                        }
                    )
                    break  # inject only once

            # Permission check before execution
            from agent.tools.permissions import PermissionDecision

            allowed_calls = []
            for tc in tool_calls:
                tool = registry.get(tc["name"])
                decision = (
                    perms.check(tool, tc.get("args", {}))
                    if tool
                    else PermissionDecision.DENY
                )
                if decision == PermissionDecision.DENY:
                    yield (
                        "tool_error",
                        {
                            "tool": tc["name"],
                            "error": f"Permission denied (mode: {perms.mode.value})",
                        },
                    )
                else:
                    allowed_calls.append(tc)
            tool_calls = allowed_calls

            if not tool_calls:
                continue

            # ── Phase 3: collect remaining tool results ──
            # Tools were submitted during streaming; wait for unfinished ones.
            # get_remaining_results() is abort-aware — if recovery signaled abort,
            # in-flight tools get synthetic error results.
            results_dict = executor.get_remaining_results()
            executor.shutdown()
            # Emit any tool events collected during streaming
            for ev in tool_events:
                yield ev

            # Map results back to tool_calls (results_dict is keyed by original index)
            results = [results_dict[tc["_stream_index"]] for tc in tool_calls]

            for tc, result in zip(tool_calls, results):
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["name"],
                    "content": result,
                }
                try:
                    cd = _extract_chart(json.loads(result))
                    if cd:
                        tool_msg["chart_data"] = cd
                except Exception:
                    pass
                messages.append(tool_msg)
                memory.increment(tc["name"])

                # Track consecutive failures for circuit breaker
                try:
                    parsed = json.loads(result)
                    if parsed.get("status") == "error":
                        key = f"{tc['name']}:{tc.get('args', {}).get('ticker', '') or tc.get('args', {}).get('query', '')}"
                        if not hasattr(memory, "consecutive_failures"):
                            memory.consecutive_failures = {}
                        memory.consecutive_failures[key] = (
                            memory.consecutive_failures.get(key, 0) + 1
                        )
                except Exception:
                    pass

            # ── Phase 4: inject attachments (placeholder) ──
            messages = self._inject_attachments(messages)

        # ── Done ──
        elapsed = time.time() - started
        yield (
            "done",
            {
                "iterations": iteration,
                "tool_calls": sum(memory.counters.values()),
                "elapsed_s": round(elapsed, 2),
            },
        )
        return {
            "status": "ok",
            "session_id": sid,
            "messages": messages,
            "iterations": iteration,
            "tool_count": sum(memory.counters.values()),
            "elapsed_s": round(elapsed, 2),
            "memory": memory.to_summary(),
        }

    # ── Phase 1: preprocess ────────────────────────────────────

    def _preprocess_messages(self, messages, previous_summary, run_dir):
        """Phase 1: Serial compression pipeline before each LLM call.

        L0 → L1 → L2 → L3 (if needed) + needle-in-haystack protection.
        """
        # L0: tool result budget (every iteration)
        messages = apply_tool_result_budget(messages)

        # L1: micro-compact (every iteration)
        messages = micro_compact(messages)

        # L2: collapse large texts (when over warn threshold)
        token_count = estimate_tokens(messages)
        if token_count > TOKEN_WARN:
            messages = collapse_large_texts(messages)

        # L3: LLM summary (when over compress threshold)
        if token_count > self.config.compress_threshold:
            messages, new_summary = llm_compress(
                messages,
                llm=None,
                trace_dir=run_dir,
                previous_summary=previous_summary,
            )
            return messages, new_summary

        return messages, previous_summary

    # ── Phase 2: call model ────────────────────────────────────

    def _call_model_streaming(self, messages, tools, iteration, executor=None):
        """Phase 2: Stream LLM response, accumulate text + tool calls.

        If executor is provided, tool calls are submitted for execution
        AS they arrive in the stream (Claude Code StreamingToolExecutor pattern).

        Yields thinking_start, thinking_delta, tool_use_end, error events.
        Returns (content, tool_calls, error_text) tuple.
        """
        yield ("thinking_start", {"iteration": iteration})

        try:
            llm = self._get_llm()
            stream = llm.root_client.chat.completions.create(
                model=llm.model_name,
                messages=_convert_messages(messages),
                tools=_convert_tools(tools),
                temperature=llm.temperature,
                max_tokens=llm.max_tokens,
                stream=True,
            )
        except Exception as exc:
            yield ("error", {"message": f"LLM call failed: {exc}"})
            return None, [], str(exc)

        content = ""
        tool_call_buffers: dict[int, dict] = {}
        tool_calls_submitted = 0

        def _try_parse_args(args_str: str) -> dict | None:
            """Try to parse incrementally accumulated JSON args.
            Returns None if args aren't complete yet (DeepSeek sends
            tool_use arguments as incremental JSON fragments)."""
            if not args_str.strip():
                return None
            try:
                return json.loads(args_str)
            except json.JSONDecodeError:
                return None

        try:
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                if delta.content:
                    content += delta.content
                    yield (
                        "thinking_delta",
                        {"text": delta.content, "iteration": iteration},
                    )

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_buffers:
                            tool_call_buffers[idx] = {
                                "id": "",
                                "name": "",
                                "args_str": "",
                            }
                        buf = tool_call_buffers[idx]
                        if tc_delta.id:
                            buf["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                buf["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                buf["args_str"] += tc_delta.function.arguments
                                # Try parse — if complete JSON, start tool NOW
                                args = _try_parse_args(buf["args_str"])
                                if args is not None and "parsed" not in buf:
                                    buf["parsed"] = True
                                    tc = {
                                        "name": buf["name"],
                                        "args": args,
                                        "id": buf["id"] or f"call_{idx}",
                                    }
                                    if executor:
                                        executor.submit(idx, tc)
                                    tool_calls_submitted += 1
                                    yield (
                                        "tool_use_end",
                                        {
                                            "index": idx,
                                            "tool_call": tc,
                                        },
                                    )
        except Exception as exc:
            yield ("error", {"message": f"Stream interrupted: {exc}"})
            return None, [], str(exc)

        # Assemble tool_calls list (including any that weren't submitted during streaming)
        tool_calls = []
        for idx in sorted(tool_call_buffers.keys()):
            buf = tool_call_buffers[idx]
            if buf["name"]:
                args = {}
                if buf["args_str"].strip():
                    args = _try_parse_args(buf["args_str"]) or {}
                tc = {
                    "name": buf["name"],
                    "args": args,
                    "id": buf["id"] or f"call_{idx}",
                }
                # Submit any tool_use that wasn't parsed during streaming
                # (e.g., DeepSeek sent complete args in a single non-streaming chunk)
                if executor and "parsed" not in buf:
                    executor.submit(idx, tc)
                    tool_calls_submitted += 1
                tool_calls.append(tc)

        yield (
            "thinking_end",
            {
                "text": str(content)[:2000] if content else "",
                "tool_calls": [
                    {"name": tc["name"], "args": tc["args"]} for tc in tool_calls
                ],
            },
        )

        return content, tool_calls, None

    # ── Phase 3 helper: filter tools ────────────────────────────

    def _is_empty_args_tool(self, tc: dict) -> bool:
        """Check if a tool call has empty args for tools that need params."""
        if tc["name"] not in (
            "get_price",
            "get_indicators",
            "get_news",
            "get_fundamentals",
            "get_meta",
            "get_sentiment",
            "search_symbol",
            "search_news",
            "web_search",
            "web_fetch",
            "load_skill",
        ):
            return False
        args = tc.get("args") or {}
        return not (
            args.get("ticker")
            or args.get("query")
            or args.get("name")
            or args.get("url")
        )

    # ── Phase 4: inject attachments ─────────────────────────────

    def _inject_attachments(self, messages):
        """Phase 4: Inject memory/skill attachments into messages.
        Placeholder for Phase 4 memory system.
        """
        return messages

    def _execute_batch(self, tool_calls: list, registry, memory, emit):
        """Execute tools: read-only parallel, write serial. Dedup + non-repeatable skip."""
        if not tool_calls:
            return []

        # Map each tool_call to either "execute" or "skip" with a reason
        seen_calls: set[str] = set()
        exec_plan: list[tuple] = []  # (index, tc, skip_reason or None)
        for i, tc in enumerate(tool_calls):
            name = tc["name"]
            args_key = json.dumps(tc["args"], sort_keys=True) if tc["args"] else "{}"
            call_key = f"{name}:{args_key}"
            if call_key in seen_calls:
                exec_plan.append((i, tc, "duplicate"))
                continue
            meta = registry.get_meta(name)
            if meta and not meta.repeatable and memory.counters.get(name, 0) > 0:
                exec_plan.append((i, tc, "non_repeatable"))
                continue
            seen_calls.add(call_key)
            exec_plan.append((i, tc, None))

        # Separate non-skipped calls for execution
        readonly = []
        write = []
        for _, tc, skip in exec_plan:
            if not skip:
                name = tc["name"]
                meta = registry.get_meta(name)
                if meta and meta.is_readonly:
                    readonly.append(tc)
                else:
                    write.append(tc)

        results: list[tuple[int, str]] = []  # (index, result)

        def _invoke(index, tc):
            name = tc["name"]
            args = tc["args"] or {}
            started = time.time()
            emit("tool_call", {"tool": name, "args": args})

            def progress_emitter(stage, current, total, message):
                elapsed = time.time() - started
                emit(
                    "tool_progress",
                    {
                        "tool": name,
                        "stage": stage,
                        "current": current,
                        "total": total,
                        "message": message,
                        "elapsed_s": round(elapsed, 2),
                    },
                )

            meta = registry.get_meta(name)
            timeout = meta.timeout if meta else 30

            try:
                with HeartbeatTimer(name, emit=progress_emitter):
                    if timeout > 0 and (meta.is_readonly if meta else True):
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(
                                registry.execute, name, args, progress_emitter
                            )
                            result = future.result(timeout=timeout)
                    else:
                        result = registry.execute(name, args, progress_emitter)

                elapsed = time.time() - started
                # Try to parse result as JSON for a preview
                preview = result[:1500]  # Enough for chart data
                chart_data = None
                try:
                    parsed = json.loads(result)
                    if parsed.get("status") == "ok":
                        # Extract chartable data
                        chart_data = _extract_chart(parsed)
                        emit(
                            "tool_done",
                            {
                                "tool": name,
                                "status": "ok",
                                "elapsed_s": round(elapsed, 2),
                                "preview": preview,
                                "chart_data": chart_data,
                            },
                        )
                    else:
                        emit(
                            "tool_error",
                            {
                                "tool": name,
                                "status": "error",
                                "elapsed_s": round(elapsed, 2),
                                "error": parsed.get("error", "")[:200],
                            },
                        )
                except json.JSONDecodeError:
                    emit(
                        "tool_done",
                        {
                            "tool": name,
                            "status": "ok",
                            "elapsed_s": round(elapsed, 2),
                            "preview": preview,
                        },
                    )
                return (index, result)

            except Exception as exc:
                elapsed = time.time() - started
                emit(
                    "tool_error",
                    {
                        "tool": name,
                        "status": "error",
                        "elapsed_s": round(elapsed, 2),
                        "error": str(exc)[:200],
                    },
                )
                return (index, f'{{"status":"error","error":"{str(exc)[:500]}"}}')

        # Execute read-only in parallel
        if readonly:
            with ThreadPoolExecutor(max_workers=min(len(readonly), 8)) as pool:
                futures = {
                    pool.submit(_invoke, index, tc): index
                    for index, tc in enumerate(readonly)
                }
                for f in as_completed(futures):
                    results.append(f.result())

        # Execute write tools serially
        for i, tc in enumerate(write, start=len(readonly)):
            results.append(_invoke(i, tc))

        # Sort by original index
        results.sort(key=lambda x: x[0])
        final_results = []
        for i, tc, skip in exec_plan:
            if skip:
                final_results.append(f'{{"status":"error","error":"Skipped: {skip}"}}')
            else:
                # Find the result for this index
                for ri, r in results:
                    if ri == i:
                        final_results.append(r)
                        break
                else:
                    final_results.append('{"status":"error","error":"No result"}')
        return final_results

    def _validate_output(self, content: str, messages: list) -> str:
        """Validate agent output against tool results. Appends warning if needed."""
        try:
            from agent.validator import validate_answer

            warning = validate_answer(content, messages)
            if warning:
                return content + warning
        except Exception:
            pass
        return content

    def _build_default_system_prompt(self, registry, user_message: str = "") -> str:
        """Build system prompt. Delegates to agent/prompts.py."""
        from agent.prompts import build_system_prompt

        return build_system_prompt(registry, user_message)

    def _build_user_context(self, registry) -> str:
        """Build user context injected as first user message.

        Modeled after Claude Code's <system-reminder> pattern.
        Contains: available data summary, usage tips.
        """
        today = time.strftime("%Y-%m-%d")
        lines = [
            f"Current date: {today}",
            f"Available tools: {registry.tool_count}",
            "Key tools: get_price(stock prices), get_indicators(RSI,MACD,SMA), "
            "get_news(stock news), get_fundamentals(PE,PB,ROE), "
            "web_search(internet search), search_symbol(find ticker)",
            "Tip: call multiple read tools in one batch for efficiency.",
            "Tip: after getting data, answer immediately — don't keep searching.",
        ]
        return "\n".join(lines)


def _convert_messages(messages: list[dict]) -> list[dict]:
    """Convert internal message format to OpenAI API format."""
    api_msgs = []
    for m in messages:
        role = m.get("role", "user")
        entry: dict = {"role": role}
        if m.get("content"):
            entry["content"] = str(m["content"])
        if m.get("tool_calls"):
            entry["tool_calls"] = [
                {
                    "id": tc.get("id", f"call_{i}"),
                    "type": "function",
                    "function": {
                        "name": tc.get("name", tc.get("function", {}).get("name", "")),
                        "arguments": json.dumps(
                            tc.get("args", tc.get("function", {}).get("arguments", {})),
                            ensure_ascii=False,
                        ),
                    },
                }
                for i, tc in enumerate(m["tool_calls"])
            ]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
        if m.get("name"):
            entry["name"] = m["name"]
        if role == "system":
            entry["role"] = "system"
        api_msgs.append(entry)
    return api_msgs


def _convert_tools(tools: list[dict]) -> list[dict]:
    """Convert tool definitions to OpenAI API format."""
    return [{"type": "function", "function": t["function"]} for t in tools]


def _extract_chart(result: dict) -> list | None:
    """Extract chart data from tool result. Prefers 'bars' (all data) over 'recent' (last 5)."""
    try:
        data = result.get("bars") or result.get("recent")
        if data and isinstance(data, list) and len(data) >= 2:
            return [
                {
                    "d": (b.get("date") or "")[-5:],
                    "v": float(b.get("close", b.get("c", 0))),
                }
                for b in data[:100]
            ]
    except Exception:
        pass
    return None
