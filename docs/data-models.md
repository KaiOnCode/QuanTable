# Data Models

Single source of truth for all shared data structures. Backend Pydantic models and frontend TypeScript types must stay aligned with this document.

---

## 1. Agent State (LangGraph)

Expanded from 5 to up to 15 agents. Fields are additive — not all agents are active in every run.

```python
class AgentState(MessagesState):
    # ── Input ──
    ticker: str                             # e.g. "AAPL"
    date: str                               # ISO 8601, e.g. "2024-01-15T00:00:00Z"
    current_position_pct: float = 0.0       # -100 to 100
    beliefs: list[str] = []                 # Active trading beliefs for this run

    # ── Active agent flags (user-configurable) ──
    active_agents: list[str] = [
        "company_overview", "market", "news", "fundamentals",
        "sentiment", "technical", "macro",
        "bull_researcher", "bear_researcher",
        "research_manager", "trader",
        "aggressive_risk", "safe_risk", "neutral_risk",
        "risk_manager", "pm"
    ]
    debate_rounds: int = 2                  # Configurable 1-5
    risk_debate_rounds: int = 2

    # ── Per-agent messages (add_messages reducer) ──
    company_overview_messages: list[BaseMessage]
    market_analyst_messages: list[BaseMessage]
    news_analyst_messages: list[BaseMessage]
    fundamentals_analyst_messages: list[BaseMessage]
    sentiment_analyst_messages: list[BaseMessage]
    technical_analyst_messages: list[BaseMessage]
    macro_analyst_messages: list[BaseMessage]
    bull_researcher_messages: list[BaseMessage]
    bear_researcher_messages: list[BaseMessage]
    research_manager_messages: list[BaseMessage]
    trader_messages: list[BaseMessage]
    aggressive_risk_messages: list[BaseMessage]
    safe_risk_messages: list[BaseMessage]
    neutral_risk_messages: list[BaseMessage]
    risk_manager_messages: list[BaseMessage]
    PM_agent_messages: list[BaseMessage]

    # ── Stage 0: Company Overview ──
    company_overview_report: str = ""       # Ticker context, sector, market cap

    # ── Stage 1: Parallel analysts (6 agents) ──
    market_report: str = ""
    news_report: str = ""
    fundamental_report: str = ""
    sentiment_report: str = ""
    technical_report: str = ""
    macro_report: str = ""

    # ── Stage 2: Bull/Bear debate ──
    debate_history: list[dict] = []         # [{round, speaker, claim, evidence, rebuttal}]
    bull_argument: str = ""
    bear_argument: str = ""

    # ── Stage 3: Research Manager ──
    investment_plan: str = ""

    # ── Stage 4: Trader ──
    trade_proposal: str = ""

    # ── Stage 5: 3-way Risk debate ──
    risk_debate_history: list[dict] = []
    aggressive_risk_view: str = ""
    safe_risk_view: str = ""
    neutral_risk_view: str = ""

    # ── Stage 6: Final decision ──
    risk_report: str = ""
    PM_report: str = ""
    Action: str = ""                        # BUY | SELL | HOLD
    Target_position_pct: float = 0.0

    # ── Memory context (injected before PM) ──
    relevant_memories: list[dict] = []      # Past decisions + outcomes for context

    # ── Timestamps ──
    session_id: str = ""
    started_at: str = ""
```

## 2. Trading Decision (PM Output)

```python
class TradingDecision(BaseModel):
    action: Literal["BUY", "SELL", "HOLD"]
    target_position_pct: float              # -100 to 100
    report: str                             # Full reasoning (Markdown)
    direction: Literal["Bullish", "Bearish", "Neutral"]
    timeframe: Literal["intraday", "1-3d", "1-4w", "long-term"]
    confidence: float                       # 0.0 to 1.0
    reasoning_outline: str
    risk_factors: list[str]
    entry_conditions: str
    exit_conditions: str
    # ── New fields ──
    winning_belief: str | None              # Which belief won the internal contest
    cross_review_result: str | None         # 2nd LLM review result (HITL only)
    cross_review_consensus: bool = True     # Did 2nd LLM agree?
```

## 3. Strategy

