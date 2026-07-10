# API Contracts

Base URL: `http://localhost:8000/api`

All responses are JSON (`snake_case`). Streaming endpoints use `text/event-stream` (SSE). All timestamps are ISO 8601.

---

## 1. Analysis (Quick Ask)

### `POST /api/analyze`

Start a new analysis. Returns SSE stream with progress events, final result as last event.

**Request:**
```json
{
  "ticker": "AAPL",
  "strategy_id": "strategy-uuid-or-default",
  "date": "2024-01-15T00:00:00Z",
  "current_position_pct": 0.0,
  "mode": "standard",
  "active_agents": ["market", "news", "fundamentals", "bull_researcher", "bear_researcher", "pm"],
  "beliefs": ["专注于短期事件驱动机会"],
  "debate_rounds": 2,
  "enable_debate": true,
  "enable_cross_review": false
}
```

The Quick Ask UI always sends the selected strategy identity. It exposes an
explicit `default` option alongside persisted strategy IDs, and restores a
validated `strategy_id` from the URL or the active analysis snapshot.

**SSE Events:**
```
event: progress
data: {"agent": "company_overview", "status": "completed", "duration_ms": 1200}

event: progress
data: {"agent": "market_analyst", "status": "started"}

event: progress
data: {"agent": "market_analyst", "status": "completed", "duration_ms": 3200}

event: progress
data: {"agent": "news_analyst", "status": "tool_call", "tool": "get_news"}

event: debate
data: {"type": "investment", "round": 1, "bull_claim": "...", "bear_claim": "..."}

event: debate
data: {"type": "risk", "round": 1, "aggressive": "...", "safe": "...", "neutral": "..."}

event: result
data: { full AgentState + TradingDecision + debate_records }
```

### `POST /api/analyze/batch`

Multi-ticker analysis.

**Request:**
```json
{
  "tickers": ["AAPL", "MSFT", "GOOG"],
  "mode": "standard"
}
```

**Response:** `{ "batch_id": "uuid", "results": [...] }`

---

## 2. Strategies

### `GET /api/strategies`

List all strategies.

**Query params:** `?type=agent&status=active&tag=tech&page=1&limit=20`

**Response:**
```json
{
  "items": [ { StrategyConfig summary } ],
  "total": 12,
  "page": 1
}
```

### `POST /api/strategies`

Create new strategy.

**Request:** StrategyConfig (see data-models.md §3)

**Response:** `201` + StrategyConfig

### `GET /api/strategies/{strategy_id}`

**Response:** StrategyConfig (full)

### `PUT /api/strategies/{strategy_id}`

Update strategy config (partial update supported).

### `DELETE /api/strategies/{strategy_id}`

Delete strategy and its database. **Requires confirmation:** `?confirm=true`

### `POST /api/strategies/{strategy_id}/clone`

**Request:** `{ "name": "My Cloned Strategy" }`. `name` is trimmed, non-empty,
and at most 200 characters; unknown request fields return `422`.

**Response:** `201` + a new StrategyConfig with a fresh `id`, `name`, timestamps,
`status: "draft"`, and `parent_strategy_id` set to the source strategy ID. Only
configuration is copied, including custom config fields. Identity/timestamps,
inline memory/history/decisions, runtime state, database references, credentials,
and secret/API-key fields are excluded; the source strategy database is not copied.

### `POST /api/strategies/{strategy_id}/start`

Persist a lifecycle status change: `draft|paused|stopped -> active`. Starting an
already-active strategy is idempotent and does not rewrite it. Archived or other
unsupported states return `409`. This endpoint does not start a scheduler.

### `POST /api/strategies/{strategy_id}/pause`

Persist `active -> paused`. Pausing an already-paused strategy is idempotent and
does not rewrite it; all other states return `409`. Positions are unchanged.

### `POST /api/strategies/{strategy_id}/stop`

**Request:** `{ "liquidate": false }` (`false` is the default). The field must be
a JSON boolean; unknown request fields return `422`.

Persist `draft|active|paused -> stopped`. Stopping an already-stopped strategy is
idempotent and does not rewrite it; unsupported states return `409`.
`{ "liquidate": true }` always returns `409` with
`{ "detail": "Liquidation is not supported" }`; this endpoint never pretends to
liquidate positions.

For clone, start, pause, and non-liquidating stop requests, an unknown strategy
ID returns `404` with `{ "detail": "Strategy {strategy_id} not found" }`.
Because `liquidate=true` is always unsupported, that stop request returns its
stable `409` before strategy lookup. Transition conflicts use `409` with
`{ "detail": "Cannot {action} strategy from status {status}" }`.

