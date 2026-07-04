# Dev Branch Acceptance Cases

**As of:** 2026-07-04 on `dev`.

This document describes how to accept the integrated `dev` branch after the
broker-plus, frontend/backend, HITL, notification, and memory work have been
combined.

The goal is not to prove that every future product idea is complete. The goal is
to prove that the integrated baseline is coherent enough to become the next
development branch.

## 0. Current Verification Baseline

Commands run during this acceptance-design pass:

```bash
git status --short --branch
uv run pytest test -q
uv run ruff check .
uv run ruff format --check .
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
cd frontend && npm run lint
cd frontend && npm run build
```

Observed result:

- `git status --short --branch`: clean `dev...origin/dev`.
- `uv run pytest test -q`: `113 passed, 1 skipped, 1 warning`.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: `142 files already formatted`.
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`: `0 errors`.
- `frontend npm run lint`: exit code `0`, but with 100 warnings.
- `frontend npm run build`: passed outside the sandbox. Inside the sandbox it
  failed because Turbopack attempted a port-binding operation that the sandbox
  denied.

Interpretation:

- The Python/backend/broker automated baseline is green.
- The frontend production build is green when run in a normal local environment.
- Frontend lint warnings are acceptance debt, not a hard blocker yet.

## 1. Acceptance Layers

Use three layers:

- **P0 automated baseline:** the branch must pass core tests, type checks,
  formatting, and frontend build.
- **P1 local product smoke:** run backend + frontend locally and exercise the
  primary user workflows.
- **P2 integration semantics:** inspect whether the major modules preserve their
  intended boundaries after being combined.

Do not treat mocked or placeholder UI as full product proof. For example,
`frontend/app/backtest/page.tsx` currently displays mock result data; real
broker/backtest acceptance should be based on `broker/` and `agentgraph/`
tests or a later API adapter.

## 2. Case A: Automated Quality Gate

### Goal

Confirm that the integrated branch is mechanically healthy.

### Execute

```bash
uv run pytest test -q
uv run ruff check .
uv run ruff format --check .
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
cd frontend && npm run lint
cd frontend && npm run build
```

### Pass Criteria

- Python tests pass.
- Ruff passes.
- Basedpyright reports no new unbaselined issues.
- Frontend lint exits `0`.
- Frontend production build succeeds in a normal local environment.

### Watch Items

- `frontend npm run lint` currently has warnings. Track these as frontend
  hygiene debt.
- If `npm run build` fails only in the sandbox with a Turbopack port-binding
  error, rerun outside the sandbox before classifying it as a product regression.

## 3. Case B: Quick Ask Analysis, Memory, HITL, And Notification Spine

### Goal

Validate the main integrated user path:

`frontend quick-ask` -> `POST /api/analyze` -> `quick_ask` agents ->
`MemoryService` -> HITL rule evaluation -> analysis notification -> history.

### Execute

Start backend and frontend:

```bash
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
cd frontend && npm run dev
```

Open:

```text
http://localhost:3000/quick-ask
```

Run a standard analysis for a liquid ticker such as `AAPL`.

For API-level identity verification, prefer a direct request so `strategy_id`,
`account_id`, and `decision_id` are explicit:

```bash
curl -N http://127.0.0.1:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "ticker": "AAPL",
    "strategy_id": "acceptance-strategy",
    "account_id": "acceptance-account",
    "decision_id": "acceptance-decision-001",
    "current_position_pct": 0,
    "mode": "standard"
  }'