```python
class StrategyType(str, Enum):
    AGENT = "agent"                         # LLM agent decision-making
    QUANT = "quant"                         # Traditional rule-based
    HITL = "hitl"                           # Agent + human approval

class StrategyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"
    ARCHIVED = "archived"

class StrategyConfig(BaseModel):
    id: str                                 # UUID
    name: str
    description: str
    type: StrategyType

    # Ticker pool
    tickers: list[str]

    # ── Belief system (replaces fixed agent_prompt_template) ──
    beliefs: list[str] = []                 # Natural language trading philosophies
    belief_weights: dict[str, float] = {}   # Per-belief weight (from historical performance)

    # Agent config
    active_agents: list[str] = [            # Which agents to use (toggle per agent)
        "market", "news", "fundamentals",
        "bull_researcher", "bear_researcher",
        "research_manager", "trader",
        "aggressive_risk", "neutral_risk",
        "risk_manager", "pm"
    ]
    debate_rounds: int = 2
    risk_debate_rounds: int = 2
    agent_model: str = "deepseek-chat"      # Quick-think model
    deep_think_model: str = "deepseek-chat" # Deep-think model (complex reasoning)
    agent_temperature: float = 0.0
    enable_debate_mode: bool = True
    enable_cross_review: bool = False       # Dual-LLM cross-review for HITL

    # Quant config (for QUANT type)
    quant_strategy_name: str | None
    quant_params: dict = {}
    alpha_zoo_factors: list[str] = []       # Selected factors from Alpha Zoo

    # Execution config
    execution_frequency: str = "daily"
    execution_time: str = "09:30"
    initial_capital: float = 100_000.0
    max_position_pct: float = 80.0
    max_drawdown_pct: float = 100.0

    # HITL config
    hitl_enabled: bool = False
    hitl_trigger_position_change_pct: float = 20.0
    hitl_trigger_signal_conflict: bool = True
    hitl_trigger_confidence_below: float = 0.6
    hitl_timeout_hours: float = 2.0

    # Memory & learning
    memory_enabled: bool = True             # Record decisions to memory
    memory_recall_limit: int = 5            # Max past memories to inject per run
    weekly_reflection: bool = True          # Auto-generate weekly reflection

    # Status
    status: StrategyStatus = StrategyStatus.DRAFT
    created_at: str
    updated_at: str
    tags: list[str] = []

    # Metadata
    creator: str
    parent_strategy_id: str | None
```

## 4. Trading Belief

```python
class TradingBelief(BaseModel):
    """A single trading philosophy that biases agent decision-making."""
    id: str                                 # UUID
    strategy_id: str
    text: str                               # Natural language belief statement
    style: Literal["aggressive", "moderate", "conservative"]  # Auto-classified
    historical_performance: dict = {}       # {win_rate, avg_return, sharpe, total_trades}
    weight: float = 1.0                     # Current weight in contest
    is_active: bool = True
    created_at: str
```

## 5. Memory System

Inspired by TradeMemory Protocol's OWM framework.

```python
class MemoryLayer(str, Enum):
    EPISODIC = "episodic"                   # Concrete trade events
    SEMANTIC = "semantic"                   # Learned rules
    PROCEDURAL = "procedural"               # Operational patterns
    AFFECTIVE = "affective"                 # Emotional context (HITL)
    TRADE_RECORD = "trade_record"           # Raw data

class MemoryRecord(BaseModel):
    """A single memory entry stored across 5 layers."""
    id: str                                 # UUID
    strategy_id: str
    session_id: str
    ticker: str

    # ── OWM 5-factor scoring ──
    outcome_quality: float                  # -1.0 to 1.0 (PnL-based)
    context_similarity: float               # 0.0 to 1.0 (how similar to current)
    recency: float                          # 0.0 to 1.0 (decay over time)
    confidence: float                       # 0.0 to 1.0 (original decision confidence)
    affective_state: str | None             # "calm", "stressed", "urgent", etc.

    # ── Content (per layer) ──
    episodic: str                           # Story: "Bought AAPL at $185 on signal X, sold at $192 (+3.8%)"
    semantic: str                           # Rule: "AAPL rallies after positive earnings"
    procedural: str                         # Pattern: "When RSI<30 AND news_sentiment>0.6 → BUY"
    affective: str | None                   # "High VIX period, reduced position by 50%"
    trade_record: dict                      # {action, price, quantity, pnl, pnl_pct, ...}

    # ── Retrieval ──
    owm_score: float                        # Computed weighted score for relevance ranking
    tags: list[str] = []                    # Auto-generated: ["earnings", "tech", "momentum"]

    created_at: str

class Reflection(BaseModel):
    """Periodic (weekly) reflection on strategy performance."""
    id: str
    strategy_id: str
    period_start: str
    period_end: str

    # Metrics
    total_trades: int
    win_rate_pct: float
    avg_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None

    # Behavioral diagnostics (from LLM Trading Lab)
    disposition_effect: str | None          # Selling winners too early, holding losers
    overtrading: str | None                 # Excessive trading frequency
    momentum_chasing: str | None            # Buying after large moves
    anchoring: str | None                   # Fixating on entry price

    # Strategy health
    strategy_decay_detected: bool
    decay_indicators: list[str]             # e.g. "declining win rate", "increasing drawdown"
    recommendations: list[str]              # Suggested adjustments

    # Knowledge base updates
    new_rules: list[str]                    # Rules confirmed this period
    new_findings: list[str]                 # New discoveries
    new_failures: list[str]                 # Falsified approaches

    generated_at: str

class PreTradeCheck(BaseModel):
    """Safety gate before executing a trade."""
    id: str
    strategy_id: str
    decision_id: str

    passed: bool
    checks: dict[str, bool]                 # {drawdown_ok, streak_ok, concentration_ok, ...}
    blocking_reasons: list[str]
    warnings: list[str]

    checked_at: str
```

