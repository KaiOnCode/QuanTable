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

export interface Report {
  id: string; type: "stock_deep_dive" | "sector_analysis";
  title: string; tickers: string[]; content_path: string;
  generated_at: string; parameters: Record<string, unknown>;
}

export interface SystemEvent {
  id: string; session_id: string; strategy_id: string | null;
  event_type: string; actor: string; payload: Record<string, unknown>;
  timestamp: string;
}

export type LlmApiKeySource = "settings" | "properties.env" | "missing";

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
}

export interface BacktestRequest {
  strategy_id: string;
  ticker: string;
  date_from: string;
  date_to: string;
  frequency: "daily" | "weekly" | "monthly";
  benchmark: string;
}

export interface PerformanceMetricsView {
  cumulative_return_pct: number;
  total_return_pct: number;
  annualized_return_pct: number;
  benchmark_return_pct: number;
  excess_return_pct: number;
  max_drawdown_pct: number;
  max_drawdown_duration: number;
  sharpe_ratio: number;
  win_rate_pct: number;
  profit_factor: number;
  avg_win: number;
  avg_loss: number;
  payoff_ratio: number;
  number_of_trades: number;
  avg_holding_period_days: number;
}

export interface BacktestConfigView {
  ticker: string;
  start_date: string;
  end_date: string;
  frequency: "daily" | "weekly" | "monthly";
  benchmark_symbol: string;
  strategy_id: string;
  account_id: string;
}

export interface BacktestSeriesPointView {
  date: string;
  strategy_equity: number;
  benchmark_equity: number;
  strategy_drawdown_pct: number;
  benchmark_drawdown_pct: number;
}

export interface BacktestTradeView {
  order_id: string;
  timestamp: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  fee: number;
  slippage: number;
  trade_value: number;
  realized_pnl: number;
  cash_after: number;
  equity_after: number;
  shares_after: number;
  avg_cost_after: number;
  strategy_id: string;
  account_id: string;
  session_id: string;
  decision_id: string;
}

export interface BacktestResultView {
  status: "completed";
  config: BacktestConfigView;
  summary: PerformanceMetricsView;
  series: BacktestSeriesPointView[];
  trades: BacktestTradeView[];
}

export interface BacktestJobError {
  code: "backtest_failed" | "interrupted" | "storage_corrupt";
  message: string;
}

export interface BacktestJobResponse {
  backtest_id: string;
  status: "pending" | "running" | "completed" | "failed";
  result: BacktestResultView | null;
  error: BacktestJobError | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  updated_at: string;
}

export interface VarResponse {
  var_95: number; cvar_95: number; var_99: number;
  method: string; lookback_days: number;
}

export interface StressTestRequest {
  scenario?: string; market_shock_pct?: number;
  vix_spike?: number; rate_change_bps?: number;
}

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
