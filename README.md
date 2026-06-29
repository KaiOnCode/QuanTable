# Agentic-Quant

**A multi-agent framework for reasoning-based quantitative analysis.**

Up to 15 specialized LLM agents collaborate via LangGraph with structured debate (bull/bear + risk 3-way) to produce verifiable investment decisions. Features strategy memory (OWM), knowledge base accumulation, belief-driven internal contests, MCP interoperability, and a React dashboard.

*University of Hong Kong — COMP7705 Final Year Project*

---

## System Architecture

```
                               ┌─ React Frontend (14 pages) ─┐
                               │  Dashboard │ Quick Ask │ ...  │
                               └──────────────┬────────────────┘
                                         REST + SSE
                               ┌──────────────▼────────────────┐
                               │        FastAPI Server          │
                               └──────────────┬────────────────┘
                                              │
         ┌────────────────────────────────────┼──────────────────────────────────┐
         │                            LangGraph Orchestrator                     │
         │                                                                       │
         │  START → [Company Overview] → 6 Analysts (parallel)                   │
         │    → Bull/Bear Debate → Research Manager → Trader                     │
         │    → 3-Way Risk Debate → Risk Manager → PM Decision → END              │
         │                                                                       │
         │  Each run: Memory recall → Belief contest → Cross-review → Record     │
         └───────────────────────────────────────────────────────────────────────┘
```

**Expanded Agent Pipeline (up to 15 agents):**

```
Stage 0: Company Overview       — Ticker context, sector, market cap
Stage 1: 6 Parallel Analysts    — Market | News | Fundamentals | Sentiment | Technical | Macro
Stage 2: Investment Debate      — Bull Researcher vs Bear Researcher (configurable rounds)
Stage 3: Research Manager       — Debate synthesis → Investment plan
Stage 4: Trader                 — Plan → Executable orders
Stage 5: 3-Way Risk Debate      — Aggressive | Safe | Neutral Risk
Stage 6: Risk Manager + PM      — Final risk sign-off + Pydantic decision output
```

## Reference Projects

This project's design is informed by deep analysis of 10+ open-source trading agent projects:

| Project | Key Ideas Adopted |
|---------|------------------|
| **TradingAgents-MCPmode** | 15-agent pipeline, dual debate architecture, agent enable/disable toggle |
| **Vibe-Trading** | SKILL.md format, Alpha Zoo (452 factors), BaseTool pattern, MCP server, backtest engine |
| **TradeMemory Protocol** | OWM 5-factor memory scoring, pre-trade safety gates, reflection cycles |
| **ContestTrade** | Belief contest mechanism, natural-language trading philosophies |
| **QuantGPT** | Knowledge base structure (rules/findings/failures), dual-LLM cross-review |
| **FinRobot/FinCon/AI-Trader** | Agent role specialization, multi-source data ingestion |
| **LLM-Trading-Lab** | Behavioral diagnostics (disposition effect, overtrading, anchoring) |
| **Daily Stock Analysis** | Multi-channel notifications, daily brief generation |
| **Financial Datasets MCP** | MCP tool design patterns, structured financial data schemas |

See `docs/reference/projects/` for detailed analyses and `docs/reusable-assets.md` for directly reusable code/patterns.

## Current Status

### Done

- **Agent pipeline**: 5-agent LangGraph workflow (market/news/fundamentals → risk → PM)
- **Data ingestion**: Yahoo Finance, Google News, AkShare, Finnhub with cache + retry
- **Data cache**: Pickle + SHA256 integrity, TTL expiry (`dataflow/cache.py`)
- **Sentiment provider**: Keyword-based news sentiment aggregation
- **8 agent tools**: price, indicators, fundamentals, news, sector, macro, sentiment, memory
- **React frontend**: 14 pages, 15 routes (Next.js 16 + shadcn/ui + TailwindCSS v4)
- **Memory layer**: OWM 5-factor scoring, SQLite store, pre-trade safety checks
- **Knowledge base**: Rules/findings/failures CRUD
- **Belief system**: Trading belief models + presets
- **ContextStore**: SQLite persistence with per-strategy database isolation
- **Data collector**: APScheduler-based periodic fetching (price/news/sentiment/macro)
- **MCP integration**: BaseTool + ToolRegistry + MCPClientManager
- **Skills**: 10 concrete SKILL.md files (data sources, analysis, workflows)
- **Documentation**: Architecture, data models, spec, API contracts, data layer

### In Progress / Next

