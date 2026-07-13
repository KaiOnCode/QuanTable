# System Architecture

## Overview

Single-process FastAPI monolith with in-process scheduler. Frontend is a separate React app. All components share the same Python process — no Redis, no Celery, no Docker required in dev.

```
┌─────────────────────────── React Frontend ──────────────────────────┐
│  Dashboard │ Strategies │ Quick Ask │ Backtest │ Memory Lab │ ...    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ REST + SSE
                               ▼
┌────────────────────────── FastAPI Server ───────────────────────────┐
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    REST Routes (/api/*)                         │  │
│  │  analyze │ strategies │ portfolios │ backtest │ approvals     │  │
│  │  memory │ knowledge │ skills │ beliefs │ scanner │ risk       │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │                                        │
│  ┌──────────────────────────┼────────────────────────────────────┐  │
│  │                    Service Layer                                │  │
│  │                                                                  │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────┐  │  │
│  │  │ Orchestrator│  │  Broker      │  │  HITL Manager         │  │  │
│  │  │ (LangGraph, │  │  Engine      │  │  Risk triggers +       │  │  │
│  │  │  5-15       │  │  Order mgmt  │  │  Cross-review +       │  │  │
│  │  │  agents)    │  │              │  │  Approval FSM          │  │  │
│  │  └──────┬──────┘  └──────┬───────┘  └──────────┬────────────┘  │  │
│  │         │                │                      │                │  │
│  │  ┌──────┴────────────────┴──────────────────────┴────────────┐  │  │
│  │  │                 ContextStore (SQLite)                      │  │  │
│  │  │  sessions │ reports │ decisions │ trades │ approvals       │  │  │
│  │  │  events (audit trail) │ conversations                     │  │  │
│  │  └────────────────────────────────────────────────────────────┘  │  │
│  │                                                                  │  │
│  │  ┌───────────────┐  ┌──────────────┐  ┌────────────────────┐    │  │
│  │  │ Memory Layer  │  │ Knowledge    │  │ Skill System       │    │  │
│  │  │ OWM scoring   │  │ Base         │  │ SKILL.md loader    │    │  │
│  │  │ 5-layer store │  │ rules/       │  │ Agent capability   │    │  │
│  │  │ Pre-trade     │  │ findings/    │  │ registry           │    │  │
│  │  │ safety rails  │  │ failures     │  │                    │    │  │
│  │  └───────────────┘  └──────────────┘  └────────────────────┘    │  │
│  │                                                                  │  │
│  │  ┌───────────────┐  ┌──────────────┐  ┌────────────────────┐    │  │
│  │  │ Belief Engine │  │ MCP Server   │  │ MCP Client         │    │  │
│  │  │ Trading       │  │ Expose tools │  │ Load external      │    │  │
│  │  │ philosophy    │  │ to external  │  │ MCP tools into     │    │  │
│  │  │ → agent bias  │  │ agents       │  │ agent registry     │    │  │
│  │  └───────────────┘  └──────────────┘  └────────────────────┘    │  │
│  │                                                                  │  │
│  │  ┌───────────────┐  ┌──────────────┐  ┌────────────────────┐    │  │
│  │  │ DataService   │  │ Scheduler    │  │ Notification        │    │  │
│  │  │ YFinance      │  │ APScheduler  │  │ Email │ Telegram    │    │  │
│  │  │ Google News   │  │ Strategy     │  │ WeChat │ Feishu     │    │  │
│  │  │ AkShare       │  │ triggers     │  │ Discord │ Slack     │    │  │
│  │  │ Fallback      │  │ Daily briefs │  │                    │    │  │
│  │  └───────────────┘  └──────────────┘  └────────────────────┘    │  │
│  │                                                                  │  │
│  │  ┌───────────────┐  ┌──────────────┐  ┌────────────────────┐    │  │
│  │  │ Quant Engine  │  │ Scanner      │  │ Report Gen          │    │  │
│  │  │ Classic       │  │ Rule-based   │  │ Deep research       │    │  │
│  │  │ strategies    │  │ Agent-driven │  │ PDF export          │    │  │
│  │  │ + Alpha Zoo   │  │              │  │                    │    │  │
│  │  └───────────────┘  └──────────────┘  └────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Storage Layer                                  │  │
│  │  system.db          — global config, strategy registry, beliefs  │  │
│  │  insights.db        — daily briefs, news archives               │  │
│  │  memory.db          — OWM memory store, reflections, audit log   │  │
│  │  knowledge.db       — rules, findings, failures, hypotheses      │  │
│  │  data/{strategy_id}.db — per-strategy: account, position, order, │  │
│  │                          trade, approval, event, performance      │  │
│  │  data/chat_{uuid}.db — per-conversation history                  │  │
│  │  skills/            — SKILL.md files (agent capabilities)        │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Orchestrator (`agentgraph/`)

LangGraph StateGraph with up to 15 agent nodes. Runs as a synchronous call wrapped in `asyncio.to_thread()` for non-blocking async handlers.

**Expanded Agent Pipeline** (inspired by TradingAgents-MCPmode, ContestTrade):

```
START
  │
  ├── [Company Overview Analyst]        ← sets context (ticker, sector, market cap)
  │
  ├── [Market │ News │ Fundamentals │ Sentiment │ Technical │ Macro] (parallel 6)
  │         ↓
  ├── [Bull Researcher │ Bear Researcher] (debate, configurable rounds)
  │         ↓
  ├── [Research Manager]                ← synthesizes debate → investment plan
  │         ↓
  ├── [Trader]                          ← plan → executable orders
  │         ↓
  ├── [Aggressive Risk │ Safe Risk │ Neutral Risk] (3-way risk debate)
  │         ↓
  ├── [Risk Manager]                    ← final risk sign-off
  │         ↓
  └── [PM Agent]                        ← final decision (Pydantic output)
         ↓
       END
