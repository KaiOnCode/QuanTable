"""Agent Terminal — SSE streaming chat endpoint.

POST /api/agent/chat — SSE streaming ReAct loop execution.
GET  /api/agent/sessions — list recent sessions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Path as FastAPIPath, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from agent.backtest_jobs import (
    BacktestJobAcceptedResponse,
    BacktestJobResponse,
    BacktestReplayUnavailableError,
    BacktestJobService,
    BacktestRequest,
    default_backtest_job_service,
)
from agent.backtest_policy import StrategyEligibilityError
from agent.scanner_adapter import ScannerCompilationError, ScannerCompilationService
from server.routes.scanner import ScanRunError, ScanRunResponse, _response_from_record
from storage import get_store

logger = logging.getLogger(__name__)

RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "agent-runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
_backtest_job_service: BacktestJobService | None = None
_backtest_job_service_lock = Lock()
_scanner_compilation_service: ScannerCompilationService | None = None
BacktestJobId = Annotated[str, FastAPIPath(pattern=r"^[0-9a-f]{32}$")]


@asynccontextmanager
async def agent_lifespan(_app: object) -> AsyncIterator[None]:
    try:
        yield
    finally:
        shutdown_backtest_job_service()


router = APIRouter(tags=["agent"], lifespan=agent_lifespan)


def get_backtest_job_service() -> BacktestJobService:
    global _backtest_job_service
    with _backtest_job_service_lock:
        if _backtest_job_service is None:
            _backtest_job_service = default_backtest_job_service(get_store())
        return _backtest_job_service


def shutdown_backtest_job_service() -> None:
    global _backtest_job_service
    with _backtest_job_service_lock:
        service = _backtest_job_service
        _backtest_job_service = None
    if service is not None:
        service.shutdown()


def get_scanner_compilation_service() -> ScannerCompilationService:
    global _scanner_compilation_service
    if _scanner_compilation_service is None:
        _scanner_compilation_service = ScannerCompilationService(
            llm_available=bool(os.getenv("OPENAI_API_KEY"))
        )
    return _scanner_compilation_service


def _sse(event: str, data: dict) -> str:
    return (
        f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    )


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(
        None, description="Session ID for continuing conversation"
    )
    history: list[dict] | None = Field(
        None, description="Previous messages for context"
    )
    include_shell: bool = Field(False, description="Include bash/shell tools")


class AgentScannerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["agent", "belief"]
    query: str | None = Field(default=None, min_length=1, max_length=2000)
    strategy_id: str | None = Field(default=None, min_length=1, max_length=128)
    belief_text: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_mode_source(self) -> AgentScannerRequest:
        match self.mode:
            case "agent":
                if self.query is None:
                    raise ValueError("agent scanner requires query")
            case "belief":
                if self.strategy_id is None or self.belief_text is None:
                    raise ValueError(
                        "belief scanner requires strategy_id and belief_text"
                    )
            case unreachable:
                from typing import assert_never

                assert_never(unreachable)
        return self


@router.post("/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """SSE streaming agent chat. Executes a ReAct loop with all available tools."""

    async def event_stream():
        queue: Queue = Queue()
        session_id = req.session_id or __import__("uuid").uuid4().hex[:12]
        run_dir = RUNS_DIR / session_id
        run_dir.mkdir(parents=True, exist_ok=True)

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
                from agent.loop import AgentLoop, AgentConfig

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
                    None, lambda: queue.get(timeout=300)
                )
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
                        "created_at": prev.get("created_at")
                        or time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "first_message": prev.get("first_message") or req.message[:200],
                        "tool_count": (
                            prev.get("tool_count", 0) + payload.get("tool_count", 0)
                        ),
                        "iterations": max(
                            prev.get("iterations", 0), payload.get("iterations", 0)
                        ),
                        "elapsed_s": round(
                            (prev.get("elapsed_s", 0) + payload.get("elapsed_s", 0)), 1
                        ),
                        "total_turns": prev.get("total_turns", 1) + 1 if prev else 1,
                        "messages": (prev.get("messages") or []) if prev else [],
                    }
                    # Append new messages, keep only last 30
                    for m in full_messages[1:]:
                        session_data["messages"].append(m)
                    if len(session_data["messages"]) > 30:
                        session_data["messages"] = session_data["messages"][-30:]
                    sp.write_text(
                        json.dumps(session_data, ensure_ascii=False, indent=2)
                    )
                except Exception as exc:
                    logger.warning("Failed to save session: %s", exc)

                yield _sse(
                    "done",
                    {
                        "ok": True,
                        "session_id": session_id,
                        "iterations": payload.get("iterations", 0),
                        "tool_count": payload.get("tool_count", 0),
                        "elapsed_s": payload.get("elapsed_s", 0),
                    },
                )
                break
            if evt_type == "_error":
                yield _sse("error", {"message": str(payload)[:500]})
                break

            yield _sse(evt_type, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/agent/sessions")
async def list_sessions(limit: int = Query(50, ge=1, le=500)):
    """List recent agent sessions. Only reads file stats, not full JSON."""
    import os as _os

    items = []
    # Collect (mtime, dirname) tuples without reading JSON
    entries = []
    for d in RUNS_DIR.iterdir():
        if d.is_dir():
            try:
                st = d.stat()
                entries.append((st.st_mtime, d.name))
            except OSError:
                pass
    entries.sort(reverse=True)

    for mtime, name in entries[:limit]:
        sp = RUNS_DIR / name / "session.json"
        data = {}
        if sp.exists():
            try:
                data = json.loads(sp.read_text())
            except Exception:
                pass
        items.append({
            "session_id": name,
            "modified": mtime,
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


async def _parse_backtest_request(
    payload: object = Body(...),
) -> BacktestRequest:
    try:
        return BacktestRequest.model_validate(payload)
    except ValidationError as exc:
        detail = [
            {
                key: value
                for key, value in error.items()
                if key not in {"ctx", "input", "url"}
            }
            for error in exc.errors()
        ]
        raise HTTPException(422, detail=detail) from exc


@router.post(
    "/agent/backtest",
    status_code=202,
    response_model=BacktestJobAcceptedResponse,
)
async def create_backtest(
    request: Annotated[BacktestRequest, Depends(_parse_backtest_request)],
) -> BacktestJobAcceptedResponse:
    service = get_backtest_job_service()
    try:
        return service.create(request)
    except StrategyEligibilityError as exc:
        raise HTTPException(
            exc.http_status, detail={"code": exc.code, "message": exc.message}
        ) from exc


@router.get("/agent/backtest/{backtest_id}", response_model=BacktestJobResponse)
async def get_backtest(backtest_id: BacktestJobId) -> BacktestJobResponse:
    job = get_backtest_job_service().get(backtest_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    return job


@router.post(
    "/agent/backtest/{backtest_id}/replay",
    status_code=202,
    response_model=BacktestJobAcceptedResponse,
)
async def replay_backtest(backtest_id: BacktestJobId) -> BacktestJobAcceptedResponse:
    service = get_backtest_job_service()
    if service.get(backtest_id) is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    try:
        return service.create_replay(backtest_id)
    except BacktestReplayUnavailableError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "replay_unavailable",
                "message": "Frozen backtest replay is unavailable",
            },
        ) from exc


@router.get("/agent/backtest/{backtest_id}/trades.csv")
async def download_backtest_trades(backtest_id: BacktestJobId) -> Response:
    service = get_backtest_job_service()
    job = service.get(backtest_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    if job.status != "completed":
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    csv_content = service.trades_csv(backtest_id)
    if csv_content is None:
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="backtest-{backtest_id}-trades.csv"'
        },
    )


@router.get("/agent/backtest/{backtest_id}/closed-trades.csv")
async def download_backtest_closed_trades(backtest_id: BacktestJobId) -> Response:
    service = get_backtest_job_service()
    job = service.get(backtest_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    if job.status != "completed":
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    csv_content = service.closed_trades_csv(backtest_id)
    if csv_content is None:
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="backtest-{backtest_id}-closed-trades.csv"'
            )
        },
    )


@router.get("/agent/backtest/{backtest_id}/decisions.csv")
async def download_backtest_decisions_csv(backtest_id: BacktestJobId) -> Response:
    service = get_backtest_job_service()
    job = service.get(backtest_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    if job.status != "completed":
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    csv_content = service.decisions_csv(backtest_id)
    if csv_content is None:
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="backtest-{backtest_id}-decisions.csv"'
        },
    )


@router.get("/agent/backtest/{backtest_id}/decisions.json")
async def download_backtest_decisions_json(backtest_id: BacktestJobId) -> Response:
    service = get_backtest_job_service()
    job = service.get(backtest_id)
    if job is None:
        raise HTTPException(
            404,
            detail={"code": "backtest_not_found", "message": "Backtest not found"},
        )
    if job.status != "completed":
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    json_content = service.decisions_json(backtest_id)
    if json_content is None:
        raise HTTPException(
            409,
            detail={
                "code": "export_unavailable",
                "message": "Backtest export is unavailable",
            },
        )
    return Response(
        content=json_content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="backtest-{backtest_id}-decisions.json"'
        },
    )


@router.post("/agent/scanner", status_code=201, response_model=ScanRunResponse)
async def create_agent_scanner(request: AgentScannerRequest) -> ScanRunResponse:
    store = get_store()
    belief_weight: float | None = None
    match request.mode:
        case "agent":
            assert request.query is not None
            source = {"mode": "agent", "query": request.query}
            prompt = request.query
        case "belief":
            assert request.strategy_id is not None
            assert request.belief_text is not None
            strategy = store.get_strategy(request.strategy_id)
            if strategy is None:
                raise HTTPException(404, "Strategy not found")
            beliefs = strategy.get("beliefs")
            if not isinstance(beliefs, list) or request.belief_text not in beliefs:
                raise HTTPException(422, "Belief does not belong to strategy")
            weights = strategy.get("belief_weights")
            raw_weight = (
                weights.get(request.belief_text) if isinstance(weights, dict) else None
            )
            belief_weight = (
                float(raw_weight) if isinstance(raw_weight, int | float) else 1.0
            )
            source = {
                "mode": "belief",
                "strategy_id": request.strategy_id,
                "belief_text": request.belief_text,
                "belief_weight": belief_weight,
            }
            prompt = (
                f"Compile a tracked scanner for belief: {request.belief_text}. "
                f"Belief weight: {belief_weight}."
            )
        case unreachable:
            from typing import assert_never

            assert_never(unreachable)
    run_id = uuid4().hex
    store.create_scan_run(
        run_id,
        json.dumps(source, ensure_ascii=False),
        mode=request.mode,
        strategy_id=request.strategy_id,
    )
    compiler = get_scanner_compilation_service()
    try:
        compiled = compiler.compile(prompt, session_id=run_id)
    except ScannerCompilationError as error:
        code: Literal["invalid_tool_output", "llm_unavailable"] = (
            "llm_unavailable" if not compiler.can_compile else "invalid_tool_output"
        )
        failure = ScanRunError(code=code, message=str(error))
        store.fail_scan_run(run_id, failure.model_dump_json())
        raise HTTPException(422, "Scanner compilation failed") from error
    completed = store.complete_scan_run(
        run_id,
        json.dumps(
            [condition.model_dump(mode="json") for condition in compiled.conditions],
            ensure_ascii=False,
        ),
        compiled.result.model_dump_json(),
    )
    if not completed:
        raise RuntimeError("scanner run did not complete")
    run = store.get_scan_run(run_id)
    if run is None:
        raise RuntimeError("scanner run disappeared after completion")
    return _response_from_record(run)


# ── Skills ────────────────────────────────────────────────────


class SkillCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Skill name (lowercase, hyphens)")
    content: str = Field(
        ..., min_length=1, description="Full SKILL.md content with YAML frontmatter"
    )
    category: str = Field("user", description="Skill category")


@router.get("/agent/skills")
async def list_skills(category: str | None = None, search: str | None = None):
    """List all skills with optional category filter and keyword search."""
    from skills.loader import get_loader, reset_loader

    reset_loader()
    loader = get_loader()
    loader.discover()

    skills = list(loader.skills.values())
    if category:
        skills = [s for s in skills if s.category == category]
    if search:
        q = search.lower()
        skills = [
            s
            for s in skills
            if q in s.name.lower()
            or q in s.description.lower()
            or q in s.prompt_template.lower()
        ]

    skills.sort(key=lambda s: (s.category, s.name))

    cat_counts: dict[str, int] = {}
    for s in loader.skills.values():
        cat_counts[s.category] = cat_counts.get(s.category, 0) + 1

    return {
        "total": len(loader.skills),
        "filtered": len(skills),
        "categories": cat_counts,
        "skills": [
            {
                "name": s.name,
                "category": s.category,
                "description": s.description[:200],
                "version": s.version,
                "is_builtin": s.is_builtin,
                "tools": s.tools,
            }
            for s in skills
        ],
    }


@router.get("/agent/skills/{name}")
async def get_skill(name: str):
    """Get full content of a skill by name."""
    from skills.loader import get_loader, reset_loader

    reset_loader()
    loader = get_loader()
    loader.discover()

    skill = loader.get(name)
    if not skill:
        for s in loader.skills.values():
            if name.lower() in s.name.lower():
                skill = s
                break
    if not skill:
        raise HTTPException(404, f"Skill '{name}' not found")

    return {
        "name": skill.name,
        "category": skill.category,
        "description": skill.description,
        "version": skill.version,
        "is_builtin": skill.is_builtin,
        "tools": skill.tools,
        "model": skill.model,
        "temperature": skill.temperature,
        "content": skill.prompt_template,
        "file_path": skill.file_path,
    }


@router.post("/agent/skills")
async def create_skill(req: SkillCreateRequest):
    """Create or update a user skill."""
    import re
    from pathlib import Path

    slug = re.sub(r"[^a-z0-9-]", "-", req.name.lower().strip())[:60]
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    user_dir = skills_dir / "user" / slug
    user_dir.mkdir(parents=True, exist_ok=True)
    skill_path = user_dir / "SKILL.md"

    content = req.content
    if not content.strip().startswith("---"):
        content = (
            f"---\nname: {slug}\n"
            f"description: User-created skill\n"
            f"category: {req.category}\n"
            f'version: "1.0"\n'
            f"---\n\n{content}"
        )

    try:
        import yaml

        parts = content.split("---")
        if len(parts) >= 3:
            yaml.safe_load(parts[1])
    except Exception as e:
        raise HTTPException(400, f"Invalid YAML frontmatter: {e}")

    skill_path.write_text(content, encoding="utf-8")

    from skills.loader import reset_loader

    reset_loader()

    return {"ok": True, "name": slug, "path": str(skill_path)}


@router.delete("/agent/skills/{name}")
async def delete_skill(name: str):
    """Delete a user skill (bundled skills are protected)."""
    import re
    import shutil
    from pathlib import Path

    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())[:60]
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    user_skill_dir = skills_dir / "user" / slug

    try:
        user_skill_dir.resolve().relative_to((skills_dir / "user").resolve())
    except ValueError:
        raise HTTPException(403, "Cannot delete skills outside user directory")

    if not user_skill_dir.exists():
        raise HTTPException(404, f"User skill '{slug}' not found")

    shutil.rmtree(user_skill_dir)

    from skills.loader import reset_loader

    reset_loader()

    return {"ok": True, "deleted": slug}


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
                {
                    "name": tc.get("name", tc.get("function", {}).get("name", "?")),
                    "args": tc.get("args", tc.get("function", {}).get("arguments", {})),
                }
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