### `GET /api/strategies/{strategy_id}/agents`

Get agent configuration for this strategy (which agents are active, debate rounds, etc.)

### `PUT /api/strategies/{strategy_id}/agents`

Update agent configuration.

**Request:**
```json
{
  "active_agents": ["market", "news", "fundamentals", "bull_researcher", "bear_researcher", "pm"],
  "debate_rounds": 2,
  "risk_debate_rounds": 2,
  "enable_cross_review": false
}
```

### `GET /api/strategies/{strategy_id}/beliefs`

Get trading beliefs for this strategy.

### `POST /api/strategies/{strategy_id}/beliefs`

Add a trading belief.

**Request:**
```json
{
  "text": "专注于短期事件驱动机会：优先关注公司公告、并购重组等催化事件",
  "weight": 1.0
}
```

### `PUT /api/strategies/{strategy_id}/beliefs/{belief_id}`

Update belief text or weight.

### `DELETE /api/strategies/{strategy_id}/beliefs/{belief_id}`

Remove a belief.

---

## 3. Portfolio & Performance

### `GET /api/strategies/{strategy_id}/account`

**Response:** `Account`

### `GET /api/strategies/{strategy_id}/positions`

**Response:** `{ "positions": [Position], "total_value": 100500.0 }`

### `GET /api/strategies/{strategy_id}/performance`

**Query params:** `?period=1m&benchmark=SPY`

**Response:** `PerformanceMetrics`

### `GET /api/strategies/{strategy_id}/trades`

**Query params:** `?ticker=AAPL&from=2024-01-01&to=2024-06-01&page=1&limit=50`

**Response:**
```json
{
  "trades": [Trade],
  "total": 120,
  "page": 1
}
```

### `GET /api/strategies/{strategy_id}/decisions`

**Query params:** `?ticker=AAPL&from=2024-01-01&to=2024-06-01`

**Response:**
```json
{
  "decisions": [
    {
      "session_id": "uuid",
      "ticker": "AAPL",
      "timestamp": "2024-01-15T10:30:00Z",
      "direction": "Bullish",
      "confidence": 0.75,
      "action": "BUY",
      "target_position_pct": 60.0,
      "winning_belief": "短期事件驱动",
      "cross_review_consensus": true,
      "pm_report": "...",
      "risk_report": "...",
      "debate_records": [...]
    }
  ]
}
```

### `GET /api/strategies/{strategy_id}/debates`

Get debate history for a session or date range.

**Query params:** `?session_id=uuid&from=2024-01-01&to=2024-06-01`

**Response:**
```json
{
  "debates": [
    {
      "session_id": "uuid",
      "type": "investment",
      "rounds": [
        {
          "round_num": 1,
          "bull": { "claim": "...", "evidence": [...] },
          "bear": { "claim": "...", "evidence": [...], "rebuttal_to": "bull_claim_1" }
        }
      ]
    }
  ]
}
```

### `GET /api/strategies/{strategy_id}/events`

Audit trail. Query params: `?session_id=uuid`

**Response:**
```json
{
  "events": [SystemEvent],
  "session_id": "uuid"
}
```

---

## 4. Memory & Learning

### `GET /api/strategies/{strategy_id}/memory`

Query params: `?ticker=AAPL&limit=20&min_score=0.5`

Records are read from `MEMORY_DB_PATH` (default `data/memory.db`) and are scoped
to the strategy ID in the path. A storage open/read failure returns `500` with
`{ "detail": "Failed to read memory" }`; it is not represented as an empty list.

**Response:**
```json
{
  "memories": [MemoryRecord],
  "total": 145
}
```

### `GET /api/strategies/{strategy_id}/memory/{memory_id}`

**Response:** MemoryRecord (full, all 5 layers)

This endpoint uses the same configured store as the list endpoint. An unknown
memory ID, or a memory owned by a different strategy, returns `404` with
`{ "detail": "Memory {memory_id} not found" }`. Storage failures use the same
safe `500` response as the list endpoint.

### `POST /api/strategies/{strategy_id}/memory/search`

Semantic search over memories.

**Request:**
```json
{
  "query": "AAPL earnings surprise",
  "limit": 10,
  "min_similarity": 0.6
}
```

### `GET /api/strategies/{strategy_id}/reflections`

Weekly reflection history.

**Query params:** `?page=1&limit=10`

**Response:**
```json
{
  "reflections": [Reflection],
  "total": 26
}
```

### `GET /api/strategies/{strategy_id}/reflections/{reflection_id}`

