# Progress & Roadmap

Last updated: 2026-07-12 | Branch: `dev`

## Frontend Demo Integration: Review Corrections ✅

Completed on 2026-07-12 after product-owner review of the Phase 7 candidate.

Delivered:

- Replaced Strategies' native deletion confirmation with the existing browser-
  DOM `AlertDialog`. The dialog has truthful deletion-scope copy, pending and
  recoverable failure states, responsive destructive styling, aligned mobile
  visual/Tab order, and explicit focus restoration to the surviving Search
  input after cancel, failure dismissal, or successful deletion.
- Identified the source of the reappearing history as two Analyze route tests
  writing fixtures into the real `data/history` directory. Both tests now use
  isolated `tmp_path` history; the two confirmed test artifacts were deleted
  through the API, and a complete suite leaves real history empty.
- Extended the tombstone contract to Reports source resolution so an analysis
  deleted from history cannot reappear as an explicit or latest Report source
  if a same-name JSON file is written later.

Fresh verification:

- The browser RED captured a native `confirm` and no DOM `alertdialog`. Final
  production Chromium captured no native dialog; cancel, forced HTTP 500,
  success, and mobile cancellation all restored Search with no inert layer.
  Keyboard input after deletion succeeded, mobile focus order matched layout,
  and destructive contrast measured `6.85:1`.
- Independent hands-on QA passed `11/11` browser/history scenarios. Both visual
  reviewers and the Goal, code-quality, security, and context review lanes
  returned unconditional PASS.
- `uv run pytest test -q` passed `261 passed, 1 skipped, 1 warning in 8.05s` and
  emitted `FULL_SUITE_HISTORY_ISOLATION_PASS`; the real history count stayed
  zero. BasedPyright, Ruff check/format, frontend TypeScript, production build,
  scoped lint, suppression, forbidden-path, and diff checks passed. Repository
  ESLint retained 66 documented pre-existing warnings and no errors.

Evidence:

- `.omo/evidence/frontend-demo-integration/review-fixes/final-review.md`
- `.omo/evidence/frontend-demo-integration/review-fixes/final-browser-qa.json`
- `.omo/evidence/frontend-demo-integration/review-fixes/strategy-delete-final-desktop.png`
- `.omo/evidence/frontend-demo-integration/review-fixes/strategy-delete-final-mobile.png`

Next: request product-owner closeout after the scoped correction is committed,
pushed to `origin/dev`, and verified at remote parity.

## Frontend Demo Integration: Phase 7 — Cross-Page Acceptance & Closeout ✅

Completed on 2026-07-12 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Completed the real cross-page acceptance journey for Strategies, Quick Ask,
  Memory Lab, Backtest, Scanner, Risk, Reports, and Settings, including failure
  or empty states, responsive layouts, reload/navigation restoration, and
  browser console/network inspection.
- Fixed full-suite pytest collection by selecting importlib import mode, then
  added deterministic startup recovery and concurrency-safe lifecycle ownership
  for Backtest and Report executors. Route-local lifespans preserve the SHARED
  `server.main` to ACTIVE track boundary on normal and exceptional shutdown.
- Made Memory Lab's `strategy_id` URL-authoritative, removed the misleading MCP
  Start control, tightened changed-path TypeScript contracts, and resolved the
  final responsive/sidebar/calendar visual gate findings.
- Updated this issue tracker only after the independent F1-F4 and security
  reviewers approved the stable candidate.

Fresh final gate evidence:

- `uv run pytest test -q` passed: `260 passed, 1 skipped, 1 warning in 7.43s`;
  the warning is the existing Starlette/httpx deprecation warning.
- BasedPyright passed with zero diagnostics and its mechanical baseline pruning
  was restored. Repository Ruff check/format, frontend TypeScript, ESLint,
  `git diff --check`, and changed-path suppression scans passed. ESLint retained
  66 documented pre-existing warnings and no errors.
- The required sandbox-external Next production-build retry passed compilation,
  TypeScript, page collection, and all 20 routes after the sandbox-only
  Turbopack internal-port `EPERM`.