- **Expanded agent pipeline**: 6 analysts, bull/bear debate, 3-way risk debate
- **FastAPI backend**: REST API for the React frontend
- **Debate visualization**: TradingView + Recharts chart integration
- **HITL approval**: Human-in-the-loop gatekeeping + cross-review
- **Broker mock engine**: Simulated trade execution with feedback loop
- **Weekly reflections**: Automated strategy health diagnostics
- **Belief contest engine**: Multi-belief internal competition
- **MCP server**: Expose tools to external AI agents via fastmcp
- **Multi-channel notifications**: Email, Telegram, WeChat, Feishu, Discord, Slack
- **Alpha Zoo integration**: 452 pre-built factor formulas

## Tech Stack

| Category | Technology |
|----------|------------|
| Agent orchestration | LangGraph (StateGraph, ToolNode, MemorySaver → SQLite) |
| LLM backend | OpenAI-compatible API (deepseek-chat, etc.) |
| Backend server | FastAPI |
| Frontend | React 19, Next.js 16, TailwindCSS v4, shadcn/ui |
| Charts | TradingView Lightweight Charts, Recharts |
| Data sources | Yahoo Finance, Google News, AkShare, Finnhub |
| Persistent storage | SQLite (ContextStore, MemoryStore, per-strategy DBs) |
| Caching | Pickle + SHA256 sidecar integrity |
| Scheduling | APScheduler (in-process) |
| Messaging | Email (SMTP), Telegram Bot API |
| Structured output | Pydantic, Zod |
| Package management | uv (Python), npm (frontend) |
| Language | Python 3.12, TypeScript |

## Quick Start

### Prerequisites

- Python 3.12
- Node.js 22+
- A DeepSeek API key (or any OpenAI-compatible key)

### 1. Configure API key

```bash
cp properties.env.example properties.env
```

Edit `properties.env` with your credentials:

```ini
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

> `properties.env` is gitignored — never commit real keys.

### 2. Backend

```bash
# Always clean up old processes before starting
pkill -f uvicorn 2>/dev/null; sleep 1

uv sync
PYTHONPATH=. uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir server --reload-dir agentgraph --reload-dir agents --reload-dir dataflow --reload-dir memory --reload-dir skills --reload-dir storage --reload-dir scheduler
# → http://localhost:8000
# → API docs: http://localhost:8000/docs
```

> **Important**: `PYTHONPATH=.` is required so Python can find the `server` module.
> `--reload-dir` limits file watching to source directories only (avoids watching `.venv`, `data/`, `frontend/`).
> If you hit port conflicts or stale processes, run `pkill -f uvicorn` first.

Verify:

```bash
curl http://localhost:8000/api/health
```

### 3. Frontend

Open a second terminal:

```bash
cd frontend
npm install

# Turbopack cache grows over time → can cause memory explosion on startup.
# Clean it when you see high memory usage or slow startup:
rm -rf .next

# Limit Node.js memory to prevent runaway V8 heap growth
NODE_OPTIONS="--max-old-space-size=2048" npm run dev
# → http://localhost:3000
```

> **Memory tip**: Turbopack's incremental compilation cache (`.next/dev/cache/turbopack/`) accumulates `.sst` files that can reach 1-2 GB. Every startup loads these into RAM. If `next dev` suddenly uses huge memory, `rm -rf .next` fixes it.
>
> The 2GB memory cap is well above normal usage (~80 MB for `next dev`) and prevents runaway heap growth in long-running sessions.

### 4. Test

Open `http://localhost:3000/agent`, ask a question like "What is the current price of AAPL?". Watch the streaming agent response.

### CLI (legacy)

```bash
uv run python app.py AAPL
uv run python app.py TSLA --visualize --verbose
```

## Documentation Map

| For... | Read... |
|--------|---------|
| Understanding the big picture | [`docs/architecture.md`](docs/architecture.md) |
| Data ingestion & storage design | [`docs/data-layer.md`](docs/data-layer.md) |
| Writing frontend code | [`docs/spec.md`](docs/spec.md) + [`docs/api-contracts.md`](docs/api-contracts.md) |
| Writing backend code | [`docs/data-models.md`](docs/data-models.md) + [`docs/architecture.md`](docs/architecture.md) |
| Adding a new agent | [`agents/`](agents/) for patterns + [`agentgraph/state.py`](agentgraph/state.py) |
| Adding a data source | [`dataflow/providers/`](dataflow/providers/) for patterns |
| Reusing reference patterns | [`docs/reusable-assets.md`](docs/reusable-assets.md) |
| Gap analysis & roadmap | [`WORKLOAD_GAP_ANALYSIS.md`](WORKLOAD_GAP_ANALYSIS.md) |
| Getting started | [`docs/README.md`](docs/README.md) |

## Project Structure

