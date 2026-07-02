# Dev Branch Merge Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for execution. This document is a read-only branch diagnosis and merge/integration plan; it does not create `dev` and does not perform merges by itself.

**As of:** 2026-07-02 after `git fetch --prune origin` and `git fetch --prune upstream`.

**Goal:** Build a long-lived `dev` branch that combines the execution substrate, Web/API shell, HITL approval flow, and notification assets into one coherent development baseline.

**Architecture:** Use `upstream/main` / `origin/main` as the repository baseline because it already contains `feat/frontend-foundation`; treat `feat/broker-plus` as the execution-domain substrate to preserve; treat `upstream/feat/frontend-backend` as the Web/API shell; treat `upstream/feat/new-hitl` and `upstream/feat/social-media-message-alerts` as feature assets that require hand integration rather than wholesale overwrite.

**Tech Stack:** Python 3.12, FastAPI, Next.js, shadcn UI, Pydantic, pandas, SQLite/local JSON stores, pytest, basedpyright, ruff, uv.

---

## 1. Current Branch Inventory

| Branch | Tip observed | Role | Relationship | Completion judgment | Merge decision |
| --- | --- | --- | --- | --- | --- |
| `feat/broker-plus` / `origin/feat/broker-plus` | `83c15fc` | Broker execution substrate: broker models, gateway, mock engine, ledger, events, views, backtest runner, execution node, broker tests and planning docs. | Current branch. `upstream/feat/broker-plus` is an ancestor and is 2 commits behind. | High for first-stage execution-domain contract; medium for full platform because server/frontend/HITL/notification are intentionally out of scope. | Merge first into `dev`; preserve as execution truth. |
| `upstream/feat/frontend-backend` | `f6ff879` | Web/API shell: FastAPI routes, Next.js UI, quick ask legacy flow, `agent/` terminal, market/watchlist/monitor/insights routes, data/store expansion. | Contains `upstream/feat/frontend-foundation` (`0 34` ahead). Independent from broker-plus; common base with broker-plus is old `36a6a3f`. | Medium-high for Web/API scaffolding; still prototype in settings/performance/agent-broker integration. | Merge after broker-plus; keep as platform shell but do not let it delete broker execution domain. |
| `upstream/feat/new-hitl` | `9234ac2` | HITL approval asset: rules, state machine, approvals SQLite CRUD, approvals API, approvals page. | Independent short branch from `upstream/main`; not contained in frontend-backend (`31 3` split). | Medium prototype: real API/UI/state machine, but no tests, no `decision_id`/`account_id`, no timeout/resume execution closure. | Merge after frontend-backend; adapt to broker-plus report/identity contracts. |
| `upstream/feat/social-media-message-alerts` | `8e4eb37` | Notification asset: Email/Telegram/WeChat/WhatsApp channels, settings tests, analysis-complete notification, watchlist alerts. | Independent short branch from `upstream/main`; not contained in frontend-backend (`31 7` split) or new-hitl (`3 7` split). | Medium prototype: real channel implementations and some tests, but watchlist storage/API conflicts with frontend-backend and settings secrets need care. | Integrate last; cherry-pick/merge assets, preserve frontend-backend storage/router shape. |
| `feat/frontend-foundation` / `upstream/feat/frontend-foundation` | `e57cd55` | Initial FastAPI + Next.js foundation. | Ancestor of `upstream/main` and `upstream/feat/frontend-backend`; local and upstream match. | Superseded. | Do not merge separately. |
| `feat/broker` / `origin/feat/broker` | `69ea315` | Early broker-plus planning predecessor. | Strict ancestor of `feat/broker-plus` (`0 26` behind). | Superseded. | Do not merge separately. |
| `upstream/feat/broker` | `400e0aa` | Older broker predecessor. | Ancestor of `upstream/feat/broker-plus`; older than local/origin broker-plus. | Superseded. | Do not merge separately. |
| `upstream/feat/broker-plus` | `8988e4b` | Upstream copy of broker-plus. | Ancestor of current local/origin broker-plus; missing `4665eb0` and `83c15fc`. | Useful reference only. | Prefer current `feat/broker-plus` / `origin/feat/broker-plus`. |

## 2. Evidence Summary

Commands used for branch relationship checks:

```bash
git for-each-ref --sort=refname --format='%(refname:short)|%(objectname)|%(committerdate:iso8601)|%(subject)' refs/heads/feat refs/remotes/origin/feat refs/remotes/upstream/feat
git rev-list --left-right --count feat/broker...feat/broker-plus
git rev-list --left-right --count upstream/feat/frontend-foundation...upstream/feat/frontend-backend
git rev-list --left-right --count upstream/feat/new-hitl...upstream/feat/frontend-backend
git rev-list --left-right --count upstream/feat/social-media-message-alerts...upstream/feat/frontend-backend
git merge-base upstream/main feat/broker-plus
git merge-base upstream/feat/frontend-backend upstream/feat/new-hitl
git merge-base upstream/feat/frontend-backend upstream/feat/social-media-message-alerts
```

Key results:

