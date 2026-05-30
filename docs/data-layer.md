# Data Layer Design

Last updated: 2026-05-28

## Overview

The data layer is responsible for four concerns:
1. **Ingestion** — fetching from external providers (YFinance, Google News, AkShare, Finnhub)
2. **Storage** — persisting market data, decisions, events via SQLite
3. **Caching** — reducing API calls with integrity-verified cache
4. **Scheduling** — periodic background collection for data accumulation

## Architecture

```
┌─ Agent Tools (agents/utils/agent_tools.py) ─────────────────┐
│  get_price │ get_indicators │ get_fundamentals │ get_news   │
│  get_sector │ get_macro │ get_sentiment │ recall_memory     │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│  DataService (dataflow/service.py)                           │
│  Multi-provider router: YFinance live / AkShare historical   │
│  + cache integration + TTL management                        │
└──────┬──────────┬──────────┬──────────┬──────────────────────┘
       │          │          │          │
┌──────▼──┐ ┌─────▼───┐ ┌───▼────┐ ┌───▼──────────┐
│YFinance │ │Google   │ │AkShare │ │Finnhub/Sentiment│
│(price,  │ │News     │ │(PIT    │ │(macro, news    │
│indicator│ │(scrape) │ │fund)   │ │sentiment)      │
│s,fund)  │ │         │ │        │ │                │
└────┬────┘ └────┬────┘ └───┬────┘ └───────┬────────┘
     │           │           │              │
     └───────────┴─────┬─────┴──────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│  Cache Layer (dataflow/cache.py)                             │
│  pickle + SHA256 sidecar integrity + TTL expiry              │
│  ~/.agentic-quant/cache/                                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│  ContextStore (storage/store.py)                             │
│  SQLite: system.db / insights.db / {strategy_id}.db          │
│  Sessions, reports, decisions, events, audit trail           │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│  Memory + Knowledge (memory/, knowledge/)                    │
│  OWM-scored experience memory + rules/findings/failures KB   │
└──────────────────────────────────────────────────────────────┘
```

## Module Map

### dataflow/ — Data Ingestion

| File | Status | Description |
|------|--------|-------------|
| `service.py` | Production | DataService router, 9 methods. Routes live (YFinance) vs historical (AkShare) based on `end_date` |
| `cache.py` | **New** | Pickle cache with SHA256 sidecar integrity check + TTL expiry |
| `utils.py` | **New** | `retry()` with exponential backoff, safe type converters |
| `providers/YFinance.py` | Production | Prices, indicators (RSI/MACD/SMA/ATR), fundamentals snapshot, sector context |
| `providers/news_google.py` | Production | Google News scraping with tenacity retry, CAPTCHA detection, multi-lang |
| `providers/fundamentals_akshare.py` | Production | Point-in-time fundamental data for CN/US stocks |
| `providers/macro_calendar.py` | Production | Finnhub economic calendar |
| `providers/sentiment.py` | **New** | News sentiment aggregation (-1.0 to 1.0 score), keyword-based with cache |
| `portfolio_manager.py` | Basic | In-memory position tracking |

### storage/ — Context Persistence

| File | Status | Description |
|------|--------|-------------|
| `store.py` | **New** | `ContextStore`: SQLite-backed sessions, reports, decisions, events. Per-strategy .db isolation. |
| `__init__.py` | **New** | Singleton `get_store()` factory |

Database layout:
```
data/
├── system.db            — strategy registry, global config, beliefs
├── insights.db          — daily briefs, news archives
├── memory.db            — OWM memory records (via memory/store.py)
├── knowledge.db         — rules, findings, failures, hypotheses
├── {strategy_id}.db     — per-strategy data isolation
└── chat_{uuid}.db       — per-conversation history
```

### memory/ — Experience Memory

| File | Status | Description |
|------|--------|-------------|
| `models.py` | Complete | MemoryRecord, Reflection, PreTradeCheck Pydantic models |
| `owm.py` | Complete | OWM 5-factor scoring algorithm |
| `store.py` | Complete | SQLite-backed MemoryStore |
| `safety.py` | Complete | 5-factor pre-trade safety gate |