```

**Key changes from original 5-agent pipeline:**
- Analysts expanded from 3 to 6 (added Sentiment, Technical, Macro)
- Added Company Overview as pre-analysis context setter
- Added Bull/Bear Researcher debate round (from TradingAgents)
- Added 3-way Risk debate (Aggressive/Safe/Neutral) before final PM decision
- All parallel stages use `asyncio.gather` internally

**Agent configuration:**
- Users can enable/disable specific agents per strategy (frontend toggle)
- Debate rounds configurable (1-5 rounds, default 2)
- Each agent can be assigned to different LLM models (deep think vs quick think)

**Agent debate mode** (from TradingAgents):
- Bull and Bear researchers receive all analyst reports
- Structured debate: Claim → Evidence → Rebuttal → Synthesis
- Research Manager reads full debate history, produces investment plan
- Risk debate follows same pattern with 3 risk stances

### 2. Memory Layer (`memory/`)

Inspired by **TradeMemory Protocol**. This is the "learning from experience" infrastructure.

**OWM Framework** (Outcome-Weighted Memory):
Five factors weight how memories are retrieved:
1. **Outcome quality** — how profitable was the past trade?
2. **Context similarity** — how similar are current market conditions?
3. **Recency** — how long ago did this happen?
4. **Confidence** — how confident was the original decision?
5. **Emotional state** — was the decision made under stress? (optional, for HITL)

**Five memory layers:**
```
MemoryRecord
├── episodic     — "On 2024-01-15, bought AAPL at $185, sold at $192 (+3.8%)"
├── semantic     — "AAPL tends to rally after positive earnings surprises"
├── procedural   — "When RSI < 30 and news sentiment > 0.6, consider buying"
├── affective    — "High volatility period: position sizing reduced"
└── trade_record — Raw data: ticker, date, action, price, quantity, PnL
```

**Pre-trade safety rails:**
- `check_trade_legitimacy(ticker, action, size)` → 5-factor gate
- Drawdown alerts: if strategy drawdown > threshold, block new positions
- Losing streak detection: N consecutive losses → reduce position size
- Concentration check: single ticker > max allocation → warn

**Reflection cycle** (per strategy execution):
```
Before analysis → recall_memories(ticker, current_conditions)
  → inject relevant past lessons into PM prompt
After execution → remember_trade(decision, outcome)
  → write to all 5 memory layers
Periodic (weekly) → reflect_on_period()
  → detect behavioral drift, strategy decay
