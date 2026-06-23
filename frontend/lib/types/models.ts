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
};

export type SSEErrorEvent = {
  agent: string;
  error: string;
  timestamp?: string;
};

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
  id: string; strategy_id: string; decision_id: string; status: ApprovalStatus;
  triggered_rules: string[]; original_decision: Record<string, unknown>;
  modified_params: Record<string, unknown> | null;
  cross_review_model: string | null; cross_review_result: string | null;
  cross_review_consensus: boolean; reviewer: string | null;
  reviewer_notes: string; created_at: string; resolved_at: string | null;
  timeout_at: string;
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

export interface ScanCondition {
  field: string; operator: "<" | ">" | "<=" | ">=" | "==" | "between";
  value: number | string; value2: number | null;
}

export interface ScannerQuery {
  id: string; name: string; type: "rule" | "agent" | "belief";
  conditions: ScanCondition[]; natural_language: string;
  belief_id: string | null; created_at: string;
}

export interface ScanResult {
  query_id: string; ticker: string; match_score: number;
  matched_conditions: string[]; explanation: string;
  snapshot_data: Record<string, unknown>; scanned_at: string;
}

export type AlertType = "price_above" | "price_below" | "rsi_above" | "rsi_below" | "volume_spike" | "news_event" | "agent_flag";

export interface Alert {
  id: string; watchlist_id: string | null; ticker: string; type: AlertType;
  threshold_value: number | string | null; message: string;
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

export interface SystemConfig {
  llm_api_key: string; llm_base_url: string; llm_model: string;
  deep_think_model: string; email_smtp_host: string; email_smtp_port: number;
  email_recipients: string[]; telegram_bot_token: string; telegram_chat_ids: string[];
  wechat_webhook_url: string; feishu_webhook_url: string;
  discord_webhook_url: string; slack_bot_token: string; slack_channel_id: string;
  data_cache_ttl_minutes: number; news_fetch_interval_minutes: number;
  max_concurrent_analyses: number; memory_enabled: boolean;
  memory_retention_days: number; weekly_reflection_day: string;
  weekly_reflection_time: string; mcp_external_servers: Record<string, unknown>;
}

export interface BacktestRequest {
  strategy_config?: Partial<StrategyConfig>;
  tickers: string[]; date_from: string; date_to: string;
  forward_days?: number; frequency?: "daily" | "weekly" | "monthly";
  benchmark?: string;
}

export interface BacktestResult {
  status: "pending" | "running" | "completed" | "failed"; backtest_id: string;
  summary?: {
    total_predictions: number; accuracy_pct: number;
    cumulative_return_pct: number; benchmark_return_pct: number;
    excess_return_pct: number; information_ratio: number; sharpe_ratio: number;
  };
  results?: {
    date: string; ticker: string; predicted_direction: string;
    confidence: number; actual_direction: string; actual_return_pct: number;
    benchmark_return_pct: number; was_correct: boolean;
  }[];
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

export interface ApprovalActionRequest { reviewer: string; notes?: string; modified_params?: Record<string, unknown>; }
export interface WatchlistCreateRequest { name: string; tickers: string[]; }
export interface AddTickerRequest { ticker: string; }
export interface CreateAlertRequest { ticker: string; type: AlertType; threshold_value: number | string; }
export interface ScannerRuleRequest { conditions: ScanCondition[]; universe?: string; }
export interface ScannerAgentRequest { query: string; universe?: string; }
export interface ScannerBeliefRequest { belief_id: string; universe?: string; }
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
