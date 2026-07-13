export type AnalysisMode = "fast" | "standard" | "deep";

export type AgentRunStatus =
  | "waiting"
  | "started"
  | "tool_call"
  | "tool_result"
  | "completed"
  | "error";

export type TradingAction = "BUY" | "SELL" | "HOLD";
export type TradingDirection = "Bullish" | "Bearish" | "Neutral";

export type AnalyzeRequest = {
  ticker: string;
  date?: string | null;
  current_position_pct?: number;
  strategy_id?: string;
  account_id?: string;
  decision_id?: string | null;
  mode?: AnalysisMode;
  active_agents?: string[];
  beliefs?: string[];
  debate_rounds?: number;
  enable_debate?: boolean;
  enable_cross_review?: boolean;
};

export type SSEProgressEvent = {
  agent: string;
  status: AgentRunStatus;
  report?: string;
  duration_ms?: number;
  tool?: string;
  error?: string;
  session_id?: string;
  ticker?: string;
  timestamp?: string;
};

export type SSEDebateEvent = {
  type: "investment" | "risk";
  round: number;
  bull_claim?: string;
  bear_claim?: string;
  aggressive?: string;
  safe?: string;
  neutral?: string;
  timestamp?: string;
};

export type SSEResultEvent = {
  session_id: string;
  strategy_id?: string;
  account_id?: string;
  decision_id?: string;
  action: TradingAction;
  direction: TradingDirection;
  confidence: number;
  timeframe?: string;
  report?: string;
  agent_reports?: Record<string, string>;
  target_position_pct?: number;
  debate_records?: SSEDebateEvent[];
  news_articles?: { title: string; source: string; url: string; published_at: string }[];
  elapsed_s?: number;
  approval_required?: boolean;
  approval_status?: ApprovalStatus | null;
  approval_id?: string | null;
  triggered_rules?: string[];
};

export type SSEErrorEvent = {
  agent: string;
  error: string;
  timestamp?: string;
};

export type AnalysisRunStatus = "running" | "completed" | "failed";

export interface AnalysisProgressSnapshot {
  agent: string;
  status: AgentRunStatus;
  report?: string;
  duration_ms?: number;
  tool?: string;
  error?: string;
  session_id?: string;
  ticker?: string;
  timestamp?: string;
}

export interface AnalysisSessionSnapshot {
  session_id: string;
  ticker: string;
  mode: AnalysisMode;
  status: AnalysisRunStatus;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
  request: AnalyzeRequest;
  progress_events: AnalysisProgressSnapshot[];
  agent_reports: Record<string, string>;
  result: SSEResultEvent | null;
  error: string | null;
}

export interface AnalysisHistoryItem {
  session_id: string;
  ticker: string;
  mode: AnalysisMode;
  status: AnalysisRunStatus;
  created_at: string;
  updated_at?: string;
  action: TradingAction | null;
  direction: TradingDirection | null;
  confidence: number | null;
  oneliner: string;
}

// ── API request / response types (required by lib/api/*.ts) ──

export type StrategyType = "agent" | "quant" | "hitl";
export type StrategyStatus = "draft" | "active" | "paused" | "stopped" | "archived";

export interface StrategyConfig {
  id: string; name: string; description: string; type: StrategyType;
  tickers: string[]; beliefs: string[]; belief_weights: Record<string, number>;
  active_agents: string[]; debate_rounds: number; risk_debate_rounds: number;
  agent_model: string; deep_think_model: string; agent_temperature: number;
  enable_debate_mode: boolean; enable_cross_review: boolean;
  quant_strategy_name: string | null; quant_params: Record<string, unknown>;
  alpha_zoo_factors: string[]; execution_frequency: string; execution_time: string;
  initial_capital: number; max_position_pct: number; max_drawdown_pct: number;
  hitl_enabled: boolean; hitl_trigger_position_change_pct: number;
  hitl_trigger_signal_conflict: boolean; hitl_trigger_confidence_below: number;
  hitl_timeout_hours: number; memory_enabled: boolean; memory_recall_limit: number;
  weekly_reflection: boolean; status: StrategyStatus;
  created_at: string; updated_at: string; tags: string[];
  creator: string; parent_strategy_id: string | null;
}

