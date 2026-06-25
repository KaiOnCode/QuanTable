"""Agent Terminal — SSE streaming chat endpoint.

POST /api/agent/chat — SSE streaming ReAct loop execution.
GET  /api/agent/sessions — list recent sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(tags=["agent"])
logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "agent-runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(None, description="Session ID for continuing conversation")
    history: list[dict] | None = Field(None, description="Previous messages for context")
    include_shell: bool = Field(False, description="Include bash/shell tools")


@router.post("/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """SSE streaming agent chat. Executes a ReAct loop with all available tools."""

    async def event_stream():
        queue: Queue = Queue()
        stop_event = __import__("threading").Event()
        session_id = req.session_id or __import__("uuid").uuid4().hex[:12]
        run_dir = RUNS_DIR / session_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = time.time()

        # Load existing session history for multi-turn
        history = req.history or []
        if req.session_id:
            session_path = run_dir / "session.json"
            if session_path.exists():
                try:
                    old = json.loads(session_path.read_text())
                    history = _reconstruct_history(old.get("messages", []))
                except Exception:
                    pass

        def on_event(evt_type: str, payload: dict):
            queue.put((evt_type, payload))

        def _worker():
            try:
                from agentgraph.react_loop import AgentLoop, AgentConfig
                loop = AgentLoop(AgentConfig(include_shell_tools=req.include_shell))
                result = loop.run(
                    user_message=req.message,
                    session_id=session_id,
                    history=history,
                    on_event=on_event,
                    run_dir=run_dir,
                )
                queue.put(("_done", result))
            except Exception as exc:
                queue.put(("_error", str(exc)))

        Thread(target=_worker, daemon=True).start()
        loop = asyncio.get_event_loop()

        while True:
            try:
                evt_type, payload = await loop.run_in_executor(
                    None, lambda: queue.get(timeout=300))
            except Empty:
                yield _sse("error", {"message": "Timeout"})
                break

            if evt_type == "_done":
                # Save session.json for history replay
                try:
                    prev = {}
                    sp = run_dir / "session.json"
                    if sp.exists():
                        try:
                            prev = json.loads(sp.read_text())
                        except Exception:
                            pass
                    full_messages = _compact_messages(payload.get("messages", []))
                    session_data = {
                        "session_id": session_id,
                        "created_at": prev.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "first_message": prev.get("first_message") or req.message[:200],
                        "tool_count": (prev.get("tool_count", 0) + payload.get("tool_count", 0)),
                        "iterations": max(prev.get("iterations", 0), payload.get("iterations", 0)),
                        "elapsed_s": round((prev.get("elapsed_s", 0) + payload.get("elapsed_s", 0)), 1),
                        "total_turns": prev.get("total_turns", 1) + 1 if prev else 1,
                        "messages": (prev.get("messages") or []) if prev else [],
                    }
                    # Append new messages (skip system prompt = index 0)
                    for m in full_messages[1:]:
                        session_data["messages"].append(m)
                    sp.write_text(json.dumps(session_data, ensure_ascii=False, indent=2))
                except Exception as exc:
                    logger.warning("Failed to save session: %s", exc)

                yield _sse("done", {
                    "ok": True, "session_id": session_id,
                    "iterations": payload.get("iterations", 0),
                    "tool_count": payload.get("tool_count", 0),
                    "elapsed_s": payload.get("elapsed_s", 0),
                })
                break
            if evt_type == "_error":
                yield _sse("error", {"message": str(payload)[:500]})
                break

            yield _sse(evt_type, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/agent/sessions")
async def list_sessions(limit: int = Query(20, ge=1, le=100)):
    """List recent agent sessions."""
    items = []
    for d in sorted(RUNS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        if d.is_dir():
            sp = d / "session.json"
            data = {}
            if sp.exists():
                try:
                    data = json.loads(sp.read_text())
                except Exception:
                    pass
            items.append({
                "session_id": d.name,
                "modified": d.stat().st_mtime,
                "first_message": data.get("first_message", "")[:100],
                "tool_count": data.get("tool_count", 0),
                "iterations": data.get("iterations", 0),
                "elapsed_s": data.get("elapsed_s", 0),
                "total_turns": data.get("total_turns", 1),
            })
    return {"sessions": items, "total": len(items)}


@router.get("/agent/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a session's summary and trace."""
    d = RUNS_DIR / session_id
    if not d.is_dir():
        raise HTTPException(404, "Session not found")

    data = {}
    sp = d / "session.json"
    if sp.exists():
        try:
            data = json.loads(sp.read_text())
        except Exception:
            pass
    return data


@router.delete("/agent/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all its data."""
    import shutil
    d = RUNS_DIR / session_id
    if not d.is_dir():
        raise HTTPException(404, "Session not found")
    shutil.rmtree(d)
    return {"ok": True}


# ── Helpers ──────────────────────────────────────────────────


def _compact_messages(messages: list[dict]) -> list[dict]:
    """Compress messages for storage. Large tool results truncated to 200 chars."""
    compacted = []
    for m in messages:
        entry: dict = {"role": m.get("role", "?")}
        if m.get("content"):
            entry["content"] = str(m["content"])
        if m.get("tool_calls"):
            entry["tool_calls"] = [
                {"name": tc.get("name", tc.get("function", {}).get("name", "?")),
                 "args": tc.get("args", tc.get("function", {}).get("arguments", {}))}
                for tc in m["tool_calls"]
            ]
        if m.get("name"):
            entry["name"] = m["name"]
        if m.get("tool_call_id"):
            entry["tool_call_id"] = m["tool_call_id"]
        if m.get("role") == "tool" and m.get("content"):
            content = str(m["content"])
            entry["preview"] = content[:500]  # Enough for chart data
            if len(content) > 500:
                entry["preview"] += "..."
        # Preserve chart data for historical session display
        if m.get("chart_data"):
            entry["chart_data"] = m["chart_data"]
        compacted.append(entry)
    return compacted


def _reconstruct_history(messages: list[dict]) -> list[dict]:
    """Reconstruct message list for LLM continuation. Only keeps user messages
    and final assistant answers — strips tool calls/results to avoid DeepSeek
    validation errors on old tool call IDs."""
    history = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            history.append({"role": "user", "content": content})
        elif role == "assistant" and content:
            # Only keep final answers (no tool_calls) — strip intermediate thinking
            if not m.get("tool_calls"):
                history.append({"role": "assistant", "content": content})
    # Remove the last assistant message (the final answer from last turn)
    # so the LLM has context but re-generates the answer
    if history and history[-1]["role"] == "assistant":
        history.pop()
    return history