## 6. Knowledge Base

Inspired by QuantGPT's structured research knowledge.

```python
class KnowledgeEntryType(str, Enum):
    RULE = "rule"                           # Verified stable rule (must follow)
    FINDING = "finding"                     # Empirical discovery (reference)
    FAILURE = "failure"                     # Falsified path (avoid)

class KnowledgeEntry(BaseModel):
    id: str                                 # UUID
    strategy_id: str
    type: KnowledgeEntryType
    title: str                              # One-line summary
    content: str                            # Full description
    evidence: list[str] = []                # Linked session_ids or backtest_ids
    confidence: float = 1.0                 # How confident we are in this knowledge
    source_session_id: str | None           # Which session generated this
    created_at: str
    updated_at: str

class Hypothesis(BaseModel):
    """Research hypothesis with lifecycle tracking (from Vibe-Trading)."""
    id: str
    strategy_id: str
    status: Literal["draft", "active", "validating", "confirmed", "rejected", "stale"]

    claim: str                              # The hypothesis statement
    acceptance_criteria: str                # How to validate
    evidence: list[dict] = []               # [{session_id, result, note, timestamp}]
    open_items: list[str] = []              # Unresolved questions

    budget_rounds: int = 5                  # Max rounds before auto-stale
    completed_rounds: int = 0

    created_at: str
    resolved_at: str | None
```

## 7. Skill System

```python
class SkillCategory(str, Enum):
    ANALYSIS = "analysis"
    STRATEGY = "strategy"
    RISK = "risk"
    RESEARCH = "research"
    DATA = "data"
    NOTIFICATION = "notification"

class Skill(BaseModel):
    """A reusable agent capability defined as a SKILL.md file."""
    id: str                                 # UUID (from skill file hash)
    name: str                               # e.g. "technical-analysis"
    version: str = "1.0"
    category: SkillCategory
    description: str

    # From SKILL.md frontmatter
    tools: list[str]                        # Required tools
    model: str = "deepseek-chat"            # Recommended model
    temperature: float = 0.0

    # Content
    prompt_template: str                    # The actual skill prompt/workflow
    file_path: str                          # Path to SKILL.md on disk

    # Status
    is_builtin: bool = True                 # Bundled vs user-created
    is_active: bool = True
    created_at: str
    updated_at: str
```

## 8. Account & Portfolio

```python
class Account(BaseModel):
    id: str
    strategy_id: str
    initial_balance: float
    cash: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    total_pnl_pct: float
    # ── Benchmark comparison ──
    benchmark_symbol: str = "SPY"           # or "000300.SH" for CSI 300
    benchmark_return_pct: float = 0.0
    excess_return_pct: float = 0.0          # total_pnl_pct - benchmark_return_pct
    information_ratio: float | None
    updated_at: str

class Position(BaseModel):
    account_id: str
    ticker: str
    quantity: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    weight_pct: float
    updated_at: str
```

## 9. Orders & Trades

```python
class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderStatus(str, Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class Order(BaseModel):
    id: str
    account_id: str
    strategy_id: str
    ticker: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    limit_price: float | None
    status: OrderStatus
    filled_quantity: float = 0.0
    filled_avg_price: float | None
    commission: float = 0.0
    slippage_pct: float = 0.0
    decision_id: str | None
    created_at: str
    executed_at: str | None
    cancelled_at: str | None
    notes: str = ""

class Trade(BaseModel):
    id: str
    order_id: str
    account_id: str
    ticker: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    slippage_pct: float
    timestamp: str

class PerformanceMetrics(BaseModel):
    account_id: str
    period: str                             # "1d" | "1w" | "1m" | "3m" | "6m" | "1y" | "all"
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_pct: float
    max_drawdown_duration_days: int | None
    win_rate_pct: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float | None
    total_trades: int
    # ── Benchmark ──
    benchmark_return_pct: float
    excess_return_pct: float
    equity_curve: list[dict]                # [{date, equity, daily_return, benchmark_equity}, ...]
```

