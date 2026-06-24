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
from queue import Queue
from typing import Any, Callable

from dotenv import load_dotenv

load_dotenv("properties.env")

from .progress import HeartbeatTimer, ProgressEvent
from .context_compression import (
    estimate_tokens, micro_compact, collapse_large_texts,
    llm_compress, TOKEN_THRESHOLD, TOKEN_WARN,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 25
DEFAULT_TIMEOUT = 600  # 10 minutes


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
        sys_prompt = system_prompt or self._build_default_system_prompt(registry)
        messages = [{"role": "system", "content": sys_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        iteration = 0
        previous_summary = ""

        # ── ReAct Loop ──
        while iteration < self.config.max_iterations:
            elapsed = time.time() - started
            if elapsed > self.config.timeout_seconds:
                _emit("error", {"message": f"Timeout after {self.config.timeout_seconds}s"})
                break

            iteration += 1

            # ── Context compression ──
            token_count = estimate_tokens(messages)

            # L1: micro-compact (every iteration, zero cost)
            messages = micro_compact(messages)

            # L2: collapse large texts
            if token_count > TOKEN_WARN:
                messages = collapse_large_texts(messages)

            # L3: LLM compression
            if token_count > self.config.compress_threshold:
                _emit("compact", {"before_tokens": token_count})
                messages, new_summary = llm_compress(
                    messages, llm=None,
                    trace_dir=run_dir,
                    previous_summary=previous_summary,
                )
                previous_summary = new_summary
                _emit("compact_done", {"after_tokens": estimate_tokens(messages)})

            # ── Call LLM ──
            _emit("thinking_start", {"iteration": iteration})

            try:
                llm = self._get_llm()
                llm_with_tools = llm.bind_tools(tools)
                response = llm_with_tools.invoke(messages)
            except Exception as exc:
                _emit("error", {"message": f"LLM call failed: {exc}"})
                break

            content = response.content if hasattr(response, "content") else ""
            tool_calls = response.tool_calls if hasattr(response, "tool_calls") else []

            _emit("thinking_end", {
                "text": str(content)[:2000] if content else "",
                "tool_calls": [{"name": tc.get("name", ""), "args": tc.get("args", {})}
                               for tc in (tool_calls or [])],
            })

            # ── No tool calls → check if done ──
            if not tool_calls:
                assistant_msg = {"role": "assistant", "content": str(content) if content else ""}
                messages.append(assistant_msg)

                if not content or len(str(content).strip()) < 50:
                    # Very short response, prompt to continue
                    messages.append({"role": "user", "content": "Please continue your analysis or provide a final answer. What have you found so far?"})
                    continue
                else:
                    _emit("answer", {"text": str(content)})
                    break

            # ── Execute tools ──
            assistant_msg = {
                "role": "assistant",
                "content": str(content) if content else None,
                "tool_calls": [
                    {"id": tc.get("id", f"call_{i}"),
                     "type": "function",
                     "function": {"name": tc.get("name", ""),
                                  "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False)}}
                    for i, tc in enumerate(tool_calls)
                ],
            }
            messages.append(assistant_msg)

            results = self._execute_batch(tool_calls, registry, memory, _emit)

            for tc, result in zip(tool_calls, results):
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{hash(tc.get('name',''))}"),
                    "name": tc.get("name", ""),
                    "content": result,
                }
                messages.append(tool_msg)
                memory.increment(tc.get("name", "unknown"))

        # ── Done ──
        elapsed = time.time() - started
        _emit("done", {
            "iterations": iteration,
            "tool_calls": sum(memory.counters.values()),
            "elapsed_s": round(elapsed, 2),
        })

        return {
            "status": "ok",
            "session_id": sid,
            "messages": messages,
            "iterations": iteration,
            "tool_count": sum(memory.counters.values()),
            "elapsed_s": round(elapsed, 2),
            "memory": memory.to_summary(),
        }

    def _execute_batch(self, tool_calls: list, registry, memory, emit):
        """Execute tools: read-only parallel, write serial."""
        if not tool_calls:
            return []

        # Separate read-only and write tools
        readonly = []
        write = []
        for tc in tool_calls:
            name = tc.get("name", "")
            meta = registry.get_meta(name)
            if meta and meta.is_readonly:
                readonly.append(tc)
            else:
                write.append(tc)

        results: list[tuple[int, str]] = []  # (index, result)

        def _invoke(index, tc):
            name = tc.get("name", "")
            args = tc.get("args", {})
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
                preview = result[:200]
                try:
                    parsed = json.loads(result)
                    if parsed.get("status") == "ok":
                        emit("tool_done", {"tool": name, "status": "ok",
                                           "elapsed_s": round(elapsed, 2),
                                           "preview": preview})
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
        return [r[1] for r in results]

    def _build_default_system_prompt(self, registry) -> str:
        """Build default system prompt with tool descriptions + skills."""
        today = time.strftime("%Y-%m-%d")
        tool_text = registry.get_description_text()

        # Load skills for injection
        skill_text = ""
        try:
            import os as _os
            from skills.loader import SkillLoader
            skills_dir = _os.path.join(_os.path.dirname(_os.path.dirname(
                _os.path.dirname(_os.path.abspath(__file__)))), "skills")
            loader = SkillLoader(skills_dir)
            loader.discover()
            if loader.skills:
                cats: dict[str, list[str]] = {}
                for s in loader.skills.values():
                    cats.setdefault(s.category, []).append(s.name)
                skill_lines = []
                for cat, names in sorted(cats.items()):
                    skill_lines.append(f"\n### {cat}")
                    for n in sorted(names)[:5]:  # Top 5 per category
                        skill_lines.append(f"- {n}: {loader.skills[n].description[:100]}")
                skill_text = "\n".join(skill_lines)
        except Exception:
            pass

        return f"""You are a financial AI agent with access to {registry.tool_count} tools. You can research markets, analyze stocks, search the web, read documents, and execute analyses.

Today's date is {today}. All analysis should be based on this date.

## Available Tools
{tool_text}

## Skills (use load_skill to read full docs)
{skill_text if skill_text else "No skills loaded."}

## How to Work
1. Think step by step. Before calling tools, explain your reasoning.
2. Use tools to gather data. Don't guess — always verify with real data.
3. Read-only tools can be called in parallel. Write tools must be called one at a time.
4. When you have enough information, provide a complete answer in Chinese.
5. Cite specific data from tool results in your analysis.
6. If a tool fails, try an alternative approach.

## Guidelines
- Always provide specific numbers (prices, percentages, dates) from tool results
- If you're unsure about something, use web_search to find the answer
- For Chinese A-share stocks, include sector and fund flow analysis
- For US stocks, include fundamental metrics and macro context
- Wrap up each analysis with a clear conclusion"""
