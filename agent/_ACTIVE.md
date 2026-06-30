# ACTIVE — Main Development Track

This directory is the **primary development target**. All new features go here.

**Architecture**: Claude Code-style ReAct agent loop + tool system.

**Core files**:
- `loop.py` — ReAct loop engine (AgentLoop class)
- `state.py` — AgentLoopState (immutable) + TransitionType
- `compression.py` — 5-layer compression pipeline
- `progress.py` — HeartbeatTimer + progress events
- `trace.py` — JSONL trace recording with blob offloading
- `discovery.py` — Agent-driven data discovery

**Tools** (`tools/`):
- `base.py` — BaseTool + ToolMeta + emit_progress
- `registry.py` — ToolRegistry (auto-discovery)
- `financial.py` — 21 financial/data tools
- `workspace.py` — File/shell tools

**Key rule**: Active code must NEVER import from `quick_ask/`.
The run_analysis tool in `tools/financial.py` is the ONLY exception — it wraps the
legacy pipeline as a black-box tool, importing only at call time.
