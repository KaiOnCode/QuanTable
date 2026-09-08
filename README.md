<p align="center">
  <a href="https://github.com/KaiOnCode/QuantDebate">
    <img src="https://img.shields.io/badge/version-0.1.0-blue?style=flat-square" alt="Version" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" />
  </a>
  <img src="https://img.shields.io/badge/python-3.12-blueviolet?style=flat-square" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/LangGraph-StateGraph-orange?style=flat-square" alt="LangGraph" />
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=flat-square" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Next.js-Frontend-black?style=flat-square" alt="Next.js" />
</p>

<p align="center">
  <b>English</b> | <a href="README.zh-CN.md">简体中文</a>
</p>

<h1 align="center">QuantDebate</h1>

<p align="center">
  A multi-agent framework for reasoning-based quantitative analysis.<br/>
  Debate-driven investment decisions powered by LLM agents.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#architecture">Architecture</a> &middot;
  <a href="#features">Features</a> &middot;
  <a href="#documentation">Docs</a> &middot;
  <a href="#contributing">Contributing</a>
</p>

---

## What is QuantDebate

QuantDebate is a research platform where multiple LLM agents collaborate to analyze stocks and produce investment decisions. Instead of asking a single model for a buy/sell recommendation, it orchestrates a structured debate: analysts present evidence, bull and bear researchers argue opposing cases, a risk committee evaluates downside scenarios, and a portfolio manager makes the final call.

The system ships with two agent pipelines that share the same data layer and tool infrastructure. A custom ReAct harness handles single-stock deep dives with streaming execution and automatic error recovery. A LangGraph 12-agent pipeline runs multi-agent debate across four analysis stages, producing structured investment memos with three depth modes.

This project was built as a final year project at the University of Hong Kong (COMP7705).

---

## Architecture

```
                           React Frontend (16 pages)
                          / Agent | Quick Ask | Backtest \
                                       |
                                  REST + SSE
                                       |
                            +----------+----------+
                            |   FastAPI Server     |
                            +----------+----------+
                                       |
            +--------------------------+--------------------------+
            |                                                     |
   Custom ReAct Harness (agent/)              LangGraph Pipeline (quick_ask/)
   +---------------------------+             +---------------------------+
   | 25-iteration loop         |             | Stage 1: 4 Analysts      |
   | Streaming tool execution  |             | Stage 2: Bull vs Bear     |
   | 5-layer context compression|            | Stage 3: Trader           |
   | Automatic error recovery  |             | Stage 4: 3-way Risk       |
   | 21+ financial tools       |             | Stage 5: PM Decision      |
   +---------------------------+             +---------------------------+
            |                                                     |
            +-------------------- Shared Layer --------------------+
                 dataflow / memory / storage / scheduler / skills
```

### Agent Pipeline (12 agents, 3 depth modes)

```
Stage 1:  Market  ->  Sentiment  ->  News  ->  Fundamentals
          (sequential, isolated tool loops)

Stage 2:  Bull Researcher <-> Bear Researcher  (multi-round debate)
          ->  Research Manager  (investment plan)

Stage 3:  Trader  (trading proposal)

Stage 4:  Aggressive <-> Conservative <-> Neutral Risk  (multi-round discussion)
          ->  Risk Analyst  (risk report)

Stage 5:  Portfolio Manager  (final BUY / HOLD / SELL)
```

The three depth modes control debate intensity:

| Mode | Debate Rounds | Risk Discussion | Typical Latency |
|------|:---:|:---:|:---:|
| Fast | 1 | Single pass | ~30s |
| Standard | 2 | 2 rounds | ~60s |
| Deep | 3 | 3 rounds | ~120s |

---

## Features

**Agent Terminal** -- Interactive ReAct analysis with 21+ financial tools: price data, technical indicators, fundamentals, balance sheet, cash flow, news, sentiment, sector context, web search, and more. Supports streaming output with automatic recovery on tool failures.

**Quick Ask** -- One-click structured analysis via the 12-agent LangGraph pipeline. Select fast, standard, or deep mode to control analysis depth and debate intensity.

**Data Layer** -- Multi-source ingestion from Yahoo Finance, Google News RSS, AkShare, and Finnhub with provider fallback. SQLite-backed caching with SHA256 integrity verification. APScheduler-based periodic collection for prices, news, sentiment, and macro data.

**Memory System** -- Cross-session persistent memory with OWM 5-factor scoring. Pre-trade safety checks that inject historical lessons before decisions. Context compression that preserves key findings across long analysis sessions.