```

### 3. Knowledge Base (`knowledge/`)

Inspired by **QuantGPT** and **Vibe-Trading Hypothesis Registry**.

Each strategy maintains a structured knowledge base:
```
data/{strategy_id}/knowledge/
├── rules.md       # Verified stable rules (must follow)
├── findings.md    # Empirical discoveries (reference)
└── failures.md    # Falsified paths (avoid repeating)
```

**Hypothesis lifecycle** (from Vibe-Trading):
```
draft → active → validating → confirmed | rejected | stale
```

Hypotheses carry: claim, acceptance criteria, evidence rows (linked to backtests/runs), budget, completion policy. The agent reads active hypotheses before each run and can attach new evidence.

### 4. Skill System (`skills/`)

Inspired by **Vibe-Trading** (75 SKILL.md files) and **AI-Trader** (agent registration via SKILL.md).

Instead of hardcoding agent capabilities, each agent's tools, prompts, and workflow are defined as SKILL.md files:

```
skills/
├── analysis/
│   ├── technical-analysis.skill.md
│   ├── fundamental-analysis.skill.md
│   ├── sentiment-analysis.skill.md
│   ├── macro-analysis.skill.md
│   └── news-analysis.skill.md
├── strategy/
│   ├── ma-cross.skill.md
│   ├── rsi-reversal.skill.md
│   ├── ts-momentum.skill.md
│   └── risk-parity.skill.md
├── risk/
│   ├── var-cvar.skill.md
│   ├── stress-test.skill.md
│   └── correlation.skill.md
└── research/
    ├── stock-deep-dive.skill.md
    └── sector-analysis.skill.md
```

Each SKILL.md follows a standard format:
```markdown
---
name: technical-analysis
version: 1.0
category: analysis
tools: [get_prices, get_indicators]
model: deepseek-chat
temperature: 0.0
---

# Technical Analysis Skill
... (prompt template + workflow)
```

Skills can be created, edited, and versioned by users. The Skill loader auto-discovers skills at startup and makes them available to strategy configuration.

### 5. Belief Engine (`belief/`)

Inspired by **ContestTrade**. Users define "trading beliefs" (trading philosophies) that bias how agents make decisions.

Beliefs are **natural language** JSON strings, not enums. This is more flexible than our original `StrategyType` enum:

```json
{
  "beliefs": [
    "专注于短期事件驱动机会：优先关注公司公告、并购重组、订单暴增等催化事件；偏好中小市值、高波动的题材股。",
    "专注于稳健的价值投资：关注低PE、高股息、稳定现金流的蓝筹股；偏好长期持有。"
  ]
}
```

Each belief spawns a separate Research Agent perspective. The internal contest mechanism (from ContestTrade) evaluates which belief produces the best signals.

**Belief → Agent mapping:**
- Each belief string is assigned to one Research Agent in the debate phase
- Multiple beliefs → multiple Research Agents, each arguing from their philosophy
- The Research Manager weights their contributions based on historical performance

### 6. MCP Server (`mcp/`)

Inspired by **Vibe-Trading** (22 MCP tools) and **TradeMemory Protocol** (17 MCP tools).

Expose Agentic-Quant's capabilities as MCP tools so external AI agents (Claude Desktop, Cursor, OpenClaw, etc.) can use them:

```
MCP Tools (stdio / SSE / streamable-http):
├── analyze_ticker(ticker, date, mode) → TradingDecision
├── get_market_data(ticker, lookback) → OHLCV + indicators
├── get_news(ticker, window_days) → news articles
├── get_fundamentals(ticker, date) → financial metrics
├── run_backtest(strategy_config, tickers, date_range) → results
├── scan_market(conditions, universe) → matching tickers
├── get_risk_report(strategy_id) → VaR, stress test, correlation
├── recall_memory(ticker, conditions) → relevant past decisions
├── search_knowledge(query) → relevant rules/findings
└── generate_report(ticker, sections, format) → PDF
```

### 7. MCP Client Mode

Inspired by **Vibe-Trading**'s MCP client mode. The built-in agent can load external MCP tools into its registry:

```json
// ~/.agentic-quant/agent.json
{
  "mcpServers": {
    "financial-datasets": {
      "command": "uvx",
      "args": ["financial-datasets-mcp"]
    },
    "tradememory": {
      "command": "uvx",
      "args": ["tradememory-protocol"]
    }
  }
}
```

External tools appear as `mcp_<server>_<tool>` in the agent's tool registry. This makes the system extensible without modifying core code.

### 8. Broker Engine (`broker/`)

Virtual exchange. All strategy types (agent/quant/HITL) trade through the same gateway interface.

```python
class BrokerGateway:
    def create_account(initial_balance) -> Account
    def place_order(account_id, ticker, side, qty, type, limit_price) -> Order
    def cancel_order(order_id) -> bool
    def get_positions(account_id) -> dict[str, Position]
    def get_account(account_id) -> Account
    def get_performance(account_id, period) -> PerformanceMetrics
    def get_order_history(account_id, filters) -> list[Order]