export interface TradingBelief {
  id: string; strategy_id: string; text: string;
  style: "aggressive" | "moderate" | "conservative";
  weight: number; is_active: boolean; created_at: string;
}

export interface MemoryRecord {
  id: string; strategy_id: string; session_id: string; ticker: string;
  outcome_quality: number; context_similarity: number; recency: number;
  confidence: number; affective_state: string | null;
  episodic: string; semantic: string; procedural: string; affective: string | null;
  trade_record: Record<string, unknown>; owm_score: number;
  tags: string[]; created_at: string;
}

export interface Reflection {
  id: string; strategy_id: string; period_start: string; period_end: string;
  total_trades: number; win_rate_pct: number; avg_return_pct: number;
  max_drawdown_pct: number; sharpe_ratio: number | null;
  strategy_decay_detected: boolean; decay_indicators: string[];
  recommendations: string[]; generated_at: string;
}

export interface PreTradeCheck {
  id: string; strategy_id: string; decision_id: string;
  passed: boolean; checks: Record<string, boolean>;
  blocking_reasons: string[]; warnings: string[]; checked_at: string;
}

export interface KnowledgeEntry {
  id: string; strategy_id: string; type: "rule" | "finding" | "failure";
  title: string; content: string; evidence: string[]; confidence: number;
  source_session_id: string | null; created_at: string; updated_at: string;
}

export type SkillCategory = "analysis" | "strategy" | "risk" | "research" | "data" | "notification";

export interface Skill {
  id: string; name: string; version: string; category: SkillCategory;
  description: string; tools: string[]; model: string; temperature: number;
  prompt_template: string; file_path: string;
  is_builtin: boolean; is_active: boolean; created_at: string; updated_at: string;
}

export interface Account {
  id: string; strategy_id: string; initial_balance: number; cash: number;
  equity: number; unrealized_pnl: number; realized_pnl: number;
  total_pnl: number; total_pnl_pct: number; benchmark_symbol: string;
  benchmark_return_pct: number; excess_return_pct: number;
  information_ratio: number | null; updated_at: string;
}

export interface Position {
  account_id: string; ticker: string; quantity: number;
  avg_entry_price: number; current_price: number; market_value: number;
  unrealized_pnl: number; unrealized_pnl_pct: number; weight_pct: number;
  updated_at: string;
}

export type OrderSide = "buy" | "sell";
export type OrderStatus = "pending" | "executed" | "partially_filled" | "cancelled" | "rejected";

export interface Order {
  id: string; account_id: string; strategy_id: string; ticker: string;
  side: OrderSide; quantity: number; order_type: "market" | "limit";
  limit_price: number | null; status: OrderStatus; filled_quantity: number;
  filled_avg_price: number | null; commission: number; slippage_pct: number;
  decision_id: string | null; created_at: string; executed_at: string | null;
}

export interface Trade {
  id: string; order_id: string; account_id: string; ticker: string;
  side: OrderSide; quantity: number; price: number; commission: number;
  slippage_pct: number; timestamp: string;
}

export interface PerformanceMetrics {
  account_id: string; period: string; total_return_pct: number;
  annualized_return_pct: number | null; sharpe_ratio: number | null;
  max_drawdown_pct: number; win_rate_pct: number; total_trades: number;
  benchmark_return_pct: number; excess_return_pct: number;
  equity_curve: { date: string; equity: number; daily_return: number; benchmark_equity: number }[];
}

export interface DebateRecord {
  id: string; session_id: string; debate_type: "investment" | "risk";
  round_num: number; speaker: string; role: string;
  claim: string; evidence: string[]; rebuttal_to: string | null;
  timestamp: string;
}

