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
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv("properties.env")

from .progress import HeartbeatTimer, ProgressEvent
from .compression import (
    estimate_tokens, micro_compact, collapse_large_texts,
    llm_compress, apply_tool_result_budget,
    TOKEN_THRESHOLD, TOKEN_WARN,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 8
DEFAULT_TIMEOUT = 600  # 10 minutes


class TerminalReason(Enum):
    """Why the agent loop terminated.

    Inspired by Claude Code query.ts — 10 terminal conditions
    checked at multiple points in the loop. Each reason maps to
    a specific exit path with different recovery behavior.
    """
    # Normal exits
    COMPLETED = "completed"
    # → Model responded without tool_use, stop hooks passed, token budget OK

    # Limit exits
    MAX_TURNS = "max_turns"
    # → turnCount exceeded maxTurns limit

    MAX_BUDGET_USD = "max_budget_usd"
    # → Cumulative API cost exceeded dollar budget

    # User interrupt exits
    ABORTED_STREAMING = "aborted_streaming"
    # → User interrupted during model streaming (Ctrl+C / Stop button)

    ABORTED_TOOLS = "aborted_tools"
    # → User interrupted during tool execution

    # Recovery-failure exits
    PROMPT_TOO_LONG = "prompt_too_long"
    # → 413 error and all recovery paths (collapse drain, reactive compact) failed

    # Hook-prevented exits
    STOP_HOOK_PREVENTED = "stop_hook_prevented"
    # → A stop hook returned preventContinuation: true

    HOOK_STOPPED = "hook_stopped"
    # → A hook during tool execution returned shouldPreventContinuation

    # Error exits
    MODEL_ERROR = "model_error"
    # → Unrecoverable API error (rate limit, auth failure)

    BLOCKING_LIMIT = "blocking_limit"
    # → Token count exceeded hard blocking limit (non-auto-compact mode)

    @property
    def is_user_initiated(self) -> bool:
        """Did the user cause this termination?"""
        return self in (TerminalReason.ABORTED_STREAMING, TerminalReason.ABORTED_TOOLS)

    @property
    def is_recoverable(self) -> bool:
        """Can this termination be recovered from (e.g., via resume)?"""
        return self not in (
            TerminalReason.MODEL_ERROR,
            TerminalReason.BLOCKING_LIMIT,
        )


@dataclass
class AgentConfig:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    timeout_seconds: int = DEFAULT_TIMEOUT
    include_shell_tools: bool = False
    model: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    compress_threshold: int = TOKEN_THRESHOLD


@dataclass
class WorkspaceMemory:
    """Lightweight runtime memory — lives only for one AgentLoop.run() call."""
    session_id: str = ""
    run_dir: Path | None = None
    counters: dict[str, int] = field(default_factory=dict)
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
            self._registry = get_registry(include_shell=self.config.include_shell_tools)
        return self._registry

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            model = self.config.model or os.getenv("OPENAI_MODEL", "deepseek-chat")
            self._llm = ChatOpenAI(
                model=model,
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_api_base=os.getenv("OPENAI_API_BASE") or None,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
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
        started = time.time()

        def _emit(event_type: str, payload: dict | None = None):
            payload = payload or {}
            payload.setdefault("session_id", sid)
            payload.setdefault("ts", time.time())
            if on_event:
                on_event(event_type, payload)

        # ── Build initial messages ──
        tools = registry.get_definitions()
        sys_prompt = system_prompt or self._build_default_system_prompt(registry, user_message)
        messages = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        iteration = 0
        previous_summary = ""

        # ── Run the ReAct loop ──
        gen = self._query_loop(messages, tools, registry, memory, sid, run_dir, started, previous_summary)
        try:
            while True:
                event_type, payload = next(gen)
                _emit(event_type, payload)
        except StopIteration as e:
            return e.value

    def _query_loop(self, messages, tools, registry, memory, sid, run_dir, started, previous_summary):
        """ReAct loop with 5-phase structure per iteration.

        Phases (inspired by Claude Code queryLoop):
        1. preprocess     — context compression
        2. call_model     — streaming LLM call
        3. execute_tools  — run tool calls
        4. inject_attach  — memory/skill injection (placeholder)
        5. check_terminate — decide whether to stop or continue
        """
        iteration = 0

        while iteration < self.config.max_iterations:
            if time.time() - started > self.config.timeout_seconds:
                yield ("error", {"message": f"Timeout after {self.config.timeout_seconds}s"})
                break

            iteration += 1

            # Wrap-up: inject message once at 70%, force no-tools at 100%
            wrap_at = int(self.config.max_iterations * 0.7)
            if iteration == wrap_at:
                messages.append({
                    "role": "user",
                    "content": "Stop calling tools. Answer based on the data you have now."
                })
            force_answer = iteration >= self.config.max_iterations - 1
            active_tools = [] if force_answer else tools

            # ── Phase 1: preprocess ──
            messages, previous_summary = self._preprocess_messages(
                messages, previous_summary, run_dir)

            # ── Phase 2: call model ──
            content, tool_calls = yield from self._call_model_streaming(
                messages, active_tools, iteration)

            if content is None:  # error occurred
                break

            # ── Phase 3: execute tools (or check done) ──
            if not tool_calls:
                is_done, messages = self._check_termination(messages, content)
                if is_done:
                    yield ("answer", {"text": str(content)})
                    break
                continue  # empty content → continuation prompt was added

            # Build assistant message with ALL tool_calls
            messages.append({
                "role": "assistant",
                "content": str(content) if content else None,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"],
                                  "arguments": json.dumps(tc["args"], ensure_ascii=False)}}
                    for tc in tool_calls
                ],
            })

            # Execute ALL tools — let tools themselves validate params
            # and return errors if needed. The LLM learns from tool results.
            tool_events = []
            results = self._execute_batch(tool_calls, registry, memory,
                                          lambda t, p: tool_events.append((t, p)))
            for ev in tool_events:
                yield ev

            for tc, result in zip(tool_calls, results):
                tool_msg = {"role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": result}
                try:
                    cd = _extract_chart(json.loads(result))
                    if cd:
                        tool_msg["chart_data"] = cd
                except Exception:
                    pass
                messages.append(tool_msg)
                memory.increment(tc["name"])

            # ── Phase 4: inject attachments (placeholder) ──
            messages = self._inject_attachments(messages)

        # ── Done ──
        elapsed = time.time() - started
        yield ("done", {"iterations": iteration,
                        "tool_calls": sum(memory.counters.values()),
                        "elapsed_s": round(elapsed, 2)})
        return {"status": "ok", "session_id": sid, "messages": messages,
                "iterations": iteration,
                "tool_count": sum(memory.counters.values()),
                "elapsed_s": round(elapsed, 2),
                "memory": memory.to_summary()}

    # ── Phase 1: preprocess ────────────────────────────────────

    def _preprocess_messages(self, messages, previous_summary, run_dir):
        """Phase 1: Serial compression pipeline before each LLM call.

        L0 → L1 → L2 → L3 (if needed)
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
                messages, llm=None, trace_dir=run_dir,
                previous_summary=previous_summary,
            )
            return messages, new_summary

        return messages, previous_summary

    # ── Phase 2: call model ────────────────────────────────────

    def _call_model_streaming(self, messages, tools, iteration):
        """Phase 2: Stream LLM response, accumulate text + tool calls.

        Yields thinking_start, thinking_delta events.
        Returns (content, tool_calls) tuple, or (None, []) on error.
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
            return None, []

        content = ""
        tool_call_buffers: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.content:
                content += delta.content
                yield ("thinking_delta", {"text": delta.content, "iteration": iteration})

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_call_buffers:
                        tool_call_buffers[idx] = {"id": "", "name": "", "args_str": ""}
                    buf = tool_call_buffers[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["args_str"] += tc_delta.function.arguments

        tool_calls = []
        for idx in sorted(tool_call_buffers.keys()):
            buf = tool_call_buffers[idx]
            args = {}
            if buf["args_str"].strip():
                try:
                    args = json.loads(buf["args_str"])
                except Exception:
                    pass
            tool_calls.append({
                "name": buf["name"], "args": args,
                "id": buf["id"] or f"call_{idx}",
            })

        yield ("thinking_end", {
            "text": str(content)[:2000] if content else "",
            "tool_calls": [{"name": tc["name"], "args": tc["args"]} for tc in tool_calls],
        })

        return content, tool_calls

    # ── Phase 3 helper: filter tools ────────────────────────────

    def _is_empty_args_tool(self, tc: dict) -> bool:
        """Check if a tool call has empty args for tools that need params."""
        if tc["name"] not in ("get_price","get_indicators","get_news","get_fundamentals",
            "get_meta","get_sentiment","search_symbol","search_news","web_search",
            "web_fetch","load_skill"):
            return False
        args = tc.get("args") or {}
        return not (args.get("ticker") or args.get("query") or args.get("name") or args.get("url"))

    # ── Phase 4: inject attachments ─────────────────────────────

    def _inject_attachments(self, messages):
        """Phase 4: Inject memory/skill attachments into messages.
        Placeholder for Phase 4 memory system.
        """
        return messages

    # ── Phase 5: check termination ──────────────────────────────

    def _check_termination(self, messages, content):
        """Phase 5: Check if the loop should terminate.
        Returns (is_done: bool, messages: list).
        """
        messages.append({"role": "assistant", "content": str(content) if content else ""})
        if not content or not str(content).strip():
            messages.append({"role": "user", "content": "Please continue."})
            return False, messages
        return True, messages

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
                emit("tool_progress", {
                    "tool": name, "stage": stage,
                    "current": current, "total": total,
                    "message": message, "elapsed_s": round(elapsed, 2),
                })

            meta = registry.get_meta(name)
            timeout = meta.timeout if meta else 30

            try:
                with HeartbeatTimer(name, emit=progress_emitter):
                    if timeout > 0 and (meta.is_readonly if meta else True):
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            future = pool.submit(registry.execute, name, args, progress_emitter)
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
                        emit("tool_done", {"tool": name, "status": "ok",
                                           "elapsed_s": round(elapsed, 2),
                                           "preview": preview, "chart_data": chart_data})
                    else:
                        emit("tool_error", {"tool": name, "status": "error",
                                            "elapsed_s": round(elapsed, 2),
                                            "error": parsed.get("error", "")[:200]})
                except json.JSONDecodeError:
                    emit("tool_done", {"tool": name, "status": "ok",
                                       "elapsed_s": round(elapsed, 2),
                                       "preview": preview})
                return (index, result)

            except Exception as exc:
                elapsed = time.time() - started
                emit("tool_error", {"tool": name, "status": "error",
                                    "elapsed_s": round(elapsed, 2),
                                    "error": str(exc)[:200]})
                return (index, f'{{"status":"error","error":"{str(exc)[:500]}"}}')

        # Execute read-only in parallel
        if readonly:
            with ThreadPoolExecutor(max_workers=min(len(readonly), 8)) as pool:
                futures = {pool.submit(_invoke, I, tc): I for I, tc in enumerate(readonly)}
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

    def _build_default_system_prompt(self, registry, user_message: str = "") -> str:
        """Build default system prompt with tool descriptions + skills."""
        today = time.strftime("%Y-%m-%d")
        tool_names = registry.get_compact_text()

        # Load skills for injection — only if user message is substantial
        skill_text = ""
        skill_header = ""
        if user_message and len(user_message) > 20:
            skill_text = self._select_relevant_skills(user_message, max_skills=10)
            skill_header = "\n## Relevant Skills\n" + skill_text

        return f"""You are a concise interactive agent. Follow instructions exactly. Never add "What would you like me to do?" or similar offers. Answer briefly.

Today: {today}.

Tools: {tool_names}
{skill_header}
Work: Call tools to get data, then answer immediately. After a tool succeeds, use its result — don't call it again. After a tool fails, try an alternative or answer with what you have. Stop calling tools once you have enough information."""

    def _select_relevant_skills(self, user_message: str, max_skills: int = 20) -> str:
        """Select top N skills relevant to user's query using keyword matching."""
        import re
        from skills.loader import get_loader

        loader = get_loader()
        loader.discover()

        if not loader.skills:
            return "No skills available."

        # Extract keywords (Chinese 2+ chars, English 3+ chars)
        keywords = set(re.findall(r'[\u4e00-\u9fff]{2,}', user_message.lower()))
        keywords |= set(re.findall(r'[a-z]{3,}', user_message.lower()))

        # Score each skill
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
            lines.append(f"- {marker}{skill.name}{marker} [{skill.category}]: {skill.description[:120]}")

        remaining = len(loader.skills) - len(selected)
        if remaining > 0:
            lines.append(f"\n(+{remaining} more skills. Use list_skills to browse all, search_skills(keyword) to find specific ones.)")

        return "\n".join(lines)

    def _list_all_skills_compact(self) -> str:
        """List all skills grouped by category in compact format."""
        from skills.loader import get_loader

        loader = get_loader()
        loader.discover()

        if not loader.skills:
            return "No skills available."

        cats: dict[str, list[str]] = {}
        for s in loader.skills.values():
            cats.setdefault(s.category, []).append(s.name)

        lines = []
        for cat in sorted(cats):
            names = sorted(cats[cat])
            lines.append(f"\n### {cat} ({len(names)})")
            for n in names:
                sk = loader.skills[n]
                builtin_tag = "" if sk.is_builtin else " [user]"
                lines.append(f"- {n}{builtin_tag}: {sk.description[:120]}")

        if len(loader.skills) > 50:
            lines.append("\nTip: Use search_skills(query) to find skills by keyword, or list_skills to browse by category.")

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
                {"id": tc.get("id", f"call_{i}"), "type": "function",
                 "function": {"name": tc.get("name", tc.get("function", {}).get("name", "")),
                              "arguments": json.dumps(tc.get("args", tc.get("function", {}).get("arguments", {})),
                                                     ensure_ascii=False)}}
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
            return [{"d": (b.get("date") or "")[-5:], "v": float(b.get("close", b.get("c", 0)))}
                    for b in data[:100]]
    except Exception:
        pass
    return None
