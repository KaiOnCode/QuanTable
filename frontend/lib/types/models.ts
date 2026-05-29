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
  target_position_pct?: number;
  debate_records?: SSEDebateEvent[];
  elapsed_s?: number;
};

export type SSEErrorEvent = {
  agent: string;
  error: string;
  timestamp?: string;
};