### knowledge/ — Knowledge Base

| File | Status | Description |
|------|--------|-------------|
| `manager.py` | Complete | File-based CRUD for rules/findings/failures. `get_context_for_agent()` for prompt injection |

### scheduler/ — Periodic Collection

| File | Status | Description |
|------|--------|-------------|
| `__init__.py` | **New** | `DataCollector` class with APScheduler. Price cache (15m), news (30m), sentiment (1h), macro (daily) |

### agents/utils/ — Agent Tools

| File | Status | Description |
|------|--------|-------------|
| `agent_tools.py` | **Updated** | Now 8 tools (was 4). Added: `get_sector`, `get_macro`, `get_sentiment`, `recall_memory`. All output includes JSON for machine parsing |

### mcp/ — MCP Integration

| File | Status | Description |
|------|--------|-------------|
| `base_tool.py` | **New** | `BaseTool` + `ToolRegistry` (95 lines, ported from Vibe-Trading, MIT) |
| `client.py` | **New** | `MCPClientManager` for loading external MCP tools. Supports stdio/SSE/streamableHttp |

### skills/ — Runtime Agent Documentation

| Directory | Content |
|-----------|---------|
| `data-sources/` | yfinance.md, akshare.md, data-routing.md (ported from Vibe-Trading) |
| `analysis/` | sentiment-analysis.md, fundamental-filter.md, factor-research.md, risk-analysis.md |
| `workflows/` | backtest-diagnose.md, alpha-zoo.md, multi-factor.md |
| `Vibe-Trading/` | Reference: full 76-skill library + BaseTool + MCP adapter |

## Data Flow

### Quick Ask (single analysis)
```
User input → agent tools → DataService → provider (cache check first)
  → if cache hit + valid TTL → return cached
  → if cache miss → fetch from API → write cache → return
  → ContextStore.record_session() + record_report()
```

### Scheduled Collection
```
DataCollector (background APScheduler)
  → Every 15m: refresh prices for DEFAULT_WATCH_TICKERS
  → Every 30m: invalidate stale news caches
  → Every 60m: pre-compute sentiment scores
  → Daily 8:00 UTC: refresh macro calendar
```

### Memory Loop (per strategy execution)
```
Before analysis:
  MemoryStore.recall(ticker, limit=5) → inject into PM prompt
After execution:
  MemoryStore.remember(decision) → store with OWM score
Weekly:
  Reflection generator → detect drift/decay → update knowledge base
```

## Anti-Hallucination Safeguards

1. **Cache integrity**: SHA256 sidecar files verify data hasn't been corrupted
2. **Explicit Unknown markers**: Providers return empty `{}` on failure, never fabricate
3. **Source attribution**: News items carry source URLs, fundamentals carry report dates
4. **Audit trail**: Every tool call, data retrieval, and agent output logged via ContextStore
5. **ONLINE toggle**: `ONLINE_DATA=false` disables all external API calls for testing

## Key Design Decisions

1. **Per-strategy .db isolation** — delete strategy = delete one file
2. **Pickle cache with SHA256** — simple, fast, integrity-verified. Not a defense against attackers with local write access
3. **Keyword-based sentiment as baseline** — production would use NLP/LLM. Current implementation provides a working baseline without external API dependency
4. **File-based knowledge base** — simpler than SQLite for text-heavy structured knowledge. Migratable to FTS5 if search needs grow
5. **APScheduler in-process** — no external cron for dev. Migrate to Celery Beat for production

## Gaps (Still TODO)

| Gap | Priority | Estimate |
|-----|----------|----------|
| `df_get_policy_expectations` implementation (FedWatch API) | Low | 8h |
| Multi-provider fallback in DataService (try YFinance → AkShare → cache) | Medium | 12h |
| News FTS5 full-text search in SQLite | Medium | 8h |
| `memory/reflection.py` — weekly reflection generator | Medium | 15h |
| `belief/contest.py` — belief competition engine | Medium | 20h |
| Broker mock engine | High | 120h |
| HITL approval state machine | High | 75h |
