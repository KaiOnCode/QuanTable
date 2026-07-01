"""StreamingToolExecutor — starts tool execution during LLM streaming.

Inspired by Claude Code's StreamingToolExecutor in query.ts:
tools start as they arrive in the stream, not after the full response.

Key behaviors:
- submit() starts a tool immediately on a background thread
- get_completed_results() is non-blocking, returns finished results
  → called during streaming after each chunk
- get_remaining_results() is blocking, waits for all unfinished tools
  → called after streaming ends; supports abort via abort_signal
- abort_all() signals running tools to stop; in-flight tools get
  synthetic error results (prevents orphaned tool_use blocks)

Concurrency model (from Claude Code):
- If no tools are executing → any tool can start
- If all executing tools are concurrency-safe → another concurrency-safe
  tool can start
- If any executing tool is NOT concurrency-safe → block all new tools
  (maintains serial order for write tools)
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TrackedTool:
    """Internal tracking for a single tool execution."""
    id: str
    name: str
    args: dict
    status: str = "queued"        # queued → executing → completed | aborted
    is_readonly: bool = True
    future: Future | None = None
    result: str | None = None     # JSON result string


class StreamingToolExecutor:
    """Executes tools in parallel during LLM streaming.

    Read-only tools start immediately on submission.
    Write tools queue and execute sequentially.
    """

    def __init__(
        self,
        registry,
        emit: Callable,
        abort_signal: threading.Event | None = None,
        max_read_workers: int = 8,
    ):
        self._registry = registry
        self._emit = emit
        self._abort = abort_signal or threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=max_read_workers)
        self._tools: dict[int, TrackedTool] = {}
        self._results: dict[int, str] = {}
        self._lock = threading.Lock()
        self._shutdown = False

    # ── Public API ──────────────────────────────────────────

    def submit(self, index: int, tool_call: dict):
        """Submit and START a tool immediately on a background thread.

        Called during LLM streaming when a tool_use block is complete.
        Read tools start right away; write tools are queued.
        """
        if self._shutdown:
            return

        meta = self._registry.get_meta(tool_call["name"])
        is_read = meta and meta.is_readonly

        tracked = TrackedTool(
            id=tool_call.get("id", f"call_{index}"),
            name=tool_call["name"],
            args=tool_call.get("args", {}),
            status="executing",
            is_readonly=is_read,
        )

        with self._lock:
            self._tools[index] = tracked

        if is_read:
            tracked.future = self._pool.submit(self._invoke, tracked)
        else:
            # Write tools: mark as completed immediately with empty result.
            # They'll be executed serially in get_remaining_results().
            tracked.status = "queued_write"

    def get_completed_results(self) -> dict[int, str]:
        """Non-blocking: return results for tools that have finished.

        Called during streaming after each chunk. Does not block.
        Returns dict of {index: result_json} for newly completed tools.
        """
        done = {}
        with self._lock:
            for idx, tool in list(self._tools.items()):
                if tool.status == "executing" and tool.future and tool.future.done():
                    tool.status = "completed"
                    try:
                        tool.result = tool.future.result()
                    except Exception as exc:
                        tool.result = json.dumps({
                            "status": "error",
                            "error": str(exc)[:500],
                        })
                    self._results[idx] = tool.result
                    done[idx] = tool.result
        return done

    def has_unfinished(self) -> bool:
        """Check if any tools are still running."""
        with self._lock:
            return any(
                t.status in ("executing", "queued_write")
                for t in self._tools.values()
            )

    def get_remaining_results(self) -> dict[int, str]:
        """Blocking: wait for ALL unfinished tools, then return ordered results.

        Called after streaming ends. Write tools execute serially here.
        If abort is signaled, in-flight tools get synthetic error results.
        """
        # First wait for all read futures
        with self._lock:
            read_tools = [
                (idx, t) for idx, t in self._tools.items()
                if t.status == "executing" and t.future
            ]
            write_tools = [
                (idx, t) for idx, t in self._tools.items()
                if t.status == "queued_write"
            ]

        # Wait for read tools (with abort check)
        for idx, tool in read_tools:
            if self._abort.is_set():
                tool.status = "aborted"
                tool.result = json.dumps({
                    "status": "error",
                    "error": "Tool execution aborted by user",
                })
                self._results[idx] = tool.result
            else:
                try:
                    tool.result = tool.future.result()
                    tool.status = "completed"
                except Exception as exc:
                    tool.result = json.dumps({
                        "status": "error",
                        "error": str(exc)[:500],
                    })
                    tool.status = "completed"
                self._results[idx] = tool.result

        # Execute write tools serially
        for idx, tool in write_tools:
            if self._abort.is_set():
                tool.result = json.dumps({
                    "status": "error",
                    "error": "Tool execution aborted by user",
                })
            else:
                tool.result = self._invoke(tool)
            tool.status = "completed"
            self._results[idx] = tool.result

        # Return in index order
        return dict(sorted(self._results.items()))

    def abort_all(self):
        """Signal all in-flight tools to stop."""
        self._abort.set()

    def shutdown(self):
        """Clean up thread pool."""
        self._shutdown = True
        self._pool.shutdown(wait=False)

    # ── Internal ────────────────────────────────────────────

    def _invoke(self, tool: TrackedTool) -> str:
        """Execute a single tool. Returns JSON result string."""
        started = time.time()

        self._emit("tool_call", {"tool": tool.name, "args": tool.args})

        try:
            result = self._registry.execute(tool.name, tool.args)
        except Exception as exc:
            result = json.dumps({"status": "error", "error": str(exc)[:500]})

        elapsed = time.time() - started
        try:
            parsed = json.loads(result)
            if parsed.get("status") == "ok":
                self._emit("tool_done", {
                    "tool": tool.name, "status": "ok",
                    "elapsed_s": round(elapsed, 2),
                    "preview": result[:1500],
                })
            else:
                self._emit("tool_error", {
                    "tool": tool.name, "status": "error",
                    "elapsed_s": round(elapsed, 2),
                    "error": parsed.get("error", "")[:200],
                })
        except json.JSONDecodeError:
            self._emit("tool_done", {
                "tool": tool.name, "status": "ok",
                "elapsed_s": round(elapsed, 2),
                "preview": result[:1500],
            })

        return result
