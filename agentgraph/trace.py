"""TraceWriter — crash-safe JSONL trace recording for agent sessions.

Large fields (>50KB) are offloaded to side files to keep the main trace
file lightweight. Design borrowed from Vibe-Trading's trace system.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class TraceWriter:
    """Append-only JSONL trace writer. Crash-safe (flush after each write)."""

    def __init__(self, dir_path: Path):
        dir_path.mkdir(parents=True, exist_ok=True)
        self.dir = dir_path
        self.path = dir_path / "trace.jsonl"
        self.blobs_dir = dir_path / "trace-blobs"
        self.blobs_dir.mkdir(exist_ok=True)
        self._handle = open(self.path, "a", encoding="utf-8")
        self._count = 0

    def write(self, entry: dict):
        """Write a JSON line to the trace file. Auto-adds timestamp and index."""
        entry.setdefault("ts", time.time())
        entry["_idx"] = self._count
        self._count += 1
        self._handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        self._handle.flush()

    def write_tool_result(self, tool_name: str, result: str,
                          params: dict | None = None):
        """Write a tool_result entry. Large results are offloaded to a blob file."""
        entry: dict = {"type": "tool_result", "tool": tool_name, "params": params}
        if len(result) > 50_000:
            digest = hashlib.sha256(f"{tool_name}\0{result}".encode()).hexdigest()
            blob_path = self.blobs_dir / f"{digest[:24]}.txt"
            blob_path.write_text(result, encoding="utf-8")
            entry["result_path"] = str(blob_path)
            entry["result_preview"] = result[:500]
            entry["result_size"] = len(result)
        else:
            entry["result"] = result
        self.write(entry)

    def write_event(self, event_type: str, **kwargs):
        self.write({"type": event_type, **kwargs})

    def close(self):
        if self._handle:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