export type ApprovalStatus = "pending" | "approved" | "rejected" | "modified" | "timed_out";

export interface Approval {
  id: string;
  strategy_id?: string;
  account_id?: string;
  session_id?: string;
  decision_id?: string;
  ticker?: string;
  status: ApprovalStatus;
  triggered_rules?: string[];
  triggered_rules_json?: string;
  approval_reason?: string;
  original_action?: string;
  original_target_position_pct?: number;
  original_confidence?: number;
  original_decision?: Record<string, unknown>;
  modified_params?: Record<string, unknown> | null;
  modified_action?: string;
  modified_target_position_pct?: number | null;
  cross_review_model?: string | null;
  cross_review_result?: string | null;
  cross_review_consensus?: boolean;
  reviewer: string | null;
  reviewer_notes: string;
  pm_report?: string;
  created_at: string;
  resolved_at?: string | null;
  decided_at?: string | null;
  timeout_at?: string;
}

export interface Conversation {
  id: string; title: string; created_at: string; updated_at: string;
  tags: string[]; is_saved: boolean; description: string;
}

export interface DailyBrief {
  id: string; type: "morning_brief" | "midday_update" | "event_alert";
  title: string; summary: string; content: string;
  key_events: string[]; tickers_covered: string[];
  market_data?: Record<string, Record<string, { name: string; price: number | null; change_pct: number | null; currency: string }>>;
  news_count?: number; elapsed_s?: number;
  generated_at: string;
}

export interface InsightFeedback {
  insight_id: string; rating: number; was_direction_correct: boolean | null;
  comment: string;
}

export const scannerFields = [
  "price",
  "change_pct",
  "volume",
  "rsi14",
  "sma20",
  "sma50",
  "pe_ratio",
  "pb_ratio",
  "market_cap",
  "sector",
] as const;

export type ScannerField = (typeof scannerFields)[number];
export type ScannerOperator = "<" | ">" | "<=" | ">=" | "==" | "between";
export type ScannerMode = "rule" | "agent" | "belief";
export type ScanRunStatus = "running" | "completed" | "failed";
export type ScannerUniverseSource = "market_store" | "strategy" | "watchlist";

export type ScanCondition = {
  readonly field: ScannerField;
  readonly operator: ScannerOperator;
  readonly value: number | string;
  readonly value2: number | string | null;
};

export type ScannerSnapshotValue = {
  readonly value: number | string | null;
  readonly unit: string;
  readonly currency: string | null;
  readonly source: string | null;
  readonly as_of: string | null;
};

export type ScannerSnapshot = {
  readonly ticker: string;
  readonly price: ScannerSnapshotValue;
  readonly change_pct: ScannerSnapshotValue;
  readonly volume: ScannerSnapshotValue;
  readonly rsi14: ScannerSnapshotValue;
  readonly sma20: ScannerSnapshotValue;
  readonly sma50: ScannerSnapshotValue;
  readonly pe_ratio: ScannerSnapshotValue;
  readonly pb_ratio: ScannerSnapshotValue;
  readonly market_cap: ScannerSnapshotValue;
  readonly sector: ScannerSnapshotValue;
};

export type TrackedTicker = {
  readonly ticker: string;
  readonly provenance: readonly ScannerUniverseSource[];
};

export type ScanResult = {
  readonly ticker: string;
  readonly match_score: number;
  readonly matched_conditions: readonly ScanCondition[];
  readonly snapshot: ScannerSnapshot;
  readonly provenance: readonly ScannerUniverseSource[];
  readonly source_dates: Readonly<Record<string, string>>;
};

export type ScannerResponse = {
  readonly universe: readonly TrackedTicker[];
  readonly results: readonly ScanResult[];
  readonly scanned_count: number;
  readonly matched_count: number;
  readonly missing_data_count: number;
  readonly warnings: readonly string[];
  readonly scanned_at: string;
};