- `feat/broker...feat/broker-plus = 0 26`: `feat/broker` has no unique commits beyond broker-plus.
- `upstream/feat/frontend-foundation...upstream/feat/frontend-backend = 0 34`: frontend-backend is the fuller frontend branch.
- `upstream/feat/new-hitl...upstream/feat/frontend-backend = 3 31`: HITL is not included in frontend-backend.
- `upstream/feat/social-media-message-alerts...upstream/feat/frontend-backend = 7 31`: notification is not included in frontend-backend.
- `upstream/main` already points at `f8a22d3`, which merged frontend-foundation.
- There is no local `dev` or `upstream/dev` ref observed in this checkout.

## 3. Recommended Merge Order

### Phase 0: Prepare The Integration Branch

Start `dev` from the current shared main baseline, then merge feature modules in semantic order.

```bash
git fetch --prune origin
git fetch --prune upstream
git switch -c dev upstream/main
```

Before creating the branch in a real execution session, verify whether `origin/main` and `upstream/main` still match or whether one has advanced:

```bash
git rev-parse origin/main upstream/main main
git rev-list --left-right --count origin/main...upstream/main
```

### Phase 1: Merge Broker-Plus First

Merge:

```bash
git merge --no-ff feat/broker-plus
```

Resolution policy:

- Keep the entire `broker/` package from broker-plus.
- Keep `agentgraph/execution_node.py` and broker-plus execution report semantics.
- Preserve broker-plus `agentgraph/orchestrator.py` run inputs: `as_of`, `execution_enabled`, `strategy_id`, `account_id`, `session_id`, `decision_id`.
- Merge `.gitignore`, `pyproject.toml`, and `uv.lock` carefully; keep broker-plus quality gates (`pytest`, `basedpyright`, `ruff`) and add platform deps later.
- Keep `properties.env` untracked/local-only.

Focused validation after resolution:

```bash
uv run pytest test/broker test/agentgraph -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check .
uv run ruff format --check .
```

### Phase 2: Merge Frontend-Backend As Web/API Shell

Merge:

```bash
git merge --no-ff upstream/feat/frontend-backend
```

Resolution policy:

- Accept `frontend/`, `server/`, `quick_ask/`, `agent/`, `storage/`, monitor/market/watchlist/insights/agent routes as platform shell assets.
- Do not allow frontend-backend's migration to `quick_ask/` to delete broker-plus `agentgraph` execution surfaces.
- Treat `quick_ask/` as legacy analysis/quick ask, and `agent/` as terminal/ReAct workspace. Treat `agentgraph/` as broker execution graph until a later architecture decision replaces it.
- Manually merge `dataflow/service.py`: keep frontend-backend's store/cache/news/provider APIs and broker-plus's broker-backed position seam.
- Combine dependencies: keep `fastapi`, `uvicorn[standard]`, `apscheduler` from frontend-backend and `pydantic-settings`, `pytest`, `basedpyright`, `ruff`, `playwright` / config from broker-plus if still needed.

Focused validation after resolution:

```bash
uv run pytest test -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check .
cd frontend && npm run lint && npm run build
```

### Phase 3: Merge HITL Approval Flow

Merge:

```bash
git merge --no-ff upstream/feat/new-hitl
```

Resolution policy:

- Keep `hitl/` and `server/routes/approvals.py`, but adapt them before treating the merge as complete.
- Remove `.next/trace` and `.next/trace-build`; they are build artifacts and one trace records a failed build.
- Do not let `server/routes/analyze.py` revert to the old foundation version; integrate HITL checks into the frontend-backend analysis stream.
- Extend approval records with `decision_id`, `account_id`, and explicit approval reason fields.
- Replace raw `dict` request bodies with Pydantic request models.
- Map `modified_target_position_pct` into broker-plus `modified_target_pct`.
- Use broker-plus `ExecutionReportView(status="pending")` for pending approval and do not place orders while pending.
- Approved/modified/rejected/timed-out results should resume through broker-plus `execution_node`; `hitl/executor.py` must not directly submit broker orders.

Focused validation after resolution:

```bash
uv run pytest test/broker test/agentgraph -q
uv run pytest test -q
cd frontend && npm run lint && npm run build
```

New tests to add during implementation:

- HITL rule trigger and no-op behavior.
- Approval state-machine valid/invalid transitions.
- Approval API approve/reject/modify schema behavior.
- Pending approval produces an execution report without broker order placement.
- Modified approval resumes execution with original and modified target percentages recorded.

### Phase 4: Integrate Notification Assets

Merge or cherry-pick assets from:

```bash
git merge --no-ff upstream/feat/social-media-message-alerts
```

Resolution policy:

- Keep `notification/` channel implementations, especially Email, Telegram, WeChat webhook, and WhatsApp adapters.
- Keep settings test endpoints and generic notification send endpoint, but preserve frontend-backend's broader settings/page state.
- Preserve frontend-backend's watchlist storage/router shape. Do not replace it wholesale with `server/routes/watchlists.py` JSON-file storage unless the team explicitly decides to abandon SQLite/store-backed watchlists.
- Move alert trigger behavior into the selected watchlist/monitor storage layer.
- Do not hard-code Telegram-only analysis notification in the final form. Route notifications through an event-aware manager and user/channel config.
- Fix the social branch UI string bug where `Create Alert for ${alertTicker}` is literal text instead of interpolation.
- Preserve masked secret semantics for `llm_api_key`, `email_password`, `telegram_bot_token`, and `whatsapp_access_token`.