**Response:** Reflection (full)

### `POST /api/strategies/{strategy_id}/reflections/generate`

Trigger a reflection generation manually.

### `GET /api/strategies/{strategy_id}/pre-trade-check`

Get the latest pre-trade safety status.

**Response:**
```json
{
  "drawdown_ok": true,
  "streak_ok": true,
  "concentration_ok": false,
  "warnings": ["AAPL position exceeds 25% concentration limit"],
  "can_trade": true
}
```

---

## 5. Knowledge Base

### `GET /api/strategies/{strategy_id}/knowledge`

Query params: `?type=rule&page=1&limit=20`

**Response:**
```json
{
  "entries": [KnowledgeEntry],
  "total": 35
}
```

### `POST /api/strategies/{strategy_id}/knowledge`

Create knowledge entry.

**Request:**
```json
{
  "type": "rule",
  "title": "AAPL rallies after positive earnings",
  "content": "...",
  "confidence": 0.9,
  "source_session_id": "uuid"
}
```

### `PUT /api/strategies/{strategy_id}/knowledge/{entry_id}`

Update entry.

### `DELETE /api/strategies/{strategy_id}/knowledge/{entry_id}`

Delete entry.

### `GET /api/strategies/{strategy_id}/knowledge/search`

**Query params:** `?q=earnings+rally&type=finding`

---

## 6. Hypotheses

### `GET /api/strategies/{strategy_id}/hypotheses`

Query params: `?status=active`

**Response:**
```json
{
  "hypotheses": [Hypothesis],
  "total": 8
}
```

### `POST /api/strategies/{strategy_id}/hypotheses`

Create hypothesis.

**Request:**
```json
{
  "claim": "RSI(14) < 30 combined with positive news sentiment produces >60% win rate",
  "acceptance_criteria": "Win rate > 60% over at least 20 trades",
  "budget_rounds": 20
}
```

### `GET /api/strategies/{strategy_id}/hypotheses/{hypothesis_id}`

**Response:** Hypothesis (full with evidence rows)

### `PUT /api/strategies/{strategy_id}/hypotheses/{hypothesis_id}`

Update hypothesis status or add evidence.

### `POST /api/strategies/{strategy_id}/hypotheses/{hypothesis_id}/evidence`

Add evidence to a hypothesis.

**Request:**
```json
{
  "session_id": "uuid",
  "result": "supporting",
  "note": "RSI(14)=28, news_sentiment=0.7, PnL=+3.2%"
}
```

---

## 7. Skills

### `GET /api/skills`

List all skills.

**Query params:** `?category=analysis&active=true`

**Response:**
```json
{
  "skills": [Skill],
  "total": 25
}
```

### `GET /api/skills/{skill_id}`

**Response:** Skill (full with prompt template)

### `POST /api/skills`

Create user skill.

**Request:**
```json
{
  "name": "my-custom-strategy",
  "category": "strategy",
  "description": "My custom trading strategy",
  "tools": ["get_prices", "get_indicators"],
  "prompt_template": "..."
}
```

### `PUT /api/skills/{skill_id}`

Update user skill (builtin skills are read-only).

### `DELETE /api/skills/{skill_id}`

Delete user skill.

### `POST /api/skills/{skill_id}/toggle`

Enable/disable a skill. `{ "is_active": false }`

---

## 8. MCP Integration

### `GET /api/mcp/status`

MCP server status.

**Response:**
```json
{
  "running": true,
  "transport": "stdio",
  "tools_exposed": 10,
  "connected_clients": 2
}
```

### `GET /api/mcp/tools`

List all MCP tools exposed by this server.

### `GET /api/mcp/servers`

List configured external MCP servers.

**Response:**
```json
{
  "servers": [
    {
      "name": "financial-datasets",
      "command": "uvx",
      "args": ["financial-datasets-mcp"],
      "enabled": true,
      "tools_count": 10
    }
  ]
}
```

### `POST /api/mcp/servers`

Add external MCP server.

### `DELETE /api/mcp/servers/{server_name}`

Remove external MCP server.

### `POST /api/mcp/servers/{server_name}/test`

Test connection to external MCP server.

---

## 9. Backtest

### `POST /api/agent/backtest`

**Request:**
```json
{
  "strategy_id": "strategy-uuid",
  "ticker": "AAPL",
  "date_from": "2025-01-02",
  "date_to": "2025-03-31",
  "frequency": "weekly",
  "benchmark": "SPY"
}
```