export type ScanRunError = {
  readonly code: "scanner_failed" | "invalid_tool_output" | "llm_unavailable";
  readonly message: string;
};

export type ScanRun = {
  readonly id: string;
  readonly input: Readonly<Record<string, unknown>>;
  readonly compiled_conditions: readonly ScanCondition[] | null;
  readonly result: ScannerResponse | null;
  readonly error: ScanRunError | null;
  readonly status: ScanRunStatus;
  readonly mode: ScannerMode;
  readonly strategy_id: string | null;
  readonly created_at: string;
  readonly completed_at: string | null;
  readonly updated_at: string;
};

export type ScannerRuleRequest = {
  readonly conditions: readonly ScanCondition[];
  readonly universe?: "tracked";
};

export type ScannerAgentRequest = {
  readonly mode: "agent";
  readonly query: string;
};

export type ScannerBeliefRequest = {
  readonly mode: "belief";
  readonly strategy_id: string;
  readonly belief_text: string;
};

export type ScanRunListResponse = {
  readonly items: readonly ScanRun[];
  readonly total: number;
};

export type AlertType = "price_above" | "price_below" | "rsi_above" | "rsi_below" | "volume_spike" | "news_event" | "agent_flag";

export interface Alert {
  id: string; watchlist_id: string | null; ticker: string; type: AlertType;
  threshold_value: number | string | null; message: string;
  notification_channels?: string[] | null;
  is_triggered: boolean; triggered_at: string | null; created_at: string;
}

export interface Watchlist {
  id: string; name: string; tickers: string[]; alerts: Alert[];
  notes: Record<string, string>; created_at: string; updated_at: string;
}

export type ReportType = "stock" | "sector";
export type ReportStatus = "pending" | "running" | "completed" | "failed";
export type StockReportSection = "decision" | "market" | "news" | "fundamentals" | "risk";
export type SectorReportSection = "overview" | "constituents" | "decision" | "data_gaps" | "sources";

export interface ReportJob {
  readonly id: string;
  readonly report_type: ReportType;
  readonly title: string;
  readonly tickers: readonly string[];
  readonly source_type: string;
  readonly source_ids: readonly string[];
  readonly parameters: Readonly<Record<string, object>>;
  readonly status: ReportStatus;
  readonly error: string | null;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly updated_at: string;
}

export type StockReportRequest = {
  readonly ticker: string;
  readonly strategy_id: string;
  readonly session_id?: string;
  readonly sections: readonly StockReportSection[];
};

export type SectorReportRequest = {
  readonly scan_run_id: string;
  readonly sections: readonly SectorReportSection[];
};

export type ReportListResponse = {
  readonly items: readonly ReportJob[];
  readonly total: number;
};

export interface SystemEvent {
  id: string; session_id: string; strategy_id: string | null;
  event_type: string; actor: string; payload: Record<string, unknown>;
  timestamp: string;
}

export type LlmApiKeySource = "settings" | "properties.env" | "missing";
export type NotificationChannelName = "email" | "telegram" | "wechat" | "whatsapp";
export type NotificationChannelStatus = {
  readonly configured: boolean;
  readonly missing_fields: readonly string[];
};

export interface SystemConfig {
  llm_api_key: string; llm_base_url: string; llm_model: string;
  deep_think_model: string; email_smtp_host: string; email_smtp_port: number;
  email_username: string; email_password: string; email_sender: string;
  email_use_tls: boolean; email_recipients: string[];
  telegram_bot_token: string; telegram_chat_ids: string[];
  wechat_webhook_url: string;
  whatsapp_access_token: string; whatsapp_phone_number_id: string;
  whatsapp_recipients: string[];
  data_cache_ttl_minutes: number; news_fetch_interval_minutes: number;
  max_concurrent_analyses: number; memory_enabled: boolean;
  memory_retention_days: number; weekly_reflection_day: string;
  weekly_reflection_time: string; mcp_external_servers: Record<string, unknown>;
  llm_api_key_configured?: boolean;
  llm_api_key_source?: LlmApiKeySource;
  llm_api_key_length?: number;
  notification_status: Record<NotificationChannelName, NotificationChannelStatus>;
}

