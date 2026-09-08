# upstream/memory Branch Analysis And Integration Plan

As of 2026-07-02, the memory branch in the upstream remote is
`upstream/memory`; there is no `upstream/feat/memory` ref in the fetched remote
branch set.

## 1. Branch Topology

- Current integration baseline: `dev` at
  `3dacba4 Merge remote-tracking branch 'upstream/feat/social-media-message-alerts' into dev`.
- Memory branch: `upstream/memory` at
  `5a52d9d feat: integrate trading memory loop`.
- Divergence from current `dev`: `dev...upstream/memory` is `130 / 1`, meaning
  `dev` contains a much newer integrated line while `upstream/memory` contributes
  one unique old commit.
- Merge-base: `4e195139a9884da94b8fbb2d6498039e10b8e72c`.

Implication: this branch is not a current feature line parallel to the already
merged `feat/*` branches. It is an early memory prototype commit from before the
broker-plus, HITL, frontend, storage, and notification integrations.

## 2. What upstream/memory Tries To Implement

The branch implements a basic "trading memory loop":

- `memory/service.py`
  - Introduces `MemoryService`.
  - Reads `MEMORY_ENABLED`, `MEMORY_DB_PATH`, `MEMORY_STRATEGY_ID`, and
    `MEMORY_RECALL_LIMIT` from the environment.
  - Recalls prior records through `MemoryStore.recall_by_context(...)` or
    `MemoryStore.recall(...)`.
  - Formats recalled memories into concise advisory prompt text.
  - Persists a post-PM `MemoryRecord` by parsing PM output fields such as
    `方向`, `时间范围`, `置信度`, and `一句话结论`.

- `memory/README.md`
  - Documents the distinction between long-term trading memory and LangGraph
    checkpoint memory.
  - Defines the intended pipeline: recall before analysis, inject into
    `AgentState`, let PM read it, and remember PM decisions after completion.
  - States an important safety rule: memory is advisory only; fresh evidence
    overrides stale or conflicting memory.

- `memory/__init__.py`
  - Exports `MemoryRecord`, `MemoryService`, `MemoryStore`, `PreTradeCheck`, and
    `Reflection`.

- `agentgraph/orchestrator.py`
  - Adds `MemoryService` to the old graph constructor.
  - Injects `memory_context` into initial graph state.
  - Writes `memory_record_id` after graph invocation.

- `agentgraph/state.py`
  - Adds `memory_context`.

- `agents/PM.py`
  - Reads `memory_context` and appends it to the PM prompt.

- `pyproject.toml` and `uv.lock`
  - Add project metadata and dependency lock files relative to the old branch
    state. These are stale compared with current `dev`.

## 3. Completion Assessment

Completion level of `upstream/memory` in isolation: prototype / partial, about
45%.

What is solid:

- The product idea is clear and valuable: PM decisions should be informed by
  OWM-scored historical trading memories.
- `MemoryService` is a good boundary: it centralizes recall, formatting,
  parsing, record creation, and enable/disable logic.
- The README captures useful operating semantics, especially that memory must
  never override current market evidence.

What is incomplete:

- The integration targets the old `agentgraph` pipeline, while current `dev`
  serves analysis through `quick_ask.orchestrator.IntelliFin_Assistant` in
  `server/routes/analyze.py`.
- It has no tests for recall, remember, PM prompt injection, disabled memory, or
  strategy isolation.
- It does not integrate with the current frontend memory lab.
- It does not integrate with current settings storage, where
  `server/routes/settings.py` already has `memory_enabled`.
- Its dependency files are older than current `dev` and should not replace the
  current project metadata or lock state.

## 4. Current dev Already Contains Memory Pieces

Current `dev` is not missing memory entirely. It already has:

- `memory/models.py`, `memory/store.py`, `memory/owm.py`, and `memory/safety.py`.
- OWM-scored SQLite persistence through `MemoryStore`.
- Inline recall and remember logic in `quick_ask/orchestrator.py`.
- PM prompt injection through `quick_ask/agents/PM.py`.
- `recall_memory` tools in both `agents/utils/agent_tools.py` and
  `quick_ask/agents/utils/agent_tools.py`.
- API endpoints in `server/routes/memory.py`.
- A frontend memory lab at `frontend/app/memory-lab/page.tsx`.
- A settings default `memory_enabled: True` in `server/routes/settings.py`.

So the branch should be treated as a source of missing service abstraction and
documentation, not as the only implementation of memory.

## 5. Gaps In Current dev

Current `dev` has a working-looking memory path, but the module boundary is not
yet clean enough for the integrated baseline:

- `quick_ask/orchestrator.py` directly constructs `MemoryStore("data/memory.db")`
  in both `run()` and `stream()` instead of using a shared service boundary.
- `quick_ask/orchestrator.py` accepts `strategy_id`, but the initial state does
  not include `strategy_id`; the remember node therefore falls back to
  `"default"` and can store memories under the wrong strategy.
- `server/routes/analyze.py` accepts `request.strategy_id`, but does not pass it
  into `assistant.stream(...)`, so strategy-scoped recall is effectively lost in
  the normal API path.
- `server/routes/settings.py` exposes `memory_enabled`, but the analysis path
  does not currently honor that switch.
- The inline remember node uses `state.get("confidence", 0.5)`, but PM currently
  returns confidence inside `PM_report`; this loses the parsed confidence that
  `server/routes/analyze.py` already knows how to extract.