```

Order lifecycle: `PENDING → EXECUTED | PARTIALLY_FILLED | REJECTED | CANCELLED`

The generic gateway is an exchange abstraction; its capabilities do not define
the persisted backtest contract. Canonical persisted backtests use this
gateway through a deliberately narrower, frozen execution policy:

- Deterministic v1 accepts only typed quant policies and is long-only.
- A signal may use the historical session close, but any resulting market
  order executes at the next available historical session open; it never
  fills on the signal bar.
- Initial cash, commission, slippage, maximum position, timing, policy, and
  data provenance are frozen with the run before it is queued.
- Pending, rejected, cancelled, and end-of-window-unfilled orders remain
  explicit evidence. A zero-trade or experimental result is not credible
  performance merely because the job reached a terminal state.

### 9. HITL Manager (`hitl/`)

Intercepts PM decisions for strategies with HITL enabled. Enhanced with **dual-LLM cross-review** (from QuantGPT).

```
PM Decision → Risk Rule Engine
  ├── Low risk → Auto-execute via Broker
  └── High risk → Cross-Review (2nd LLM)
                    ├── Consensus → HITL Queue (human approval)
                    └── Divergence → Flag for human with both analyses
```

Risk triggers (configurable per strategy):
- Position size change exceeds threshold
- Signal conflict detected (analyst disagreement → debate didn't resolve)
- Confidence score below threshold
- Single-ticker concentration exceeds limit

**Dual-LLM Cross-Review** (from QuantGPT):
- For HITL-triggered decisions, a second LLM (different model or higher temperature) independently reviews the first LLM's reasoning chain
- Consensus → proceed to human approval with confidence note
- Divergence → present both analyses to human reviewer, flag for careful review
- This reduces confirmation bias in high-stakes decisions

### 10. Scheduler (`scheduler/`)

APScheduler running in-process. Handles:
- Periodic strategy executions (per-strategy configurable: hourly, daily, weekly)
- Daily insight generation (8:00 AM + 12:30 PM market time)
- News scraping intervals
- Data cleanup jobs
- Memory reflection cycles (weekly)

### 11. DataService (`dataflow/`)

Unified data access with multi-provider fallback. This is the anti-hallucination layer.

```
DataService
├── get_prices(ticker, lookback, end_date)
│   Primary: Yahoo Finance
│   Fallback: local CSV cache
│   On failure: return empty + error flag (NEVER fabricate)
│
├── get_news(ticker, window_days)
│   Primary: Google News scraping
│   Fallback: cached news from previous fetch
│   On failure: return empty list + "No news available" flag
│
├── get_fundamentals(ticker, end_date)
│   Live: Yahoo Finance snapshot
│   Historical: AkShare point-in-time
│   On failure: return partial data with "Unknown" markers
│
├── get_indicators(ticker, lookback)
│   Computed from price data
│
├── get_macro_calendar(days)
│   Source: Finnhub economic calendar
│   On failure: return empty
│
└── get_sentiment(ticker, window_days)
    Source: Google News sentiment aggregation
    On failure: return neutral with "Unknown" flag
```

**Critical rule**: Data functions NEVER return fabricated data. If all sources fail, they return empty results with explicit error flags. Agent prompts instruct agents to say "Unknown: [field]" when data is missing.

### 12. ContextStore (`storage/`)

SQLite-based persistence replacing MemorySaver.

Database layout (updated):
- `system.db` — strategy registry, user settings, global config, beliefs
- `insights.db` — daily briefs, scraped news archive
- `memory.db` — OWM memory records, reflections, pre-trade safety state
- `knowledge.db` — rules, findings, failures, hypotheses
- `data/{strategy_id}.db` — per-strategy: account, position, order, trade, decision, event, performance
- `data/chat_{uuid}.db` — per-conversation history

### 13. Quant Engine (`quant/`)

Pure-Python strategy functions + **Alpha Zoo** (from Vibe-Trading).

```python
@register_strategy("ma_cross")
def strategy_ma_cross(prices: pd.DataFrame, params: dict) -> Signal:
    """50/200-day moving average crossover"""