export type BacktestFrequency = "daily" | "weekly" | "monthly";
export type BacktestMode = "deterministic" | "agent_experiment";
export type BacktestJobStatus = "pending" | "running" | "completed" | "failed";

export type BacktestRequest = {
  readonly strategy_id: string;
  readonly ticker: string;
  readonly date_from: string;
  readonly date_to: string;
  readonly frequency: BacktestFrequency;
  readonly benchmark: string;
  readonly mode: BacktestMode;
};

export type BacktestJobAcceptedResponse = {
  readonly id: string;
  readonly status: "pending";
  readonly contract_version: 1;
};

export type PerformanceMetricsView = {
  readonly cumulative_return_pct: number | null;
  readonly total_return_pct: number | null;
  readonly annualized_return_pct: number | null;
  readonly annualized_volatility_pct: number | null;
  readonly benchmark_return_pct: number | null;
  readonly excess_return_pct: number | null;
  readonly max_drawdown_pct: number | null;
  readonly max_drawdown_duration: number;
  readonly sharpe_ratio: number | null;
  readonly win_rate_pct: number | null;
  readonly profit_factor: number | null;
  readonly avg_win: number | null;
  readonly avg_loss: number | null;
  readonly payoff_ratio: number | null;
  readonly number_of_trades: number;
  readonly number_of_fills: number;
  readonly number_of_orders: number;
  readonly number_of_rejections: number;
  readonly number_of_closed_trades: number;
  readonly avg_holding_period_days: number;
  readonly realized_pnl_usd: number;
  readonly unrealized_pnl_usd: number;
  readonly net_pnl_usd: number;
  readonly total_fees_usd: number;
  readonly total_slippage_usd: number;
  readonly turnover_pct: number;
  readonly average_daily_gross_exposure_pct: number;
};

export type BacktestConfigView = {
  readonly ticker: string;
  readonly start_date: string;
  readonly end_date: string;
  readonly frequency: BacktestFrequency;
  readonly benchmark_symbol: string;
  readonly strategy_id: string;
  readonly account_id: string;
  readonly mode: BacktestMode;
  readonly agent_model: string | null;
  readonly strategy_snapshot_hash: string;
  readonly policy_hash: string;
  readonly data_snapshot_hash: string;
  readonly engine_version: string;
  readonly strategy_execution_frequency: BacktestFrequency;
  readonly run_frequency: BacktestFrequency;
  readonly initial_capital: number;
  readonly commission_rate: number;
  readonly commission_bps: number;
  readonly slippage_rate: number;
  readonly slippage_bps: number;
  readonly execution_timing: "next_open" | "close_bar";
  readonly max_position_pct: number;
  readonly allow_short: boolean;
  readonly provider_adjustment_mode: string;
  readonly corporate_actions_mode: string;
  readonly data_provider: string;
  readonly data_provider_version: string;
  readonly data_interval: "1d";
  readonly data_auto_adjust: boolean;
  readonly data_actions: boolean;
  readonly data_end_exclusive: string;
  readonly data_lookback_days: number;
  readonly data_provider_buffer_days: number;
  readonly data_provider_end_semantics: "exclusive";
  readonly data_provider_timezone: string;
  readonly data_timezone_normalization: "exchange_session_date_to_UTC_midnight";
  readonly warmup_bars: number;
  readonly risk_free_rate: number;
  readonly periods_per_year: number;
  readonly max_drawdown_limit_pct: number;
  readonly max_drawdown_limit_enforced: boolean;
  readonly evaluation_bar_count: number;
  readonly sample_first_date: string;
  readonly sample_last_date: string;
};