- Fresh production Chromium and real FastAPI/curl QA used a cleanable two-
  strategy dataset and drove all eight pages. Backtest, Scanner, and Report
  records survived a backend restart; Risk and Memory switched between distinct
  strategy identities; a completed Report downloaded as a real PDF while
  pending, missing, and traversal-shaped downloads were rejected.
- The runtime debugging audit rejected all three required hypotheses: in-memory-
  only job loss, stale cross-strategy query identity, and unsafe Report download
  bypass. F1, F2, F3, F4, and security reviewers returned unconditional
  approval with no blocker.

Evidence:

- `.omo/evidence/frontend-demo-integration/phase-7/phase-7-runtime-receipt.md`
- `.omo/evidence/frontend-demo-integration/phase-7/full-gate-root.md`
- `.omo/evidence/frontend-demo-integration/phase-7/debug-audit/runtime-audit.md`
- `.omo/evidence/frontend-demo-integration/final-review/`

Next: create the scoped Phase 7 commit, push `origin dev:dev`, prove remote
parity, and run the F1 remote-final audit before presenting closeout to the
user.

## Frontend Demo Integration: Phase 6 — Notification Setup & Status ✅

Completed on 2026-07-12 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Added accurate configured/incomplete state and exact missing-field guidance
  for the four existing Email, Telegram, WeChat, and WhatsApp channels,
  including partial and whitespace-only configuration handling.
- Added stable, actionable local test feedback and safe transport-error
  categories. Notification secrets, tokenized URLs, chat IDs, recipients,
  webhook URLs, access tokens, and provider response bodies are redacted from
  API responses and logs.
- Replaced the Settings notification demo guidance with typed four-channel
  status, required-field help, official provider links, and truthful pending,
  success, and failure states. Editing a channel configuration clears only
  that channel's stale test result.
- Added `docs/notifications.md` with provider-specific setup and trigger-point
  guidance, and aligned the API contract with the four implemented channels;
  the former unimplemented Feishu reference was removed.

Fresh independent final gate evidence:

- `uv run pytest test/test_notification_channels.py
  test/server/test_notification_settings.py test/test_watchlist_alerts.py -q`
  passed: `22 passed, 1 warning`; the warning is the existing Starlette/httpx
  deprecation warning.
- Strict changed-path and baseline BasedPyright passed with zero diagnostics.
  Scoped Ruff check/format, frontend TypeScript, ESLint, `git diff --check`,
  and the no-suppression scan passed. Frontend lint retained 69 documented
  pre-existing warnings outside the Phase 6 Settings changes.
- The final escalated `cd frontend && npm run build` passed compilation,
  TypeScript, page collection, and all 20 Next.js routes.
- An isolated live FastAPI matrix drove all four configured successes via
  monkeypatched local transports, all four unconfigured responses,
  whitespace-only and partial configurations, timeout, HTTP 429, and invalid-
  recipient-style HTTP 400 failures. No real provider or recipient was
  contacted, and generated secret markers were absent from API responses and
  captured logs.
- Production Chromium QA at 1280, 768, and 375 widths proved all four channel
  states, official help, pending/success/failure feedback, and stale-success
  clearing after a configuration edit, with no horizontal overflow, console
  error, or secret exposure. Two independent visual reviewers returned PASS.
  A three-hypothesis runtime audit rejected logger/API leakage, whitespace
  false-positive configuration, and stale per-channel success. Full receipt:
  `.omo/evidence/frontend-demo-integration/phase-6/phase-gate-final.md`.
- Official Telegram, SMTP/RFC and provider app-password, Enterprise WeChat,
  and Meta WhatsApp Cloud documentation links were verified reachable during
  execution.

Next: begin only Phase 7 Todo 14 (cross-page real acceptance, final runtime
debugging/review, issue-truth update, and final push) after this Phase 6 commit
is pushed and `origin/dev` parity is proved.

## Frontend Demo Integration: Phase 5 — Source-Driven Reports ✅

