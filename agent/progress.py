"""Progress tracking — HeartbeatTimer + ProgressEvent for agent tool execution.

Design borrowed from Vibe-Trading's progress system.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    tool: str
    stage: str
    current: int | None = None
    total: int | None = None
    message: str = ""
    elapsed_s: float = 0.0
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "elapsed_s": round(self.elapsed_s, 2),
            "ts": self.ts,
        }


_EmitterType = Callable[..., None]


class HeartbeatTimer:
    """Background daemon thread that emits 'tool_heartbeat' events every interval
    while a tool is executing. Used via context manager:

        with HeartbeatTimer("get_price", emit=callback):
            result = registry.execute(...)
    """

    def __init__(
        self, tool_name: str, interval: float = 3.0, emit: _EmitterType | None = None
    ):
        self._tool = tool_name
        self._interval = max(0.5, interval)
        self._emit = emit
        self._started = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _run(self):
        while not self._stop.wait(self._interval):
            elapsed = time.time() - self._started
            if self._emit:
                try:
                    self._emit(
                        stage="heartbeat",
                        current=None,
                        total=None,
                        message=f"Running... ({elapsed:.0f}s)",
                    )
                except Exception:
                    pass

    def __enter__(self):
        self._started = time.time()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None
