"""Workspace tools — file operations, shell, search.

Design borrowed from Claude Code's tool set and Vibe-Trading's workspace tools.
"""

from __future__ import annotations

import glob as glob_mod
import json
import logging
import os
import subprocess
import time
from pathlib import Path

from .base import BaseTool, ToolMeta, emit_progress

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path(os.getenv("AGENT_WORKSPACE", os.path.expanduser("~")))


def _safe_path(p: str) -> Path:
    """Resolve a path safely within the workspace root."""
    resolved = (WORKSPACE_ROOT / p).resolve()
    if not str(resolved).startswith(str(WORKSPACE_ROOT.resolve())):
        raise ValueError(f"Path outside workspace: {p}")
    return resolved


class ReadFileTool(BaseTool):
    meta = ToolMeta(name="read_file",
        description="读取文件内容。参数: path(文件路径), offset(起始行,可选), limit(行数,可选), encoding(默认utf-8)。",
        category="workspace", timeout=10)

    def execute(self, path: str = "", offset: int | str = 0, limit: int | str = 0,
                encoding: str = "utf-8") -> str:
        try:
            offset = int(offset); limit = int(limit)
        except (ValueError, TypeError):
            offset = 0; limit = 0
        try:
            p = _safe_path(path)
            if not p.exists():
                return self._error(f"File not found: {path}")
            if p.is_dir():
                items = sorted(p.iterdir())[:50]
                return self._ok({"type": "directory", "items": [
                    {"name": i.name, "is_dir": i.is_dir()} for i in items
                ]})
            content = p.read_text(encoding=encoding)
            lines = content.split("\n")
            total = len(lines)
            if limit > 0 and offset >= 0:
                lines = lines[offset:offset + limit]
                content = "\n".join(lines)
            return self._ok({
                "path": str(p), "lines_total": total,
                "offset": offset, "limit": limit if limit else total,
                "content": content[:10000],
            })
        except ValueError as exc:
            return self._error(str(exc))
        except Exception as exc:
            return self._error(str(exc))


class WriteFileTool(BaseTool):
    meta = ToolMeta(name="write_file",
        description="写入/创建文件。参数: path(文件路径), content(内容), encoding(默认utf-8)。",
        category="workspace", timeout=10, is_readonly=False)

    def execute(self, path: str = "", content: str = "", encoding: str = "utf-8") -> str:
        try:
            p = _safe_path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding=encoding)
            return self._ok({"path": str(p), "size": len(content)})
        except ValueError as exc:
            return self._error(str(exc))
        except Exception as exc:
            return self._error(str(exc))


class GlobTool(BaseTool):
    meta = ToolMeta(name="glob",
        description="文件模式匹配(类似Unix glob)。参数: pattern(如 **/*.py), path(搜索目录,默认当前目录)。",
        category="workspace", timeout=10)

    def execute(self, pattern: str = "**/*", path: str = ".") -> str:
        try:
            p = _safe_path(path)
            matches = sorted(p.glob(pattern))
            files = []
            for m in matches[:100]:
                files.append({
                    "path": str(m.relative_to(WORKSPACE_ROOT)),
                    "is_dir": m.is_dir(),
                    "size": m.stat().st_size if m.is_file() else 0,
                })
            return self._ok({"pattern": pattern, "count": len(files),
                            "total": len(matches), "files": files})
        except ValueError as exc:
            return self._error(str(exc))
        except Exception as exc:
            return self._error(str(exc))


class BashTool(BaseTool):
    meta = ToolMeta(name="bash",
        description="执行Shell命令并返回输出。参数: command(命令), timeout(超时秒数,默认30), workdir(工作目录,可选)。",
        category="workspace", timeout=60, is_readonly=False)

    def execute(self, command: str = "", timeout: int | str = 30, workdir: str = "") -> str:
        if not command.strip():
            return self._error("No command provided")
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            timeout = 30
        cwd = str(_safe_path(workdir)) if workdir else str(WORKSPACE_ROOT)
        emit_progress("running", message=f"Running: {command[:60]}...")
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=cwd, env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            return self._ok({
                "stdout": result.stdout[:5000],
                "stderr": result.stderr[:2000],
                "returncode": result.returncode,
                "cwd": cwd,
            })
        except subprocess.TimeoutExpired:
            return self._error(f"Command timed out after {timeout}s")
        except Exception as exc:
            return self._error(str(exc))