Completed on 2026-07-11 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Added validated Stock and Sector report sources over completed persisted
  analysis and Scanner runs, with explicit provenance, selected-section
  allowlisting, data-gap reporting, and no analysis, LLM, or provider reruns.
- Added durable SQLite report jobs, restart recovery, bounded background
  rendering, CJK preflight, atomic PDF publication, safe basename-only artifact
  resolution, sanitized downloads, and stable failure cleanup.
- Replaced the Reports demo with typed Stock generation, the required Scanner
  then persisted Sector-report flow, durable status/history polling, completed-
  only PDF downloads, and actionable missing-source, empty, and failure states.

Fresh independent final gate evidence:

- `uv run pytest test/reporting test/server/test_reports_api.py -q` passed:
  `18 passed, 1 warning`; separately run Scanner regressions passed `24` tests
  and analysis run-state/memory regressions passed `4` tests. The warning is
  the existing Starlette/httpx deprecation warning.
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` passed
  with zero diagnostics. Scoped Ruff check/format, frontend TypeScript,
  ESLint quiet, and `git diff --check` passed; the authoritative BasedPyright
  baseline was restored after the tool pruned obsolete entries.
- The final default `cd frontend && npm run build` passed compilation,
  TypeScript, page collection, and all 20/20 Next routes.
- Isolated seeded FastAPI and production Chromium QA created, polled, reloaded,
  downloaded, and inspected a source-driven Stock PDF; proved the Sector
  request order `POST /api/agent/scanner` then `POST /api/reports/sector`;
  exercised missing analysis, zero-match/compilation, renderer, history 500,
  pending 409, missing 404, and restart-recovery paths. The downloaded PDF had
  valid PDF magic, one page, safe filename, selected Decision/Risk content,
  and no deselected sections.
- Thirteen fresh captures covered Reports at 1280, 768, and 375 widths,
  including the tablet table's rightmost Status/Updated/Download columns and
  responsive mobile history cards. Two independent visual reviewers returned
  PASS/HIGH. A three-hypothesis runtime audit rejected unsafe or pending
  downloads, non-durable job status, and Sector Scanner bypass/ticker
  fabrication. Full receipt:
  `.omo/evidence/frontend-demo-integration/phase-5/phase-gate-final.md`.

Existing out-of-scope observations retained: the repository-wide Ruff probe
finds only `.omo` QA-harness E402/format findings, and the global Header still
contains its pre-existing fixed `Market Open` placeholder.

Next: begin only Phase 6 Todo 13 (safe configured-state and guidance for the
four existing notification channels) after this Phase 5 commit is pushed and
`origin/dev` parity is proved.

## Frontend Demo Integration: Phase 4 — Decision-Target Risk Analytics ✅

Completed on 2026-07-11 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Added deterministic Risk analytics over each strategy's latest persisted
  decision targets and cached market history. The response identifies
  `source="decision_target"`, preserves decision IDs/timestamps and residual
  cash, rejects exposure above 100% without normalization, and never treats
  targets as executed holdings.
- Added typed overview and uniform-market-shock APIs with decimal return units,
  historical VaR95/VaR99/CVaR95, drawdown, correlation, ticker/sector
  concentration, actual worst-day stress, and distinct complete, partial,
  unavailable, and invalid states.
- Replaced the Risk demo with a real strategy selector, strategy-keyed server
  state, accessible return/drawdown charts, correlation and exposure tables,
  concentration results, explainable stress execution, and truthful error and
  insufficient-data states without stale cross-strategy results.

Fresh independent final gate evidence:

- `uv run pytest test/risk test/server/test_risk_api.py test/server/test_strategies_lifecycle.py test/server/test_scanner_api.py test/server/test_backtest_api.py test/dataflow/test_data_service.py -q`
  passed: `54 passed, 1 warning in 3.84s`; the warning is the existing
  Starlette/httpx deprecation warning.
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` passed
  with zero diagnostics. Scoped `uv run ruff check` and
  `uv run ruff format --check`, `cd frontend && npx tsc --noEmit`,
  `cd frontend && npm run lint -- --quiet`, and `git diff --check` passed.