export type BacktestProgressView = {
  readonly bars_total: number;
  readonly bars_processed: number;
  readonly decisions_total: number;
  readonly decisions_eligible: number;
  readonly decisions_not_ready: number;
  readonly decisions_completed: number;
  readonly current_decision_date: string | null;
};

export type BacktestDecisionView = {
  readonly sequence: number;
  readonly signal_date: string;
  readonly execution_date: string | null;
  readonly status: "not_ready" | "completed" | "failed" | "unfilled_end_of_window";
  readonly attempts: number;
  readonly target_position_pct: number | null;
  readonly confidence: number | null;
  readonly action: "BUY" | "SELL" | "HOLD" | null;
  readonly rationale: string | null;
  readonly feature_hash: string | null;
  readonly policy_hash: string;
  readonly error_code: string | null;
  readonly error_stage: string | null;
};

export type BacktestOrderEvidenceView = {
  readonly order_id: string;
  readonly status: "pending" | "executed" | "cancelled" | "rejected" | "unfilled";
  readonly signal_date: string;
  readonly execution_date: string | null;
  readonly reason: string;
  readonly ticker: string | null;
  readonly side: "BUY" | "SELL" | null;
  readonly quantity: number | null;
  readonly order_type: "MARKET" | "LIMIT" | null;
  readonly limit_price: number | null;
};

export type BacktestTradeView = {
  readonly order_id: string;
  readonly timestamp: string;
  readonly ticker: string;
  readonly side: "buy" | "sell";
  readonly quantity: number;
  readonly price: number;
  readonly fee: number;
  readonly slippage: number;
  readonly trade_value: number;
  readonly realized_pnl: number;
  readonly cash_after: number;
  readonly equity_after: number;
  readonly shares_after: number;
  readonly avg_cost_after: number;
  readonly strategy_id: string;
  readonly account_id: string;
  readonly session_id: string;
  readonly decision_id: string;
};

export type ClosedTradeView = {
  readonly entry_at: string;
  readonly exit_at: string;
  readonly ticker: string;
  readonly quantity: number;
  readonly entry_vwap: number;
  readonly exit_vwap: number;
  readonly average_cost_basis: number;
  readonly net_realized_pnl: number;
  readonly fees: number;
  readonly slippage: number;
  readonly holding_period_trading_days: number;
  readonly strategy_id: string;
  readonly account_id: string;
  readonly session_id: string;
  readonly decision_id: string;
};

export type BacktestSeriesPointView = {
  readonly date: string;
  readonly strategy_equity: number;
  readonly benchmark_equity: number | null;
  readonly strategy_drawdown_pct: number;
  readonly benchmark_drawdown_pct: number | null;
};

export type BacktestNoTradeReasonView = {
  readonly code: "no_signals" | "not_ready" | "all_hold" | "all_rejected";
  readonly count: number;
};

export type BacktestEndPositionView = {
  readonly ticker: string;
  readonly shares: number;
  readonly market_value: number;
  readonly average_cost_basis: number;
  readonly unrealized_pnl: number;
  readonly liquidated_at_end: boolean;
};

export type BacktestProvenanceView = {
  readonly strategy_snapshot_hash: string;
  readonly policy_hash: string;
  readonly data_snapshot_hash: string;
  readonly canonical_result_hash: string;
};

export type BacktestSnapshotEvidenceView = {
  readonly compressed_bytes: number;
  readonly uncompressed_bytes: number;
};

export type BacktestJobResult = {
  readonly outcome: "completed" | "completed_no_trades";
  readonly warnings: readonly string[];
  readonly no_trade_reasons: readonly BacktestNoTradeReasonView[];
  readonly metrics: PerformanceMetricsView;
  readonly equity: readonly BacktestSeriesPointView[];
  readonly orders: readonly BacktestOrderEvidenceView[];
  readonly fills: readonly BacktestTradeView[];
  readonly closed_trades: readonly ClosedTradeView[];
  readonly end_position: BacktestEndPositionView;
  readonly snapshot: BacktestSnapshotEvidenceView | null;
  readonly provenance: BacktestProvenanceView;
};