```

### Pass Criteria

- SSE emits a `progress` event with `agent=system`.
- PM produces a final result event.
- Result contains `session_id`, `strategy_id`, `account_id`, `decision_id`,
  `memory_enabled`, and, when memory persistence is enabled and PM completed,
  `memory_record_id`.
- If HITL rules trigger, result contains `approval_required=true`,
  `approval_status=pending`, and an `approval_id`.
- Analysis history endpoint can retrieve the session:

```text
GET /api/analyze/history
GET /api/analyze/history/{session_id}
```

### Existing Automated Coverage

- `test/server/test_analyze_memory.py`
- `test/server/test_analyze_hitl.py`
- `test/quick_ask/test_memory_integration.py`

### Watch Items

- The Quick Ask UI currently does not expose a strategy/account selector; use
  direct API requests for strategy/account acceptance.
- `SSEResultEvent` in `frontend/lib/types/models.ts` should be checked against
  the backend result payload if the UI starts displaying `memory_enabled` or
  `memory_record_id`.

## 4. Case C: Memory Isolation And Disable Switch

### Goal

Verify that memory is strategy-scoped, advisory, auditable, and disable-able.

### Execute

Use a temporary settings file and memory DB to avoid contaminating local state:

```bash
AGENTIC_QUANT_SETTINGS_PATH=/tmp/agentic-quant-settings.json \
MEMORY_DB_PATH=/tmp/agentic-quant-memory.db \
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Run two API-level analyses using different `strategy_id` values.

Then inspect:

```text
GET /api/strategies/{strategy_id}/memory
GET /api/strategies/{strategy_id}/memory?ticker=AAPL
```

Disable memory:

```text
PUT /api/settings
{"memory_enabled": false}
```

Run another analysis and confirm `memory_enabled=false` in the result.

### Pass Criteria

- Strategy A does not see Strategy B memories.
- Records contain `session_id`, `strategy_id`, `account_id`, and `decision_id`
  inside the persisted trade record when those inputs are present.
- PM prompt semantics keep memory advisory: current Market/Fundamental/News/Risk
  evidence must override stale memory.
- With memory disabled, no new memory is persisted.

### Existing Automated Coverage

- `test/memory/test_service.py`
- `test/quick_ask/test_memory_integration.py`
- `test/server/test_analyze_memory.py`

### Watch Items

- `memoryApi.search(...)`, reflection detail, and reflection generation client
  helpers exist in frontend API code, but the corresponding backend endpoints
  are not currently complete. Do not include those in first-pass acceptance.

## 5. Case D: HITL Approval Lifecycle

### Goal

Validate that risky PM decisions produce pending approvals and that approval
actions update state without directly executing broker orders from the approval
route.

### Execute

Use either a deterministic test path or a live analysis that triggers HITL
rules. The deterministic proof is:

```bash
uv run pytest test/hitl test/server/test_analyze_hitl.py -q
```

For manual UI smoke:

1. Run an analysis that produces a large target position or low confidence.
2. Open `http://localhost:3000/approvals`.
3. Confirm the pending approval appears.
4. Approve, reject, and modify separate sample approvals.

### Pass Criteria

- Pending approval carries `strategy_id`, `account_id`, `session_id`, and
  `decision_id`.
- Triggered rules are visible and persisted.
- Approve/reject/modify endpoints update status.
- Approval notification path is invoked as a side effect.
- Approval routes do not directly submit broker orders.

### Existing Automated Coverage

- `test/hitl/test_hitl_flow.py`
- `test/server/test_analyze_hitl.py`
- `test/agentgraph/test_execution_node.py`

### Watch Items

- Full "approve then resume broker execution" is still an architecture-sensitive
  workflow. Do not claim it is fully productized unless a dedicated resume
  adapter/API is verified.

## 6. Case E: Broker Execution And Backtest Contract

### Goal

Validate that the broker-plus execution substrate survived the dev merge and
still enforces identity, approval, event, ledger, and backtest contracts.

### Execute

```bash
uv run pytest test/broker test/agentgraph -q
```

Then inspect key outputs through tests or small scripts:

- `ExecutionReportView` contains `strategy_id`, `account_id`, `session_id`, and
  `decision_id`.