**Response (202):** `{ "backtest_id": "uuid", "status": "pending" }`.
Each request creates an independent persisted job. `strategy_id` must refer to an
existing strategy. Invalid dates/ticker/frequency return `422`; an unknown
strategy returns `404`; a missing LLM configuration returns `422` before a job
is created. The ACTIVE route never invokes a legacy analysis pipeline.

### `GET /api/agent/backtest/{backtest_id}`

**Response:**
```json
{
  "status": "completed",
  "backtest_id": "uuid",
  "result": {
    "status": "completed",
    "config": {
      "ticker": "AAPL",
      "start_date": "2025-01-02",
      "end_date": "2025-03-31",
      "frequency": "weekly",
      "benchmark_symbol": "SPY",
      "strategy_id": "strategy-uuid"
    },
    "summary": {
      "cumulative_return_pct": 15.3,
      "benchmark_return_pct": 9.1,
      "excess_return_pct": 6.2,
      "max_drawdown_pct": -7.1,
      "sharpe_ratio": 1.2
    },
    "series": [],
    "trades": []
  },
  "error": null,
  "created_at": "2025-01-02T00:00:00+00:00",
  "started_at": "2025-01-02T00:00:01+00:00",
  "completed_at": "2025-01-02T00:00:10+00:00",
  "updated_at": "2025-01-02T00:00:10+00:00"
}
```

Pending/running jobs have `result: null`. Failed jobs have `result: null` and
a safe `{ "code", "message" }` error. Results live in `system.db`; startup
marks abandoned pending/running jobs as failed with `code: "interrupted"`.

### `GET /api/agent/backtest/{backtest_id}/trades.csv`

Returns a generated `text/csv` attachment only when the persisted job is
completed. Unknown jobs return `404`; pending, running, failed, or malformed
results return `409` and never expose prompts, credentials, paths, or stacks.

---

## 10. Alpha Zoo

### `GET /api/alpha-zoo`

List all available alpha factors.

**Query params:** `?zoo=gtja191&theme=momentum&limit=20`

**Response:**
```json
{
  "zoos": ["qlib158", "alpha101", "gtja191", "academic"],
  "total_factors": 452,
  "factors": [
    {
      "id": "gtja191_171",
      "zoo": "gtja191",
      "name": "...",
      "expression": "rank(ts_av_diff(close, 10))",
      "theme": "momentum",
      "source": "Guotai Junan 2014"
    }
  ]
}
```

### `GET /api/alpha-zoo/{factor_id}`

**Response:** Factor metadata + expression + source attribution.

### `POST /api/alpha-zoo/bench`

Benchmark factors against a universe.

**Request:**
```json
{
  "factor_ids": ["gtja191_171", "gtja191_111"],
  "universe": "csi300",
  "period_start": "2018-01-01",
  "period_end": "2025-12-31",
  "top_n": 20
}
```

**Response:** `{ "job_id": "uuid" }` → SSE stream for progress

---

## 11. Daily Insights

### `GET /api/insights`

**Query params:** `?from=2024-01-01&to=2024-01-31&type=morning_brief`

**Response:**
```json
{
  "insights": [DailyInsight]
}
```

### `GET /api/insights/{insight_id}`

**Response:** DailyInsight (full)

### `POST /api/insights/{insight_id}/feedback`

**Request:**
```json
{
  "rating": 4,
  "was_direction_correct": true,
  "comment": "Accurate on tech sector outlook"
}
```

---

## 12. Approvals (HITL)

### `GET /api/approvals`

**Query params:** `?status=pending`

**Response:**
```json
{
  "pending": [Approval],
  "total_pending": 3
}
```

### `GET /api/approvals/{approval_id}`

**Response:** Approval with full context (all agent reports, debate history, cross-review result)

### `POST /api/approvals/{approval_id}/approve`

**Request:** `{ "reviewer": "username", "notes": "Looks good" }`

### `POST /api/approvals/{approval_id}/reject`

**Request:** `{ "reviewer": "username", "notes": "Too risky, conflicting signals" }`

### `POST /api/approvals/{approval_id}/modify`

**Request:**
```json
{
  "reviewer": "username",
  "modified_params": {
    "target_position_pct": 30.0
  },
  "notes": "Reduced position size due to uncertainty"
}
```

---

## 13. Scanner

### `POST /api/scanner/rule`

**Request:**
```json
{
  "conditions": [
    { "field": "rsi14", "operator": "<", "value": 30 },
    { "field": "pe_ratio", "operator": "<", "value": 15 }
  ],
  "universe": "sp500"
}
```

**Response:**
```json
{
  "results": [ScanResult],
  "total_matches": 23,
  "scanned_at": "..."
}
```