```
├── agentgraph/             # LangGraph workflow orchestration
│   ├── orchestrator.py     # Builds & runs the StateGraph
│   ├── state.py            # AgentState: shared state definition
│   └── debate.py           # TODO: Debate state machine
├── agents/                 # AI agent implementations (5 → up to 15)
│   ├── market_analyst.py
│   ├── news_analyst.py
│   ├── fundamentals_analyst.py
│   ├── risk_analyst.py
│   ├── PM.py               # Portfolio manager: Pydantic decision output
│   └── utils/
│       ├── agent_tools.py  # 8 LangChain tools with structured JSON output
│       └── output_prase.py # Pydantic schemas (TradingDecision)
├── dataflow/               # Data service layer
│   ├── service.py          # DataService: unified access with multi-provider routing
│   ├── cache.py            # Pickle cache with SHA256 integrity + TTL
│   ├── utils.py            # Retry with exponential backoff
│   ├── portfolio_manager.py
│   └── providers/          # Data source implementations
│       ├── YFinance.py     # Prices, indicators, fundamentals
│       ├── news_google.py  # Google News scraping
│       ├── fundamentals_akshare.py  # AkShare point-in-time data
│       ├── macro_calendar.py
│       └── sentiment.py    # News sentiment aggregation
├── memory/                 # OWM memory layer
│   ├── models.py           # MemoryRecord, Reflection, PreTradeCheck
│   ├── owm.py              # OWM 5-factor scoring algorithm
│   ├── store.py            # SQLite-backed memory store
│   └── safety.py           # Pre-trade safety checks
├── knowledge/              # Knowledge base
│   └── manager.py          # Rules/findings/failures CRUD + context injection
├── belief/                 # Belief engine
│   ├── models.py           # TradingBelief Pydantic model
│   └── presets.json        # 5 default belief presets
├── skills/                 # Agent skill documentation
│   ├── loader.py           # SKILL.md auto-discovery
│   ├── data-sources/       # yfinance, akshare, data-routing
│   ├── analysis/           # sentiment, fundamental-filter, factor-research, risk
│   └── workflows/          # backtest-diagnose, alpha-zoo, multi-factor
├── mcp/                    # MCP integration
│   ├── base_tool.py        # BaseTool + ToolRegistry (from Vibe-Trading, MIT)
│   └── client.py           # MCPClientManager (stdio/SSE/streamableHttp)
├── storage/                # ContextStore persistence
│   └── store.py            # Per-strategy SQLite DB isolation
├── scheduler/              # Periodic data collection
│   └── __init__.py         # DataCollector (APScheduler, 4 schedules)
├── frontend/               # React frontend (14 pages, 15 routes)
│   ├── app/                # Next.js App Router pages
│   ├── components/         # UI components (33 shadcn/ui + 9 custom)
│   └── lib/                # API client, types, stores, hooks
├── docs/                   # Project documentation
│   ├── README.md           # Documentation index
│   ├── architecture.md     # System architecture
│   ├── data-layer.md       # Data layer design reference
│   ├── data-models.md      # 19 shared data model groups
│   ├── spec.md             # 14-page product specification
│   ├── api-contracts.md    # 19 REST API endpoint groups
│   └── reusable-assets.md  # Reusable code/patterns catalog
├── reports/                # Archived proposal materials (COMP7705)
│   └── detail-proposal/    # Proposal .typ, .pdf, citations
├── archive/                # Superseded files (Streamlit UI, pip requirements)
├── test/                   # Test data and scripts
├── app.py                  # CLI entry point
├── properties.env          # Environment variables (API keys)
├── CLAUDE.md               # AI assistant project instructions
└── WORKLOAD_GAP_ANALYSIS.md # Module-by-module gap analysis
```

## Contributing

1. Read [`docs/README.md`](docs/README.md) for the documentation map
2. Understand the architecture from [`docs/architecture.md`](docs/architecture.md)
3. Choose a task from the gap analysis in [`WORKLOAD_GAP_ANALYSIS.md`](WORKLOAD_GAP_ANALYSIS.md)
4. Backend: follow patterns in existing agents and providers
5. Frontend: follow `docs/spec.md` + `docs/api-contracts.md`, use shadcn/ui components
6. Keep [`docs/data-models.md`](docs/data-models.md) in sync when adding fields

Key conventions:
- **Python**: snake_case, Pydantic for structured output, agents as functions
- **TypeScript**: snake_case field names (match backend), shadcn/ui components
- **All agent output**: Chinese by default
- **Data sources**: Never fabricate data — return empty/Unknown on failure

## License

This project is for academic research purposes. See the proposal in `reports/detail-proposal/` for full context.

---

**Disclaimer**: This system provides analysis for research purposes only. It does not constitute investment advice. All trading involves risk.