## 10. Debate Record

```python
class DebateType(str, Enum):
    INVESTMENT = "investment"               # Bull vs Bear
    RISK = "risk"                           # Aggressive vs Safe vs Neutral

class DebateRecord(BaseModel):
    """Captures a single round of a debate for visualization."""
    id: str
    session_id: str
    debate_type: DebateType
    round_num: int
    speaker: str                            # Agent name
    role: str                               # "bull", "bear", "aggressive_risk", etc.
    claim: str                              # Main argument
    evidence: list[str]                     # Supporting data points
    rebuttal_to: str | None                 # ID of the claim being rebutted
    timestamp: str
```

## 11. HITL Approval

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    TIMED_OUT = "timed_out"

class Approval(BaseModel):
    id: str
    strategy_id: str
    decision_id: str
    status: ApprovalStatus
    triggered_rules: list[str]
    original_decision: dict
    modified_params: dict | None
    # ── Cross-review ──
    cross_review_model: str | None          # 2nd LLM used for review
    cross_review_result: str | None         # 2nd LLM's analysis
    cross_review_consensus: bool = True     # Did 2nd LLM agree?
    # ── Human review ──
    reviewer: str | None
    reviewer_notes: str = ""
    created_at: str
    resolved_at: str | None
    timeout_at: str
```

## 12. Quick Ask & Conversations

```python
class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    tags: list[str] = []
    is_saved: bool = False
    description: str = ""

