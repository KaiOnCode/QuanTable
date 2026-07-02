# Memory Module

The memory module provides long-term trading memory for Agentic-Quant. It is
separate from LangGraph checkpoint memory: checkpoints keep one graph run alive,
while this module stores reusable trading experience across runs.

## Components

- `models.py` defines `MemoryRecord`, `Reflection`, and `PreTradeCheck`.
- `owm.py` computes Outcome-Weighted Memory scores.
- `store.py` persists memories in SQLite and recalls them by ticker, strategy,
  score, or current context.
- `safety.py` provides optional pre-trade safety checks. The current selective
  integration does not wire memory into broker pre-trade execution.
- `service.py` is the runtime boundary used by `quick_ask.orchestrator`.

## Runtime Path

Current analysis requests flow through:

1. `server/routes/analyze.py`
2. `quick_ask.orchestrator.IntelliFin_Assistant`
3. `quick_ask/agents/PM.py`
4. `data/memory.db`

The frontend memory inspection surface is `frontend/app/memory-lab/page.tsx`.

## Pipeline Semantics

`IntelliFin_Assistant.run()` and `IntelliFin_Assistant.stream()` use
`MemoryService` to recall relevant strategy-scoped records before PM decides.
The PM prompt receives historical memory as advisory context. After PM emits a
decision, `MemoryService.remember_decision()` writes a new `MemoryRecord` and
the graph propagates `memory_record_id` where available.

Memory is advisory only. Current Market, Fundamental, News, and Risk evidence
overrides stale or conflicting memory.

## Configuration

```bash
MEMORY_ENABLED=false
MEMORY_DB_PATH=data/memory.db
MEMORY_STRATEGY_ID=default
MEMORY_RECALL_LIMIT=5
```

Server settings also expose `memory_enabled`; an explicit `false` setting or a
false-like `MEMORY_ENABLED` value disables recall and persistence.

## Minimal Usage

```python
from memory import MemoryService

service = MemoryService(strategy_id="default")
records = service.recall_records("AAPL")
context = service.recall_context("AAPL")
memory_id = service.remember_decision(langgraph_state)
```