- The final API payload does not expose `memory_record_id`, so it is hard to
  trace a user-visible decision back to a persisted memory.
- `memory/__init__.py` is empty, so import ergonomics are weaker than the
  upstream prototype.

## 6. Merge Recommendation

Do not directly run `git merge upstream/memory` into `dev`.

Reasons:

- The branch has only one useful unique commit but diverged from a much older
  baseline.
- Direct merge would touch stale `agentgraph/orchestrator.py`,
  `agentgraph/state.py`, `agents/PM.py`, `pyproject.toml`, and `uv.lock` in ways
  that are not aligned with current `dev`.
- Current `dev` already contains a broader memory/backend/frontend surface than
  the branch.
- The valuable part is the service boundary and README semantics, which should
  be selectively ported.

Recommended strategy: selective import / reimplementation on top of `dev`.

## 7. Integration Plan

### Phase M1: Add MemoryService On dev

Create `memory/service.py` based on the upstream prototype, adapted to current
models and store:

- Keep `MemoryService.recall_context(...)` for prompt-ready text.
- Add or retain a record-returning method such as `recall_records(...)` so the
  existing PM formatter can keep receiving `MemoryRecord` objects if preferred.
- Keep `remember_decision(...)`, but adapt it to current `quick_ask` state and
  result fields.
- Preserve `parse_pm_report(...)` logic for `方向`, `时间范围`, `置信度`, and
  `一句话结论`.
- Store `strategy_id`, `session_id`, `ticker`, action, target position, date,
  current position, direction, time range, confidence, and PM report excerpt.
- Use `MEMORY_DB_PATH` as the DB default but continue to work with
  `data/memory.db`.
- Implement `memory_enabled(...)` so env settings and server settings can share
  one decision point.

### Phase M2: Export The Memory API

Update `memory/__init__.py` to export:

- `MemoryRecord`
- `MemoryService`
- `MemoryStore`
- `PreTradeCheck`
- `Reflection`

Bring over `memory/README.md`, edited to match current `dev` paths:

- Current runtime path is `server/routes/analyze.py` ->
  `quick_ask.orchestrator.IntelliFin_Assistant`.
- UI path is `frontend/app/memory-lab/page.tsx`.
- Store path is `data/memory.db`.

### Phase M3: Refactor quick_ask Memory Flow

Replace inline memory operations in `quick_ask/orchestrator.py` with
`MemoryService`:

- In `run()` and `stream()`, pass `strategy_id` into `initial_state`.
- Respect `memory_enabled`.
- Recall via service before graph execution.
- Persist through service after `PM_agent`.
- Return or propagate `memory_record_id` from the remember node when possible.
- Keep failures non-fatal: memory failure should log and continue analysis.

### Phase M4: Fix Server Integration

Update `server/routes/analyze.py`:

- Pass `request.strategy_id` into `assistant.stream(...)`.
- Optionally pass `request.account_id` and `decision_id` into quick_ask state if
  the memory trade record should include them.
- Respect settings `memory_enabled` from `_load_settings()`.
- Include `memory_record_id` in the final result payload if the graph returns it.
- Save memory metadata in analysis history for traceability.

### Phase M5: Tighten PM Prompt Semantics

Update `quick_ask/agents/PM.py`:

- Keep the current OWM-formatted history section.
- Add the upstream safety rule in system prompt form: historical memory is
  advisory only, and current evidence overrides stale or conflicting memory.
- Avoid letting memory become a hidden primary signal; the PM report should still
  cite current Market/Fundamental/News/Risk inputs.

### Phase M6: Tests

Add focused tests before treating this as integrated:

- `test/memory/test_service.py`
  - recall returns empty advisory text when no records exist.
  - recall uses strategy-scoped records.
  - remember parses PM report confidence/timeframe/direction.
  - disabled memory does not recall or persist.

- `test/quick_ask/test_memory_integration.py`
  - `strategy_id` is present in initial graph state.
  - remember uses the requested strategy instead of `"default"`.
  - memory failures are logged and non-fatal.

- `test/server/test_analyze_memory.py`
  - `/api/analyze` passes `request.strategy_id` into `assistant.stream(...)`.
  - final result includes memory metadata when available.

## 8. Expected Adaptation Work After Selective Import

After the selected files are ported, the main compatibility work is not schema
heavy; it is contract cleanup:

- Align memory configuration across env variables and `server/routes/settings.py`.
- Decide whether PM consumes `relevant_memories: list[MemoryRecord]` or
  `memory_context: str`; support both during transition if needed.
- Preserve strategy/account/session/decision identifiers across analysis,
  HITL, notification, history, and memory.
- Keep memory advisory and auditable: user-facing result/history should expose
  when a memory record was written.
- Avoid touching broker-plus execution modules unless a later phase explicitly
  routes memory into execution or pre-trade safety gates.

## 9. Stop Condition For This Integration

Treat the memory branch as integrated when:

- No direct merge from `upstream/memory` is needed.
- `memory/service.py`, `memory/__init__.py`, and memory docs are present on
  `dev`.
- Normal `/api/analyze` requests pass strategy identity into quick_ask memory
  recall and persistence.
- `memory_enabled=false` disables recall and persistence.
- PM sees memory as advisory context only.
- Tests cover service behavior, strategy isolation, server handoff, and
  non-fatal failure behavior.