class ChatMessage(BaseModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    analysis_result: dict | None
    # ── Debate visualization data ──
    debate_records: list[DebateRecord] = []
    timestamp: str
```

## 13. Daily Insights

```python
class InsightType(str, Enum):
    MORNING_BRIEF = "morning_brief"
    MIDDAY_UPDATE = "midday_update"
    EVENT_ALERT = "event_alert"

class DailyInsight(BaseModel):
    id: str
    type: InsightType
    title: str
    content: str
    summary: str
    tickers_covered: list[str]
    key_events: list[str]
    generated_at: str
    sent_via: list[str] = []                # ["email", "telegram", "wechat", "feishu"]

class InsightFeedback(BaseModel):
    insight_id: str
    rating: int                             # 1-5
    was_direction_correct: bool | None
    comment: str = ""
```

## 14. Market Scanner

```python
class ScanCondition(BaseModel):
    field: str
    operator: Literal["<", ">", "<=", ">=", "==", "between"]
    value: float | str
    value2: float | None

class ScannerQuery(BaseModel):
    id: str
    name: str
    type: Literal["rule", "agent", "belief"]  # Added "belief" mode
    conditions: list[ScanCondition] = []
    natural_language: str = ""
    belief_id: str | None                    # Link to a TradingBelief
    created_at: str

class ScanResult(BaseModel):
    query_id: str
    ticker: str
    match_score: float
    matched_conditions: list[str]
    explanation: str
    snapshot_data: dict
    scanned_at: str
```

## 15. Alerts (Watchlist)

```python
class AlertType(str, Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"
    VOLUME_SPIKE = "volume_spike"
    NEWS_EVENT = "news_event"
    AGENT_FLAG = "agent_flag"

class Alert(BaseModel):
    id: str
    watchlist_id: str | None
    ticker: str
    type: AlertType
    threshold_value: float | str | None
    message: str
    is_triggered: bool = False
    triggered_at: str | None
    created_at: str
```

## 16. Watchlist

```python
class Watchlist(BaseModel):
    id: str
    name: str
    tickers: list[str]
    alerts: list[Alert] = []
    notes: dict[str, str] = {}
    created_at: str
    updated_at: str
```

## 17. Reports

```python
class ReportType(str, Enum):
    STOCK_DEEP_DIVE = "stock_deep_dive"
    SECTOR_ANALYSIS = "sector_analysis"

class Report(BaseModel):
    id: str
    type: ReportType
    title: str
    tickers: list[str]
    content_path: str
    generated_at: str
    parameters: dict
```

## 18. System Events (Audit Trail)

```python
class EventType(str, Enum):
    DATA_FETCH = "data_fetch"
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DEBATE_ROUND = "debate_round"           # New
    DECISION = "decision"
    MEMORY_RECALL = "memory_recall"         # New
    MEMORY_RECORD = "memory_record"         # New
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_RESOLVED = "approval_resolved"
    CROSS_REVIEW = "cross_review"           # New

class SystemEvent(BaseModel):
    id: str
    session_id: str
    strategy_id: str | None
    event_type: EventType
    actor: str
    payload: dict
    timestamp: str
```

## 19. Global Config

```python
class SystemConfig(BaseModel):
    # ── LLM ──
    llm_api_key: str
    llm_base_url: str
    llm_model: str = "deepseek-chat"
    deep_think_model: str = "deepseek-chat"

    # ── Notification channels ──
    email_smtp_host: str
    email_smtp_port: int
    email_recipients: list[str]
    telegram_bot_token: str
    telegram_chat_ids: list[str]
    wechat_webhook_url: str                 # New
    feishu_webhook_url: str                 # New
    discord_webhook_url: str                # New
    slack_bot_token: str                    # New
    slack_channel_id: str                   # New

    # ── System ──
    data_cache_ttl_minutes: int = 15
    news_fetch_interval_minutes: int = 30
    max_concurrent_analyses: int = 3

    # ── Memory ──
    memory_enabled: bool = True
    memory_retention_days: int = 365
    weekly_reflection_day: str = "sunday"
    weekly_reflection_time: str = "18:00"

    # ── MCP ──
    mcp_external_servers: dict = {}         # External MCP server configs
```

---

## Enums Summary

| Enum | Values |
|------|--------|
| `Action` | `BUY`, `SELL`, `HOLD` |
| `Direction` | `Bullish`, `Bearish`, `Neutral` |
| `Timeframe` | `intraday`, `1-3d`, `1-4w`, `long-term` |
| `StrategyType` | `agent`, `quant`, `hitl` |
| `StrategyStatus` | `draft`, `active`, `paused`, `stopped`, `archived` |
| `OrderSide` | `buy`, `sell` |
| `OrderType` | `market`, `limit` |
| `OrderStatus` | `pending`, `executed`, `partially_filled`, `cancelled`, `rejected` |
| `ApprovalStatus` | `pending`, `approved`, `rejected`, `modified`, `timed_out` |
| `InsightType` | `morning_brief`, `midday_update`, `event_alert` |
| `AlertType` | `price_above`, `price_below`, `rsi_above`, `rsi_below`, `volume_spike`, `news_event`, `agent_flag` |
| `ReportType` | `stock_deep_dive`, `sector_analysis` |
| `EventType` | `data_fetch`, `agent_start`, `agent_complete`, `tool_call`, `tool_result`, `debate_round`, `decision`, `memory_recall`, `memory_record`, `order_placed`, `order_filled`, `approval_requested`, `approval_resolved`, `cross_review` |
| `MemoryLayer` | `episodic`, `semantic`, `procedural`, `affective`, `trade_record` |
| `KnowledgeEntryType` | `rule`, `finding`, `failure` |
| `SkillCategory` | `analysis`, `strategy`, `risk`, `research`, `data`, `notification` |
| `DebateType` | `investment`, `risk` |
| `BeliefStyle` | `aggressive`, `moderate`, `conservative` |

---

## Database Layout (Updated)

```
data/
├── system.db                     # StrategyRegistry, SystemConfig, Watchlists, Beliefs
├── insights.db                   # DailyInsight, InsightFeedback
├── memory.db                     # MemoryRecord, Reflection, PreTradeCheck
├── knowledge.db                  # KnowledgeEntry, Hypothesis
├── scanner_queries.db            # ScannerQuery (saved scans)
├── {strategy_id}.db              # Per-strategy: Account, Position, Order, Trade,
│                                  #   Approval, SystemEvent, PerformanceMetrics
├── chat_{uuid}.db                # Per-conversation: Conversation, ChatMessage
└── {strategy_id}/knowledge/      # Per-strategy knowledge base
    ├── rules.md
    ├── findings.md
    └── failures.md
```

## Skill File Layout

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

## API Field Naming Convention

- JSON keys: `snake_case` (matches Python/Pydantic output directly)
- Frontend: deserialize as-is, use TypeScript interfaces mirroring these models
- No field renaming in the API layer

## MCP Tool Naming Convention

- Internal tools: `verb_noun` (e.g., `analyze_ticker`, `get_market_data`)
- External MCP tools: `mcp_<server>_<tool>` (e.g., `mcp_financial_datasets_get_income_statements`)