Focused validation after resolution:

```bash
uv run pytest test/test_notification_channels.py test/test_watchlist_alerts.py -q
uv run pytest test -q
cd frontend && npm run lint && npm run build
```

## 4. Integration Work Required After Merges

### 4.1 Execution, Analysis, And Agent Boundaries

- Keep broker-plus execution as the source of truth for orders, fills, events, ledger records, execution reports, and backtest result views.
- Keep `quick_ask` as legacy analysis flow, and decide explicitly whether `/api/analyze` should use `quick_ask`, `agent/`, or `agentgraph` for each workflow.
- Add a thin server adapter for broker-plus instead of duplicating execution DTOs in FastAPI or TypeScript first.
- Align frontend `frontend/lib/types/models.ts` with `broker/views.py` output names and enum values.

### 4.2 Data Isolation And Backtest Safety

- Preserve broker-plus `as_of` propagation.
- Add a platform-level data access boundary so backtests and historical analysis cannot call current/live providers without an explicit as-of context.
- Keep `BacktestRunner` independent from `server`, `frontend`, `ContextStore`, and external brokers.

### 4.3 HITL Alignment

- Add `decision_id` and `account_id` to approval storage/API/UI.
- Standardize status naming between HITL and broker-plus. Recommendation: keep HITL lifecycle statuses (`pending`, `approved`, `rejected`, `modified`, `timed_out`) and map them into broker `ApprovalSnapshotView`; avoid exposing `auto_passed` as a broker approval snapshot when no human approval happened.
- Pending approval should create a structured pending execution report and no order.
- Approved/modified approval should resume through `execution_node` and produce normal broker events/reports.
- Rejected/timed-out approval should produce rejected execution reports and no ledger trade.

### 4.4 Notification Alignment

- Treat notification as a subscriber to domain events, not a state-changing participant.
- Source execution notifications from `BrokerEventView`, `ExecutionReportView`, or `ExecutionOutcomeView`.
- Source approval notifications from HITL state changes.
- Source analysis notifications from analysis completion/failure events with `session_id`, ticker, confidence, and report summary.
- Include `strategy_id`, `account_id`, `session_id`, and `decision_id` in notification payloads when available.

### 4.5 Storage And Settings

- Decide one persistent store shape for strategies, watchlists, approvals, monitor tasks, reports, and settings.
- Prefer preserving frontend-backend's store-backed watchlist/monitor APIs, then extending them for notification alerts.
- Keep `properties.env` out of Git and continue using `properties.env.example` for shared defaults.
- Do not let settings updates overwrite masked secrets with placeholders.

## 5. Conflict Hotspots

Expected high-touch files:

- `.gitignore`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `agentgraph/orchestrator.py`
- `agentgraph/state.py`
- `dataflow/service.py`
- `server/main.py`
- `server/routes/analyze.py`
- `server/routes/settings.py`
- `server/routes/watchlist.py` / `server/routes/watchlists.py`
- `storage/store.py`
- `frontend/lib/types/models.ts`
- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/app/settings/page.tsx`
- `frontend/app/watchlist/page.tsx`
- `frontend/app/approvals/page.tsx`

Delete/ignore artifacts during integration:

- `.next/trace`
- `.next/trace-build`
- runtime `data/*.db`, `data/settings.json`, `data/watchlists.json`, `data/history/`, and `data/agent-runs/` unless intentionally committed as fixtures.

## 6. Definition Of Done For The First Dev Branch

- `dev` contains broker-plus execution contracts and tests.
- `dev` contains frontend-backend Web/API shell without deleting broker execution surfaces.
- HITL can create/list/resolve approvals and carries `strategy_id`, `account_id`, `session_id`, and `decision_id`.
- Pending HITL decisions do not place broker orders.
- Approved/modified decisions can resume through broker-plus execution semantics.
- Notification channels can be configured/tested and can subscribe to analysis, approval, watchlist/monitor, and broker execution events without mutating domain state.
- Frontend TypeScript models match backend/broker view contracts.
- Full validation passes:

```bash
uv run pytest test -q
uv run basedpyright --baselinefile bugs/basedpyright/baseline.json
uv run ruff check .
uv run ruff format --check .
cd frontend && npm run lint && npm run build
```

## 7. Short Execution Handoff

Use `superpowers:subagent-driven-development` to execute this plan on a fresh `dev` branch created from the verified current main baseline. Merge in this order: `feat/broker-plus`, `upstream/feat/frontend-backend`, `upstream/feat/new-hitl`, then notification assets from `upstream/feat/social-media-message-alerts`. Preserve broker-plus as execution truth, frontend-backend as Web/API shell, HITL as approval lifecycle, and notification as event subscriber. Stop after all listed validation gates pass and the dev branch has a clean status.
