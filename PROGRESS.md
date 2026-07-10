# Progress & Roadmap

Last updated: 2026-07-10 22:17 | Branch: `dev`

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