### `POST /api/scanner/agent`

**Request:**
```json
{
  "query": "Find tech stocks that had negative news last week but strong fundamentals",
  "universe": "nasdaq100"
}
```

### `POST /api/scanner/belief`

**Request:**
```json
{
  "belief_id": "uuid",
  "universe": "sp500"
}
```

### `GET /api/scanner/queries`

Saved scan queries.

---

## 14. Watchlists

### `GET /api/watchlists`
### `POST /api/watchlists`

**Request:** `{ "name": "My AI Stocks", "tickers": ["NVDA", "AMD", "INTC"] }`

### `GET /api/watchlists/{watchlist_id}`
### `PUT /api/watchlists/{watchlist_id}`
### `DELETE /api/watchlists/{watchlist_id}`
### `POST /api/watchlists/{watchlist_id}/tickers`

**Request:** `{ "ticker": "SMCI" }`

### `DELETE /api/watchlists/{watchlist_id}/tickers/{ticker}`

### `POST /api/watchlists/{watchlist_id}/alerts`

**Request:**
```json
{
  "ticker": "AAPL",
  "type": "price_below",
  "threshold_value": 200.0
}
```

---

## 15. Risk Analytics

### `GET /api/risk/{strategy_id}/var`

**Query params:** `?confidence=0.95`

**Response:**
```json
{
  "var_95": -0.023,
  "cvar_95": -0.031,
  "var_99": -0.045,
  "method": "historical",
  "lookback_days": 252
}
```

### `POST /api/risk/{strategy_id}/stress`

**Request:**
```json
{
  "scenario": "custom",
  "market_shock_pct": -10.0,
  "vix_spike": 40.0,
  "rate_change_bps": 100
}
```

### `GET /api/risk/{strategy_id}/correlation`

### `GET /api/risk/{strategy_id}/concentration`

---

## 16. Reports

### `POST /api/reports/stock`

### `POST /api/reports/sector`

### `GET /api/reports`

### `GET /api/reports/{report_id}/download`

Returns PDF binary (`application/pdf`).

---

## 17. Conversations

### `GET /api/conversations`

### `GET /api/conversations/{conversation_id}`

### `DELETE /api/conversations/{conversation_id}`

### `POST /api/conversations/{conversation_id}/save`

---

## 18. Settings

### `GET /api/settings`

**Response:** SystemConfig (see data-models.md §19)

### `PUT /api/settings`

Partial update supported.

### `POST /api/settings/test-email`

### `POST /api/settings/test-telegram`

### `POST /api/settings/test-wechat`

Send test WeChat message.

### `POST /api/settings/test-feishu`

Send test Feishu message.

---

## 19. System

### `GET /api/health`

**Response:**
```json
{ "status": "ok", "uptime_seconds": 3600, "version": "1.0.0" }
```

### `GET /api/data-sources/status`

---

## Error Format

All errors use a consistent format:

```json
{
  "error": {
    "code": "STRATEGY_NOT_FOUND",
    "message": "Strategy with id 'xxx' not found",
    "details": {}
  }
}
```

HTTP status codes:
- `400` — bad request (invalid params)
- `404` — resource not found
- `409` — conflict (e.g., strategy already running)
- `422` — validation error
- `429` — rate limited
- `500` — internal error
- `503` — data source unavailable

---

## SSE Event Format

Used by `/api/analyze` and `/api/alpha-zoo/bench` for real-time progress:

```
event: progress
data: {"agent": "market_analyst", "status": "started", "timestamp": "..."}

event: progress
data: {"agent": "news_analyst", "status": "tool_call", "tool": "get_news", "timestamp": "..."}

event: debate
data: {"type": "investment", "round": 1, "bull_claim": "...", "bear_claim": "...", "timestamp": "..."}

event: debate
data: {"type": "risk", "round": 1, "aggressive": "...", "safe": "...", "neutral": "...", "timestamp": "..."}

event: error
data: {"agent": "fundamentals_analyst", "error": "Data source unavailable", "timestamp": "..."}

event: result
data: {"session_id": "uuid", "action": "BUY", "debate_records": [...], ...}
```

Status values: `started`, `tool_call`, `tool_result`, `completed`, `error`

Frontend should:
- Display agent status cards in real time with parallel grouping (Stage 1: 6 analysts; Stage 2: debate; Stage 3: risk)
- Display debate events in a side-by-side panel (bull vs bear) or 3-column (risk debate)
- Handle `error` events gracefully (show which agent failed, allow retry)
- Parse the final `result` event as the complete AgentState + TradingDecision + debate records