- The required escalated `cd frontend && npm run build` passed against the
  final Risk source: compilation, TypeScript, page collection, and all 20/20
  Next routes completed.
- A seeded isolated FastAPI service and production Chromium QA proved distinct
  Alpha/Beta targets and metrics, a real `-10%` stress request rendering
  `-8.50%` for 85% gross exposure, and separate unavailable, invalid, partial,
  and deliberate HTTP 500 states. Fourteen fresh captures covered the full
  Risk surface at 1280, 768, and 375 widths with zero horizontal overflow;
  two independent visual reviewers returned PASS/HIGH. A three-hypothesis
  runtime audit refuted cross-strategy stale data, decimal conversion errors,
  and provider/agent/equal-weight fallback. Full receipt:
  `.omo/evidence/frontend-demo-integration/phase-4/phase-gate-final.md`.

Next: begin only Phase 5 Todos 11–13 (validated report sources, durable report
jobs and safe artifacts, real report API/page) after this Phase 4 commit is
pushed and `origin/dev` parity is proved.

## Frontend Demo Integration: Phase 3 — Tracked-Universe Scanner ✅

Completed on 2026-07-11 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Added the deterministic tracked-universe resolver and typed Scanner engine.
  The sorted universe is the normalized union of strategy, watchlist, and
  cached-market tickers; snapshots use cached `MarketDataStore` data only,
  preserve missing values, expose provenance and warnings, and evaluate the
  frozen field/operator grammar with deterministic AND semantics.
- Added durable SQLite scan runs plus separate SHARED rule/read routes and an
  ACTIVE restricted Agent/Belief compilation route. Agent compilation accepts
  exactly one validated `scan_tracked_universe` tool result; Belief mode
  verifies exact strategy ownership and weight, and neither path persists
  chain-of-thought.
- Replaced the Scanner demo with real Rule, Agent, and Belief workflows,
  editable typed conditions, honest tracked-universe counts, visible
  pending/error/empty/partial states, API-backed results and compiled
  conditions, and `scan_run_id` reload restoration.

Fresh independent final gate evidence:

- `uv run pytest test/scanner test/server/test_scanner_api.py test/agent/test_scanner_tool.py test/agent/test_tool_allowlist.py test/dataflow/test_data_service.py test/server/test_strategies_lifecycle.py -q`
  passed: `54 passed`, with one existing Starlette/httpx deprecation warning.
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json` passed
  with zero diagnostics. Scoped `uv run ruff check` and
  `uv run ruff format --check`, `cd frontend && npx tsc --noEmit`,
  `cd frontend && npm run lint`, and `git diff --check` passed. Frontend lint
  retained 75 existing out-of-scope warnings and reported no errors or
  warnings in the changed Scanner files.
- The required escalated `cd frontend && npm run build` retry passed against
  the current source after the sandbox-only Turbopack localhost-port `EPERM`;
  compilation, TypeScript, page collection, and all 20 routes completed.
- Fresh mounted FastAPI and production Chromium QA exercised Rule, Agent, and
  Belief request bodies and results, Add/Remove conditions, exact belief
  ownership, empty and 503 states, `scan_run_id` reload restoration, mode
  isolation, and responsive 375px layouts. The three-hypothesis runtime audit
  rejected provider/future-data leakage, cross-mode stale restoration, and
  ACTIVE allowlist or belief-ownership bypass. Full receipt:
  `.omo/evidence/frontend-demo-integration/phase-3/phase-gate-final.md`.

Next: begin only Phase 4 Todos 9–10 (decision-target Risk analytics and the
truthful Risk page) after this Phase 3 commit is pushed and `origin/dev`
parity is proved.

## Frontend Demo Integration: Phase 2 — Trusted Backtest ✅

Completed on 2026-07-11 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Replaced the BacktestRunner legacy-orchestrator default with an explicitly
  injected ACTIVE AgentLoop adapter, an allowlisted backtest tool surface, and
  an `as_of`-scoped data boundary that prevents future-bar lookahead.
- Added canonical single-ticker, independent-benchmark backtest results with
  exact daily/weekly/monthly decision frequency, typed failures, and persisted
  SQLite job recovery. The ACTIVE `/api/agent/backtest*` routes expose create,
  poll, and completed-job CSV download only.
- Replaced the Backtest demo page with a real strategy/job flow: canonical
  request fields, status polling, reload recovery, server-safe failure UI,
  equity/drawdown/trades/metrics, and completed-job CSV export.

Fresh independent final gate evidence:

- The focused Phase 2 suite passed: `53 passed, 1` existing
  Starlette/httpx deprecation warning. Scoped Ruff check/format, BasedPyright
  baseline, frontend TypeScript, scoped lint, and `git diff --check` passed.
- Two production `npm run build` executions passed (including the local API
  configuration used by Chromium); both completed compilation, TypeScript,
  and all 20 static pages.
- A real mounted FastAPI + production Chromium run observed the exact
  canonical `POST /api/agent/backtest` request, `202` job creation, persisted
  GET polling through completion, reload without duplicate create, CSV
  download, and a safe rendered failure state. Fresh 1280/768/375 visual
  reviews passed. Full receipt:
  `.omo/evidence/frontend-demo-integration/phase-2/phase-gate-final.md`.

Next: begin only Phase 3 Todos 6–8 (tracked-universe Scanner engine, persisted
rule/agent/belief runs, and truthful Scanner UI) after this Phase 2 commit is
pushed and `origin/dev` parity is proved.

## Frontend Demo Integration: Phase 1 — Strategy Lifecycle & Scoped Memory ✅

Completed on 2026-07-10 under
`plans/frontend-demo-integration/frontend-demo-to-real-functionality-plan.md`.

Delivered:

- Persisted Strategy clone/start/pause/stop routes with stable 404/409 contracts,
  idempotent lifecycle transitions, clone isolation, and explicit rejection of
  unsupported liquidation.
- Quick Ask now selects, sends, restores, and displays the real `strategy_id`;
  Strategy list mutations invalidate live state and expose failures; Memory Lab
  uses the selected strategy's configured memory store with distinct loading,
  empty, and storage-error states plus explicit refresh.
- Memory list/detail consistently honor `MEMORY_DB_PATH`, reject cross-strategy
  record access, and return observable `500` storage failures rather than a
  false empty result. The responsive mobile navigation and affected layouts
  were remediated as direct Phase 1 browser-QA support.

Fresh independent final gate evidence:

- `cd frontend && npm run build` passed on the immediate escalated retry after
  the sandbox-only Turbopack localhost-port bind failure; compilation,
  TypeScript, and all 20 static pages completed.
- `uv run pytest test/server/test_strategies_lifecycle.py test/server/test_memory_routes.py test/memory/test_service.py test/server/test_analyze_memory.py test/quick_ask/test_memory_integration.py -q`
  passed: `38 passed, 1` existing Starlette/httpx deprecation warning.
- `uv run basedpyright --baselinefile bugs/basedpyright/baseline.json`, scoped
  Ruff check/format, `cd frontend && npx tsc --noEmit`, and Git diff checks all
  passed. `cd frontend && npm run lint` passed with zero errors and 85 existing
  out-of-scope warnings.
- Mounted FastAPI and real Chromium proof covered strategy create/lifecycle/
  clone, visible lifecycle 409, exact Quick Ask `strategy_id` request body,
  Memory Lab 200 then rendered 500 error state, and cleanup of temporary
  strategies. Full receipt and source hashes:
  `.omo/evidence/frontend-demo-integration/phase-1/phase-gate-final.md`.

Next: begin Phase 2 Todos 3–5 (ACTIVE Backtest/no-lookahead contract, durable
SQLite jobs/API, and truthful Backtest UI) only after this Phase 1 commit is
pushed and `origin/dev` parity is proved.

## Phase 1 Progress: Data Foundation ✅

| # | Task | Status | Verified |
|---|------|--------|----------|
| 1.1 | Install APScheduler + activate DataCollector | Done | 32 tickers (dynamic from watchlists), 5 jobs, 192 OHLCV bars |
| 1.2 | MarketDataStore Python API | Done | JSON-safe, clean interface, no wrapper needed |
| 1.3 | Market Data REST routes | Done | 5 endpoints: prices, fundamentals, news, search, stats |
| 1.4 | Server integration | Done | collector starts with server, status in health endpoint |

**New API endpoints (all return real data from market_data.db):**
- `GET /api/market/prices/AAPL?start=...&end=...` — 114 OHLCV bars across 9 tickers
- `GET /api/market/fundamentals/AAPL` — PE/PB/PS/EPS/margins/growth
- `GET /api/market/news/AAPL?days=30` — 11 Chinese news articles via AkShare
- `GET /api/market/search?q=华为` — FTS5 full-text search
- `GET /api/market/stats` — data volume summary

## Phase 2 Progress: Strategy Storage & Management ✅

| # | Task | Status | Verified |
|---|------|--------|----------|
| 2.1 | Add list_strategies() + update_strategy() to ContextStore | Done | Create, list, filter by type/status, update |
| 2.2 | Rewrite /api/strategies CRUD endpoints | Done | All 8 tests passed (CRUD + delete → 404) |
| 2.3 | Frontend strategy pages → real API | Done | Build: 0 errors, TanStack useQuery |
| 2.4 | Verify Phase 2 end-to-end | Done | Backend CRUD works, frontend compiles |

**New/changed files:**
- `storage/store.py` — added `list_strategies()` (with type/status filter), `update_strategy()` (deep merge)
- `server/routes/strategies.py` — full rewrite: 7 endpoints, all real data from ContextStore
- `frontend/app/strategies/page.tsx` — TanStack useQuery replacing MOCK_STRATEGIES, Delete button wired
- `frontend/app/strategies/[id]/page.tsx` — TanStack useQuery for strategy + performance + decisions

**Strategy CRUD now works:**
- `GET /api/strategies` → real list with type/status filters
- `POST /api/strategies` → persists to system.db, returns 201
- `GET /api/strategies/:id` → reads from system.db, 404 if not found
- `PUT /api/strategies/:id` → partial update with deep merge
- `DELETE /api/strategies/:id?confirm=true` → deletes strategy DB + registry entry
- `GET /api/strategies/:id/performance` → computed from real decisions (no hardcoded 5.23%)
- `GET /api/strategies/:id/decisions` → date filter fixed

## Block A-D Progress: Frontend + Integration ✅

| Block | Task | Status | Verified |
|-------|------|--------|----------|
| A1 | Dashboard → real API | Done | Strategy cards with live performance from backend |
| A2 | Settings → real API | Done | Load/save config, Test Connection, data source status |
| B1 | Memory recall in PM agent | Done | recall_by_context injected into PM prompt before decision |
| B2 | remember_memory node in orchestrator | Done | Graph: PM_agent → remember_memory → END |
| C1 | Watchlist CRUD backend | Done | 8 endpoints, watchlists table in system.db |
| C2 | Watchlist frontend | Done | Real CRUD + live price data from market API |
| D1 | Memory Lab → real memory API | Done | Memories tab with OWM scores + ticker filter |
| E1 | Agent-driven data discovery | Done | New scheduler job, LLM discovery agent, discovery pool |
| F1 | MonitorTask CRUD + Runner | Done | 7 endpoints, keyword/ticker/domain modes, Agent summary |
| F2 | MonitorTask frontend | Done | Task list, create form, Run Now, report view with search trace |
| G1 | DataService unified layer | Done | Single entry point for all data access, 6 new methods, 17ms/700ms fast/slow |
| G2 | Consumer migration | Done | market.py, monitor.py, watchlist.py all use DataService only |
| H1 | Data layer fixes | Done | WAL mode, absolute paths, explicit commits, persistence verified |

**Cleanup:**
- `app.py` — marked as LEGACY/DEPRECATED. All analysis now via FastAPI `/api/analyze`.

**New files created:**
- `server/routes/watchlist.py` — 8 watchlist CRUD endpoints
- `server/routes/market.py` — 5 market data endpoints (Phase 1)

**Files modified:**
- `agentgraph/orchestrator.py` — added `_remember_memory_node`, `strategy_id`/`session_id` params, memory recall in `run()`
- `agents/PM.py` — memory context injected into system prompt
- `frontend/app/dashboard/page.tsx` — useQuery for strategies + performance
- `frontend/app/settings/page.tsx` — useQuery/mutation for settings API
- `frontend/app/watchlist/page.tsx` — full rewrite with real CRUD + price data
- `frontend/app/memory-lab/page.tsx` — full rewrite with real memory API
- `frontend/app/strategies/page.tsx` — useQuery (Phase 2)
- `frontend/app/strategies/[id]/page.tsx` — useQuery (Phase 2)
- `storage/store.py` — `list_strategies()`, `update_strategy()` (Phase 2)
- `server/routes/strategies.py` — full rewrite (Phase 2)
- `server/routes/health.py` — collector status in data-sources endpoint
- `server/main.py` — registered market + watchlist routers
- `CLAUDE.md` — commit conventions, properties.env never-touch rule

**Frontend pages now connected to real API:**
- Quick Ask (SSE) — was working before
- Strategy List + Strategy Detail + New Strategy — Phase 2
- Dashboard + Settings — Block A
- Watchlist — Block C
- Memory Lab (Memories tab) — Block D
- Monitor — Block F
- **Total: 8 of 15 pages connected** (was 1 at session start)

## Current State: Backend Audit Summary

**99 API endpoints in contract → 38 implemented (38%). Of those 38, 25 return real data.**

| Category | Endpoints in Contract | Implemented | Return Real Data |
|----------|----------------------|-------------|------------------|
| Analysis | 2 | 1 | 1 (SSE streaming) |
| Strategies CRUD | 12 | 6 | 6 (all real) |
| Beliefs | 4 | 0 | — |
| Portfolio & Performance | 7 | 2 | 1 (decisions) |
| Memory & Learning | 7 | 4 | 2 (memory, memory/:id) |
| Knowledge Base | 5 | 0 | — |
| Hypotheses | 5 | 0 | — |
| Skills | 6 | 0 | — |
| MCP | 6 | 0 | — |
| Backtest | 2 | 0 | — |
| Alpha Zoo | 3 | 0 | — |
| Insights | 3 | 0 | — |
| Approvals | 5 | 0 | — |
| Scanner | 4 | 0 | — |
| Watchlists | 8 | 8 | 8 (all real) |
| Monitors | 7 | 7 | 7 (all real) |
| Risk | 4 | 0 | — |
| Reports | 4 | 0 | — |
| Conversations | 4 | 0 | — |
| Settings | 6 | 4 | 0 (all stubs/mock) |
| Health | 2 | 2 | 2 |
| **Total** | **99** | **19** | **5** |

## Frontend Status

**15 pages → 1 functional (Quick Ask). 14 use inline mock data, 0 API imports.**

| Page | Uses API? | Buttons Work? | Backend Needed |
|------|-----------|---------------|----------------|
| Landing `/` | N/A (static) | Links work | None |
| Dashboard `/dashboard` | No | No | strategies, insights, approvals |
| Strategies `/strategies` | **Yes** (useQuery) | **Yes** (Delete works) | strategies CRUD ✅ |
| Strategy Detail `/strategies/[id]` | **Yes** (useQuery) | Partial (tabs render) | account, positions, debates, events |
| Quick Ask `/quick-ask` | **Yes** (SSE) | **Yes** | analyze (exists, works) |
| Conversation `/quick-ask/[id]` | No | No | conversations CRUD |
| Backtest `/backtest` | No | No | backtest CRUD |
| Memory Lab `/memory-lab` | No | No | knowledge, hypotheses, reflections |
| Insights `/insights` | No | No | insights CRUD |
| Approvals `/approvals` | No | No | approvals CRUD |
| Scanner `/scanner` | No | No | scanner CRUD |
| Watchlist `/watchlist` | No | No | watchlist CRUD |
| Risk `/risk` | No | No | risk CRUD |
| Reports `/reports` | No | No | reports CRUD |
| Settings `/settings` | No | No | settings (partially exists, all stubs) |

## Data Layer Status

| Module | Status | Notes |
|--------|--------|-------|
| **MarketDataStore** (`dataflow/store.py`) | Complete | OHLCV, fundamentals, news (FTS5), ticker_meta, freshness |
| **ContextStore** (`storage/store.py`) | Stable | Strategies, watchlists, monitor_tasks, monitoring_reports. WAL mode, absolute paths, explicit commits. |
| **MemoryStore** (`memory/store.py`) | Core + OWM | Missing: Reflection store |
| **DataService** (`dataflow/service.py`) | Unified | Single entry point: get_prices, get_news, get_meta, get_indicators, get_fundamentals, search_news. All consumers go through it. |
| **DataCollector** (`scheduler/__init__.py`) | Running | 5 jobs, 32 tickers (dynamic from watchlists). MonitorRunner integrated. |
| **MonitorRunner** (`scheduler/__init__.py`) | Running | 5-min master refresh, per-task scheduling |
| **MarketData DB** (`data/market_data.db`) | Live | 192 OHLCV, 12 fundamentals, 131 news, 10 tickers, ticker_meta populated |

## Verified Modules

| Module | Verified | Notes |
|--------|----------|-------|
| Agent pipeline (CLI) | Yes | 5-agent, DeepSeek LLM, real output |
| Agent pipeline (API) | Yes | POST /api/analyze SSE stream |
| AkShare news | Yes | East Money, mainland accessible |
| Google News -> AkShare fallback | Yes | automatic |
| Frontend build | Yes | 17 routes, 0 errors |
| Frontend Quick Ask | Yes | input ticker -> Analyze -> result |
| Market Data REST routes | Yes | 5 endpoints, all return real data |
| MarketDataStore | Yes | OHLCV, fundamentals, news (FTS5) |
| DataCollector (APScheduler) | Yes | 4 jobs, 9 tickers, automated |
| MemoryStore | Yes | SQLite CRUD + OWM scoring |
| ContextStore (core) | Yes | sessions, reports, decisions |

## Data Architecture

Two-mode data acquisition (search + recommendation model):

**Mode A: Search (Quick Ask)** — On-demand, deep, single-ticker
- User queries a ticker -> instant full fetch (prices, news, fundamentals, indicators)
- Data cached to store for future queries

**Mode B: Recommendation (Watchlist/Strategy)** — Proactive, broad, multi-ticker
- Active Pool: tickers in user strategies + watchlists (full data, scheduled)
- Discovery Pool: related tickers by sector/theme/co-occurrence (light data, idle time)
- Relation graph auto-expands coverage as user explores domains

See `docs/development-plan.md` for full data strategy design.

## Development Phases

### ✅ Phase 1: Data Foundation
### ✅ Phase 2: Strategy Management
### ✅ Phase 3: Frontend Integration (Dashboard, Settings, Watchlist, Memory Lab, Monitor)
### ✅ Phase 4: Agent Integration (Memory recall/remember, Discovery)
### ✅ Data Layer Unification (DataService single entry point)

### Next priority:
1. **Strategy Execution** — strategies actually run on schedule, produce decisions
2. **Deep Research** — multi-agent deep analysis pipeline
3. **Backtest** — historical simulation
4. **Settings persistence** — system.db instead of in-memory DEFAULT_CONFIG

## Branch Strategy

```
main <- feat/frontend-backend (current)
  ↑
  ├── feat/strategy-crud
  ├── feat/agent-expansion
  ├── feat/hitl-approval
  └── feat/broker-engine
```