**Skills** -- 76 SKILL.md documents across 10 categories (technical analysis, fundamentals, macro, risk, etc.) that agents load dynamically to guide their analysis methodology.

**Frontend** -- 16-page Next.js 16 application with shadcn/ui and TailwindCSS v4. Includes agent terminal, quick ask, backtest, morning brief, stock scanner, memory viewer, and approval management.

**Backtest** -- MockBrokerEngine with next-open execution, hash-verified reproducibility, VaR/CVaR risk analytics, and PDF report generation.

**Risk Management** -- Human-in-the-loop approval system with rule-triggered gates (position change, confidence threshold, concentration limit). State machine for approval workflows.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Agent Orchestration | Self-built ReAct loop + LangGraph StateGraph |
| LLM Backend | OpenAI-compatible API (DeepSeek) |
| Backend | FastAPI + uvicorn |
| Frontend | Next.js 16 + React + TypeScript + shadcn/ui |
| Data Sources | Yahoo Finance, Google News RSS, AkShare, Finnhub |
| Storage | SQLite (ContextStore, MarketDataStore, MemoryStore) |
| Scheduling | APScheduler |
| Structured Output | Pydantic |
| Package Management | uv (Python), npm (frontend) |

---

## Quick Start

### Prerequisites

- Python 3.12
- Node.js 22+
- A DeepSeek API key (or any OpenAI-compatible key)

### 1. Clone and configure

```bash
git clone https://github.com/KaiOnCode/QuantDebate.git
cd QuantDebate
cp properties.env.example properties.env
```

Edit `properties.env` with your API credentials:

```ini
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

> `properties.env` is gitignored. Never commit real API keys.

### 2. Start the backend

```bash
uv sync
PYTHONPATH=. uv run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open the app

Navigate to `http://localhost:3000`:

- `/agent` -- Interactive ReAct agent terminal
- `/quick-ask` -- Structured multi-agent analysis (3 modes)

---

## Project Structure

```
QuantDebate/
+-- agent/                  # Custom ReAct harness (ACTIVE)
|   +-- loop.py             #   25-iteration ReAct loop engine
|   +-- state.py            #   AgentLoopState + TransitionType
|   +-- compression.py      #   5-layer context compression
|   +-- progress.py         #   HeartbeatTimer + progress events
|   +-- trace.py            #   JSONL trace recording
|   +-- tools/              #   21+ financial and workspace tools
+-- quick_ask/              # LangGraph 12-agent pipeline (LEGACY)
|   +-- orchestrator.py     #   IntelliFin_Assistant (StateGraph)
|   +-- state.py            #   AgentState (MessagesState)
|   +-- agents/             #   5 agent modules
+-- skills/                 # 76 SKILL.md documents (shared)
+-- dataflow/               # Data providers and collection
+-- memory/                 # Cross-session persistent memory
+-- storage/                # SQLite persistence layer
+-- scheduler/              # APScheduler-based data collection
+-- server/                 # FastAPI backend
|   +-- main.py             #   Application entry point
|   +-- routes/             #   REST and SSE endpoints
+-- frontend/               # Next.js 16 frontend
+-- data/                   # Runtime data (gitignored)
+-- test/                   # Test suite
+-- docs/                   # Architecture and design docs
```

---

## Documentation

| Topic | File |
|-------|------|
| Architecture overview | [`docs/architecture.md`](docs/architecture.md) |
| Data models | [`docs/data-models.md`](docs/data-models.md) |
| API contracts | [`docs/api-contracts.md`](docs/api-contracts.md) |
| Frontend spec | [`docs/spec.md`](docs/spec.md) |
| Development plan | [`docs/development-plan.md`](docs/development-plan.md) |
| Adding a data source | [`dataflow/providers/`](dataflow/providers/) |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and PR guidelines.

---

## Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| Phase 1 | Data foundation (market data REST, APScheduler) | In Progress |
| Phase 2 | Frontend-backend integration (SSE streaming, all pages) | Planned |
| Phase 3 | Memory injection into agent pipeline | Planned |
| Phase 4 | Backtest engine with real broker connectors | Planned |
| Phase 5 | Production deployment and monitoring | Planned |

---

## License

MIT License -- see [LICENSE](LICENSE) for details.

---

**Disclaimer**: QuantDebate is research software for educational purposes. It does not constitute investment advice, does not hold funds, and does not execute real trades. Past performance does not guarantee future results. Use at your own risk.