- `execution_enabled=false` produces a skipped execution report.
- `approval_status=pending` produces no broker order.
- `approval_status=rejected` or `timed_out` produces no ledger trade.
- `approval_status=modified` uses `modified_target_pct`.
- `BacktestRunner` passes `as_of` into the agent and records daily snapshots.

### Pass Criteria

- Execution node never places orders while approval is pending.
- Broker events include identity fields.
- Ledger/account queries remain account-aware.
- Backtest results include config, trades, portfolio, and metrics.

### Existing Automated Coverage

- `test/broker/test_engine.py`
- `test/broker/test_ledger.py`
- `test/broker/test_backtest_runner.py`
- `test/broker/test_views.py`
- `test/agentgraph/test_execution_node.py`
- `test/agentgraph/test_orchestrator.py`

### Watch Items

- `frontend/app/backtest/page.tsx` is currently a mock UI. Use Python broker
  tests for real backtest acceptance until a backend API adapter is wired.
- No-lookahead data isolation remains a high-value future hardening topic.

## 7. Case F: Notification And Settings

### Goal

Validate that notification works as a subscriber side effect and settings do not
corrupt secrets.

### Execute

```bash
uv run pytest test/test_notification_channels.py test/test_watchlist_alerts.py -q
```

Manual smoke:

1. Open `http://localhost:3000/settings`.
2. Save settings with masked secrets already present.
3. Confirm masked placeholders do not overwrite stored secret values.
4. Use notification test endpoints for configured channels only.

### Pass Criteria

- Missing channel config returns a clear non-fatal result.
- Webhook payload format is correct.
- Analysis and approval notifications include strategy/account/session/decision
  identity where available.
- Settings preserve masked secret semantics.

### Existing Automated Coverage

- `test/test_notification_channels.py`
- `test/test_watchlist_alerts.py`
- `server/routes/settings.py` secret-preservation behavior should be covered more
  directly in a future test.

### Watch Items

- Real external channel delivery needs real credentials and network access; keep
  this separate from normal CI acceptance.

## 8. Case G: Frontend Shell And API Contract Smoke

### Goal

Verify that the integrated frontend builds and the main pages map to real API
routes.

### Execute

```bash
cd frontend
npm run lint
npm run build
npm run dev
```

Visit:

- `/quick-ask`
- `/approvals`
- `/memory-lab`
- `/settings`
- `/watchlist`
- `/monitor`
- `/agent`
- `/strategies`

### Pass Criteria

- Production build succeeds.
- Pages render without fatal runtime errors.
- `/quick-ask` can consume `/api/analyze` SSE.
- `/approvals` can list and mutate approval rows.
- `/memory-lab` can list strategy-scoped memory rows.
- `/settings` can read and update settings.

### Watch Items

- Frontend lint currently has warning debt.
- Some frontend API helpers are ahead of backend implementation. Treat those as
  future-work surfaces unless the route exists in `server/routes`.

## 9. Recommended Acceptance Order

Run acceptance in this order:

1. **P0 command gate:** tests, ruff, basedpyright, frontend lint/build.
2. **Memory + analyze spine:** direct `/api/analyze` SSE request with explicit
   strategy/account/decision identity.
3. **HITL lifecycle:** deterministic tests, then UI smoke if a pending approval
   exists.
4. **Broker/backtest contract:** `test/broker` and `test/agentgraph`.
5. **Frontend shell:** build plus browser navigation.
6. **External integrations:** notification channels and provider-backed live
   analysis only after credentials/network are intentionally available.

## 10. Acceptance Decision Template

Use this final signoff shape:

```text
Dev acceptance status: PASS / PASS WITH DEBT / FAIL

Automated baseline:
- pytest:
- ruff:
- basedpyright:
- frontend lint:
- frontend build:

Manual smoke:
- Quick Ask analyze:
- Memory Lab:
- Approvals:
- Settings/notifications:
- Broker/backtest:

Known debt:
- ...

Blockers before using dev as baseline:
- ...
```
