"""StreamingToolExecutor — starts tool execution during LLM streaming.

Inspired by Claude Code's StreamingToolExecutor in query.ts:
not after the full LLM response completes.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Any, Callable


class StreamingToolExecutor:
    """Executes tools in parallel during LLM streaming.

    Read-only tools start immediately upon registration.
    Write tools queue and execute sequentially after streaming ends.
    """

    def __init__(self, registry, emit: Callable, max_read_workers: int = 8):
        self.registry = registry
        self.emit = emit
        self._read_pool = ThreadPoolExecutor(max_workers=max_read_workers)
        self._read_futures: dict[int, Future] = {}    # index → Future
        self._write_queue: list[tuple[int, dict]] = []  # (index, tool_call)
        self._results: dict[int, str] = {}              # index → result JSON

    def submit(self, index: int, tool_call: dict):
        """Register a tool for execution. Read tools start immediately."""
        meta = self.registry.get_meta(tool_call["name"])
        is_read = meta and meta.is_readonly

        if is_read:
            future = self._read_pool.submit(self._invoke, tool_call)
            self._read_futures[index] = future
        else:
            self._write_queue.append((index, tool_call))

    def _invoke(self, tc: dict) -> tuple[int, str]:
        """Execute a single tool and return (index, result_json)."""
        name = tc["name"]
        args = tc.get("args") or {}
        started = time.time()

        self.emit("tool_call", {"tool": name, "args": args})

        try:
            result = self.registry.execute(name, args)
        except Exception as exc:
            result = json.dumps({"status": "error", "error": str(exc)[:500]})

        elapsed = time.time() - started
        try:
            parsed = json.loads(result)
            if parsed.get("status") == "ok":
                self.emit("tool_done", {"tool": name, "status": "ok",
                                        "elapsed_s": round(elapsed, 2),
                                        "preview": result[:1500]})
            else:
                self.emit("tool_error", {"tool": name, "status": "error",
                                         "elapsed_s": round(elapsed, 2),
                                         "error": parsed.get("error", "")[:200]})
        except json.JSONDecodeError:
            self.emit("tool_done", {"tool": name, "status": "ok",
                                    "elapsed_s": round(elapsed, 2),
                                    "preview": result[:1500]})

        return result

    def get_completed_read_results(self) -> dict[int, str]:
        """Get results from read tools that finished during streaming."""
        done = {}
        for idx, future in list(self._read_futures.items()):
            if future.done():
                done[idx] = future.result()
                del self._read_futures[idx]
        return done

    def collect_all_results(self) -> list[str]:
        """Wait for all tools (read + write) and return ordered results."""
        # Wait for remaining read futures
        for idx, future in self._read_futures.items():
            self._results[idx] = future.result()

        # Execute write tools sequentially
        for idx, tc in self._write_queue:
            self._results[idx] = self._invoke(tc)

        # Return in index order
        return [self._results[i] for i in sorted(self._results.keys())]

    def shutdown(self):
        self._read_pool.shutdown(wait=False)