@register_strategy("rsi_reversal")
def strategy_rsi_reversal(prices: pd.DataFrame, params: dict) -> Signal:
    """RSI mean reversion (oversold buy, overbought sell)"""

@register_strategy("ts_momentum")
def strategy_ts_momentum(prices: pd.DataFrame, params: dict) -> Signal:
    """Time series momentum (Moskowitz 2012)"""

@register_strategy("vol_targeting")
def strategy_vol_targeting(prices: pd.DataFrame, params: dict) -> Signal:
    """Volatility-targeted position sizing"""

@register_strategy("risk_parity")
def strategy_risk_parity(prices: pd.DataFrame, params: dict) -> Signal:
    """Equal risk contribution across assets"""
```

**Alpha Zoo** — pre-built factor library (452 formulas):
| Zoo | Count | Source |
|-----|-------|--------|
| Qlib158 | 154 | Microsoft Qlib Alpha158 |
| Alpha101 | 101 | Kakushadze 101 Formulaic Alphas |
| GTJA191 | 191 | Guotai Junan short-horizon factors |
| Academic | 6 | Fama-French 5 + Carhart momentum |

Users can select factors from the zoo when creating quant strategies, or use them as features for agent analysis.

### 14. Scanner (`scanner/`)

Two modes:
- **Rule-based**: User defines conditions (RSI < 30, PE < 15, market cap > 10B) → filter universe
- **Agent-driven**: User describes in natural language → agent interprets → runs targeted searches
- **Belief-driven** (new): User's trading beliefs auto-generate scanner queries matching their philosophy

### 15. Report Generator (`reports/`)

Generates structured research reports:
- Individual stock deep dive (10-15 pages, all agent outputs + charts)
- Industry/sector reports (auto-discovers relevant tickers, analyzes each)

### 16. Notification (`notification/`)

Abstract adapter with multi-channel implementations (expanded from Daily Stock Analysis):
- `send_alert(message, priority)` — time-sensitive HITL alerts
- `send_daily_brief(message)` — morning/midday insights (HTML email)
- `send_approval_request(decision)` — HITL approval with deep link

Channels:
- Email (SMTP, HTML format)
- Telegram Bot
- Enterprise WeChat (企业微信机器人)
- Feishu (飞书机器人)
- Discord Webhook
- Slack Bot

## Data Flow Patterns

### Pattern A: Quick Ask (single analysis)
```
User input → POST /api/analyze → SSE stream
  → Orchestrator.run() → up to 15 agents execute → PM decision
  → Memory.recall() injected into PM prompt
  → [Optional] Save to chat_{uuid}.db
  → Memory.remember() after result
  → Return final result
```

### Pattern B: Strategy Execution (scheduled)
```
APScheduler triggers → For each ticker in strategy:
  → Memory.recall(ticker, conditions) → inject past lessons
  → Orchestrator.run() → Belief Engine biases Research Agents
  → Internal Contest: multiple beliefs compete → best signal selected
  → PM decision
  → Pre-trade safety check (drawdown, streak, concentration)
  → HITL check (if enabled)
    → Cross-review (2nd LLM)
    → HITL queue or auto-execute
  → Broker.place_order() or skip
  → Memory.remember(decision, outcome)
  → All results → strategy_id.db
```

### Pattern C: Backtesting
```
User selects one eligible Strategy + date range + ticker
  → Freeze typed policy, broker config, Strategy snapshot, and request
    as BacktestRunSpec
  → Load and persist normalized target/benchmark OHLCV plus policy warm-up
  → For each eligible historical signal session:
    → Build point-in-time features from data at or before that session close
    → Deterministic policy emits a declared target
      (agent mode is explicitly experimental)
    → Broker executes a resulting order only at the next historical open
  → Persist decisions, orders, fills, closed trades, equity, metrics,
    and provenance
  → Verify/replay only the frozen snapshot; return fidelity and
    sample-truthfulness evidence
```

The canonical deterministic path does not invoke an LLM for each bar and does
not claim prediction accuracy or out-of-sample robustness. Those questions
require a separately specified research protocol.

### Pattern D: Daily Insights
```
APScheduler @ 8:00 / 12:30
  → DataService fetches market snapshot + news
  → Special "daily brief" prompt → PM_agent
  → Notification.send_daily_brief() → multi-channel
  → Store to insights.db