export type BacktestJobError = {
  readonly code:
    | "agent_failed"
    | "backtest_failed"
    | "execution_failed"
    | "interrupted"
    | "market_data_unavailable"
    | "storage_corrupt"
    | "decision_context_invalid"
    | "decision_policy_invalid"
    | "decision_transient_exhausted"
    | "provider_failed"
    | "decision_schema_invalid"
    | "insufficient_history";
  readonly stage: string | null;
  readonly decision_date: string | null;
  readonly attempt: number | null;
  readonly message: string;
};

export type BacktestJobResponse = {
  readonly id: string;
  readonly status: BacktestJobStatus;
  readonly request: BacktestRequest | null;
  readonly config: BacktestConfigView | null;
  readonly progress: BacktestProgressView;
  readonly decisions: readonly BacktestDecisionView[];
  readonly result: BacktestJobResult | null;
  readonly error: BacktestJobError | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type RiskStatus = "unavailable" | "invalid" | "partial" | "complete";

export type DecisionTarget = {
  readonly decision_id: string;
  readonly ticker: string;
  readonly target_position_pct: number;
  readonly weight: number;
  readonly created_at: string;
};

export type DecisionTargetExposure = {
  readonly status: RiskStatus;
  readonly source: "decision_target";
  readonly strategy_id: string;
  readonly as_of: string | null;
  readonly decision_ids: readonly string[];
  readonly decisions: readonly DecisionTarget[];
  readonly weights: Readonly<Record<string, number>>;
  readonly cash_weight: number | null;
  readonly gross_exposure: number | null;
  readonly warnings: readonly string[];
};

export type DatedReturn = {
  readonly date: string;
  readonly value: number;
};

export type CorrelationResult = {
  readonly status: RiskStatus;
  readonly labels: readonly string[];
  readonly matrix: readonly (readonly (number | null)[])[];
  readonly warnings: readonly string[];
};

export type ConcentrationResult = {
  readonly weights: Readonly<Record<string, number>>;
  readonly herfindahl_index: number;
  readonly largest_label: string | null;
  readonly largest_weight: number;
};

export type RiskOverview = {
  readonly status: RiskStatus;
  readonly source: "decision_target";
  readonly strategy_id: string;
  readonly as_of: string | null;
  readonly return_unit: "decimal";
  readonly exposure: DecisionTargetExposure;
  readonly observation_count: number;
  readonly common_dates: readonly string[];
  readonly portfolio_returns: readonly number[];
  readonly cumulative_curve: readonly DatedReturn[];
  readonly drawdown_curve: readonly DatedReturn[];
  readonly var_95: number | null;
  readonly var_99: number | null;
  readonly cvar_95: number | null;
  readonly max_drawdown: number | null;
  readonly correlation: CorrelationResult;
  readonly ticker_concentration: ConcentrationResult;
  readonly sector_concentration: ConcentrationResult;
  readonly warnings: readonly string[];
};

export type StressTestRequest = {
  readonly uniform_market_shock: number;
  readonly lookback_days?: number;
};

export type StressResult = {
  readonly status: RiskStatus;
  readonly source: "decision_target";
  readonly strategy_id: string;
  readonly as_of: string | null;
  readonly return_unit: "decimal";
  readonly decision_ids: readonly string[];
  readonly historical_worst_day: {
    readonly date: string | null;
    readonly impact: number | null;
    readonly source: "historical_portfolio_returns";
  };
  readonly uniform_market_shock: {
    readonly shock: number;
    readonly gross_exposure: number | null;
    readonly impact: number | null;
    readonly assumption: "uniform_market_shock";
  };
  readonly warnings: readonly string[];
};

export interface CreateSkillRequest {
  name: string; category: SkillCategory; description: string;
  tools: string[]; prompt_template: string;
}

export interface PaginatedResponse<T> {
  items: T[]; total: number; page: number;
}

export interface ApiError {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export interface ApprovalActionRequest { reviewer: string; notes?: string; modified_action?: string; modified_target_position_pct?: number; }
export interface WatchlistCreateRequest { name: string; tickers: string[]; }
export interface AddTickerRequest { ticker: string; }
export interface CreateAlertRequest { ticker: string; type: AlertType; threshold_value: number | string; notification_channels?: string[] | null; }
export interface AnalyzeBatchRequest { tickers: string[]; mode?: string; }
export interface CreateKnowledgeEntryRequest { type: "rule" | "finding" | "failure"; title: string; content: string; confidence?: number; source_session_id?: string; }
export interface CreateHypothesisRequest { claim: string; acceptance_criteria: string; budget_rounds?: number; }
export interface AddMCPServerRequest { name: string; command: string; args: string[]; enabled?: boolean; }
export interface MCPStatus { running: boolean; transport: string; tools_exposed: number; connected_clients: number; }
export interface MCPServer { name: string; command: string; args: string[]; enabled: boolean; tools_count: number; }
export interface AlphaFactor { id: string; zoo: string; name: string; expression: string; theme: string; source: string; }
export interface HealthResponse { status: string; uptime_seconds: number; version: string; }
export type CreateStrategyRequest = Omit<StrategyConfig, "id" | "created_at" | "updated_at" | "status"> & { status?: StrategyStatus; };
export type UpdateStrategyRequest = Partial<CreateStrategyRequest>;
export interface Hypothesis { id: string; strategy_id: string; status: string; claim: string; acceptance_criteria: string; evidence: { session_id: string; result: string; note: string; timestamp: string }[]; open_items: string[]; budget_rounds: number; completed_rounds: number; created_at: string; resolved_at: string | null; }

// ── MonitorTask types ─────────────────────────────────────
export type MonitorMode = "keyword" | "ticker" | "domain";
export interface MonitorTargets { keywords?: string[]; tickers?: string[]; domain_prompt?: string; }
export interface MonitorSchedule { frequency: string; time?: string; days?: string[]; }
export interface MonitorAgentConfig { enabled: boolean; auto_discover?: boolean; }
export interface MonitorOutput { format?: string; language?: string; }

export interface MonitorTask {
  id: string; name: string; description: string; mode: MonitorMode;
  targets: MonitorTargets; sources: string[]; schedule: MonitorSchedule;
  agent: MonitorAgentConfig; output: MonitorOutput;
  cron_expression?: string;
  expanded_keywords?: string[];
  expanded_tickers?: string[];
  report_language?: string;
  run_status?: "idle" | "running" | "failed";
  current_run_id?: string | null;
  last_run_started_at?: string | null;
  last_run_finished_at?: string | null;
  last_run_error?: string;
  status: string; created_at: string; updated_at: string; last_run_at: string | null;
}

export interface MonitoringReport {
  id: string; monitor_id: string; session_id: string;
  title?: string; summary: string; key_findings: string[]; sentiment: string;
  related_tickers: string[]; alerts: { level: string; message: string }[];
  raw_data: Record<string, unknown>; generated_at: string;
  report_type?: string; content_text?: string; content?: string;
}

export interface MonitorNewsItem {
  id: string; monitor_id: string;
  title: string; summary: string; url: string;
  source_name: string; published_at: string | null;
  relevance_score: number; fetched_at: string;
}

export type CreateMonitorRequest = Omit<MonitorTask, "id" | "created_at" | "updated_at" | "last_run_at"> & { status?: string; expand_keywords?: boolean; };
export type UpdateMonitorRequest = Partial<CreateMonitorRequest>;
