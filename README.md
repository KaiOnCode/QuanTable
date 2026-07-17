# Agentic-Quant

**A multi-agent framework for reasoning-based quantitative analysis.**

A self-built ReAct harness (25-iteration loop, streaming tool execution, 5-layer compression, error recovery) and a LangGraph 12-agent debate pipeline (4 sequential analysts → bull/bear debate → trader → 3-way risk discussion → PM) collaborate to produce verifiable investment decisions with three depth modes (fast/standard/deep).

*University of Hong Kong — COMP7705 Final Year Project*

---

## System Architecture

```
                          ┌─ React Frontend (16 pages) ──┐
                          │  Agent │ Quick Ask │ Backtest  │
                          └──────────────┬────────────────┘
                                    REST + SSE
                          ┌──────────────▼────────────────┐
                          │        FastAPI Server          │
                          └──────────────┬────────────────┘
                                         │
    ┌────────────────────────────────────┼──────────────────────────────────┐
    │                    Dual-Track Agent Architecture                       │
    │                                                                       │
    │  Custom Harness (`agent/`)         LangGraph Pipeline (`quick_ask/`)  │
    │  ┌─────────────────────┐          ┌──────────────────────────────┐    │
    │  │ ReAct Loop           │          │ Stage 1: 4 Analysts (serial) │    │
    │  │   → 5-phase iteration│          │ Stage 2: Bull↔Bear Debate    │    │
    │  │   → 21+ tools        │          │ Stage 3: Trader              │    │
    │  │   → Streaming exec   │          │ Stage 4: 3-Way Risk Debate   │    │
    │  │   → Recovery machine │          │ Stage 5: PM Decision         │    │
    │  └─────────────────────┘          └──────────────────────────────┘    │
    │                                                                       │
    │  SHARED: dataflow / memory / storage / scheduler / skills             │
    └───────────────────────────────────────────────────────────────────────┘
```

**Agent Pipeline (12 agents, 3 depth modes):**

```
Stage 1: Market → Sentiment → News → Fundamentals (sequential, isolated tool loops)
Stage 2: Bull Researcher ↔ Bear Researcher (multi-round debate)
         → Research Manager (investment plan)
Stage 3: Trader (trading proposal)
Stage 4: Aggressive ↔ Conservative ↔ Neutral Risk (multi-round discussion)
         → Risk Analyst (risk report)
Stage 5: Portfolio Manager (final BUY/HOLD/SELL)
```

---

## Current Status

### Done

- **Custom Harness (`agent/`)**: ReAct loop with 21+ tools, streaming executor, 5-layer compression, recovery state machine, 7-section prompt engineering
- **LangGraph Pipeline (`quick_ask/`)**: 12-agent TradingAgents-style pipeline, 3 modes (fast/standard/deep), debate + risk discussion
- **Data ingestion**: Yahoo Finance, Google News RSS, AkShare, Finnhub with multi-provider fallback
- **Data cache**: SQLite MarketDataStore + Pickle with SHA256 integrity
- **News**: Multi-source merging (Yahoo Finance + Google News RSS), cache-first with live fallback
- **Sentiment**: Keyword-based news sentiment aggregation (16 bullish / 16 bearish terms)
- **14 agent tools**: price, indicators, fundamentals, balance sheet, cash flow, income statement, verified market snapshot, news, global news, macro indicators, sentiment, sector, web search, symbol search
- **React frontend**: 16 pages (Next.js 16 + shadcn/ui + TailwindCSS v4)
- **Memory layer**: OWM 5-factor scoring, SQLite store, pre-trade safety checks
- **ContextStore**: SQLite persistence with per-strategy database isolation
- **Data collector**: APScheduler-based periodic fetching (price/news/sentiment/macro)
- **76 Skills**: 10 categories of SKILL.md documents
- **Bash/shell optional tools**: read_file, write_file, glob, bash (gated)
- **Knowledge base**: Rules/findings/failures CRUD
- **Belief system**: Trading belief models + presets
- **MCP integration**: BaseTool + ToolRegistry + MCPClientManager
- **HITL approval**: Rule-triggered approval state machine
- **Backtest engine**: MockBrokerEngine with next-open execution, hash-verified reproducibility
- **Risk analytics**: VaR, CVaR, correlation matrix, stress testing
- **Scanner**: Deterministic stock scanning with rule/agent/belief modes
- **PDF reporting**: fpdf2 + Jinja2 templates + Chinese font support
- **Multi-channel notifications**: Email, Telegram, WeChat, WhatsApp
- **Documentation**: Architecture, data models, spec, API contracts, progress log

---

## Tech Stack

| Category | Technology |
|----------|------------|
| Agent orchestration | Self-built ReAct loop + LangGraph StateGraph |
| LLM backend | OpenAI-compatible API (deepseek-chat) |
| Backend server | FastAPI + uvicorn |
| Frontend | Next.js 16 + React + TypeScript + shadcn/ui + TailwindCSS v4 |
| Charts | Recharts + TradingView Lightweight Charts |
| Data sources | Yahoo Finance, Google News RSS, AkShare, Finnhub |
| Persistent storage | SQLite (ContextStore, MarketDataStore, MemoryStore) |
| Scheduling | APScheduler (in-process) |
| Structured output | Pydantic |
| Package management | uv (Python), npm (frontend) |
| Language | Python 3.12, TypeScript |

---

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
pkill -f uvicorn 2>/dev/null; sleep 1
uv sync
PYTHONPATH=. uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Test

- Agent terminal: `http://localhost:3000/agent` — interactive ReAct analysis
- Quick Ask: `http://localhost:3000/quick-ask` — structured multi-agent analysis (3 modes)

---

## Documentation Map

| For... | Read... |
|--------|---------|
| Architecture overview | [`docs/architecture.md`](docs/architecture.md) |
| Development progress | [`docs/PROGRESS.md`](docs/PROGRESS.md) |
| Data models | [`docs/data-models.md`](docs/data-models.md) |
| API contracts | [`docs/api-contracts.md`](docs/api-contracts.md) |
| Frontend spec | [`docs/spec.md`](docs/spec.md) |
| Architecture comparison | [`docs/architecture-comparison.md`](docs/architecture-comparison.md) |
| Adding a data source | [`dataflow/providers/`](dataflow/providers/) |

---

## Key Conventions

- Agents access data through `DataService`, never call providers directly
- Pydantic for all structured output
- All agent output in Chinese
- Never fabricate financial data — return empty/error on failure
- Snake_case field names in JSON API (frontend and backend must match)
- Default initial capital: $100,000 USD (backtest)

---

**Disclaimer**: This system provides analysis for research purposes only. It does not constitute investment advice.