```

### Pattern E: Memory Reflection (weekly)
```
APScheduler @ Sunday 18:00
  → For each active strategy:
    → Aggregate week's trades
    → Detect behavioral drift (disposition effect, overtrading, anchoring)
    → Detect strategy decay (declining win rate, increasing drawdown)
    → Generate reflection report
    → Update knowledge base (rules/findings/failures)
```

### Pattern F: Belief Contest (per strategy execution)
```
For each ticker in strategy:
  → Load strategy's belief list
  → Spawn Research Agent per belief
  → Each agent analyzes from its philosophical perspective
  → Internal contest: score each agent's proposal
  → Weighted synthesis → PM decision
```

## Key Design Decisions

1. **Monolith, not microservices** — simpler dev, one process to debug. Can extract services later.
2. **APScheduler in-process** — no external cron for dev. Migrate to Celery Beat for production.
3. **Per-strategy SQLite** — isolation by design. Delete strategy = delete one file.
4. **SSE, not WebSocket** — agent execution is one-directional streaming, not bidirectional.
5. **Pydantic as type bridge** — frontend TS types can be generated from backend Pydantic models.
6. **Data never fabricated** — explicit Unknown markers in agent output when data is unavailable.
7. **Broker as singleton** — all strategies share one broker instance. Account isolation by account_id.
8. **Memory layer is first-class** — every decision is recorded and recalled. OWM scoring ensures relevant memories surface.
9. **Beliefs over enums** — natural language trading philosophies are more flexible and user-friendly than hardcoded strategy types.
10. **Skills over hardcoded agents** — agent capabilities defined as SKILL.md files, auto-discovered at startup.
11. **MCP for interoperability** — expose tools via MCP so external agents can use them; load external MCP tools for extensibility.
12. **Dual-LLM cross-review** — second LLM reviews high-risk decisions before human approval, reducing confirmation bias.

## Anti-Hallucination Design

1. **Data layer**: Functions return empty, never fabricate. Error flags are explicit.
2. **Agent prompts**: Every agent prompt includes "只使用输入事实；未知项以'Unknown: …'标注并说明影响" (only use provided facts; mark unknowns explicitly).
3. **Structured output**: PM uses Pydantic schema, not free text. Direction/position are typed fields.
4. **Audit trail**: Every tool call, data retrieval, and agent output is logged in the events table.
5. **Source attribution**: News items carry source URLs. Fundamental data carries report dates.
6. **Cross-review**: High-risk decisions reviewed by independent second LLM before execution.

## MCP Integration (Interoperability)

### Exposing tools (MCP Server)
Agentic-Quant tools exposed to external AI agents via MCP (stdio / SSE / streamable-http):
- `analyze_ticker` — full multi-agent analysis
- `get_market_data` — OHLCV + technical indicators
- `get_news` — news articles with sentiment
- `get_fundamentals` — financial statement data
- `run_backtest` — strategy backtesting
- `scan_market` — rule-based + agent-driven screening
- `get_risk_report` — VaR, stress test, correlation
- `recall_memory` — search past decisions by context
- `search_knowledge` — search knowledge base
- `generate_report` — PDF research report

### Loading external tools (MCP Client)
Config file: `~/.agentic-quant/agent.json`
External MCP tools are auto-injected into agent registry with `mcp_<server>_<tool>` naming.
```

## Reusable Patterns from Reference Projects

| Pattern | Source | License | How to reuse |
|---------|--------|---------|-------------|
| OWM 5-factor memory scoring | TradeMemory Protocol | MIT | Design pattern, implement our own |
| SKILL.md format | Vibe-Trading | MIT | Adopt format, write our own skills |
| Alpha Zoo formulas | Vibe-Trading | Apache-2.0 / math | Copy formulas (mathematical content), implement our own engine |
| Belief contest mechanism | ContestTrade | Apache-2.0 | Design pattern, implement our own |
| Dual debate (invest + risk) | TradingAgents-MCPmode | Apache-2.0 | Design pattern, adapt for our architecture |
| Dual-LLM cross-review | QuantGPT | MIT | Design pattern, implement our own |
| Knowledge base structure | QuantGPT | MIT | Adopt directory structure |
| Agent enable/disable toggle | TradingAgents-MCPmode | Apache-2.0 | Design pattern, add to our frontend |
| Multi-channel notification | Daily Stock Analysis | MIT | Design pattern, adapt channel implementations |
