import { api } from "./client";
import type {
  StrategyConfig,
  CreateStrategyRequest,
  UpdateStrategyRequest,
  TradingBelief,
  Account,
  Position,
  PerformanceMetrics,
  Trade,
  PaginatedResponse,
  SystemEvent,
  DebateRecord,
  Approval,
} from "@/lib/types/models";

const BASE = "/strategies";

export type StrategyDecision = {
  readonly id: string;
  readonly ticker: string;
  readonly action: string | null;
  readonly direction: string | null;
  readonly confidence: number | null;
  readonly report: string | null;
  readonly winning_belief: string | null;
  readonly created_at: string;
};

// ── Strategy CRUD ─────────────────────────────────────

export const strategiesApi = {
  list(params?: {
    type?: string;
    status?: string;
    tag?: string;
    page?: number;
    limit?: number;
  }): Promise<PaginatedResponse<StrategyConfig>> {
    const sp = new URLSearchParams();
    if (params?.type) sp.set("type", params.type);
    if (params?.status) sp.set("status", params.status);
    if (params?.tag) sp.set("tag", params.tag);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("limit", String(params.limit));
    return api.get(`${BASE}?${sp.toString()}`);
  },

  create(data: CreateStrategyRequest): Promise<StrategyConfig> {
    return api.post(BASE, data);
  },

  get(strategyId: string): Promise<StrategyConfig> {
    return api.get(`${BASE}/${strategyId}`);
  },

  update(
    strategyId: string,
    data: UpdateStrategyRequest
  ): Promise<StrategyConfig> {
    return api.put(`${BASE}/${strategyId}`, data);
  },

  delete(strategyId: string, confirm = true): Promise<void> {
    return api.delete(`${BASE}/${strategyId}?confirm=${confirm}`);
  },

  clone(
    strategyId: string,
    name: string
  ): Promise<StrategyConfig> {
    return api.post(`${BASE}/${strategyId}/clone`, { name });
  },

  start(strategyId: string): Promise<void> {
    return api.post(`${BASE}/${strategyId}/start`);
  },

  pause(strategyId: string): Promise<void> {
    return api.post(`${BASE}/${strategyId}/pause`);
  },

  stop(strategyId: string, liquidate = false): Promise<void> {
    return api.post(`${BASE}/${strategyId}/stop`, { liquidate });
  },

  // ── Agents ──────────────────────────────────────────

  getAgents(strategyId: string): Promise<{
    active_agents: string[];
    debate_rounds: number;
    risk_debate_rounds: number;
    enable_cross_review: boolean;
  }> {
    return api.get(`${BASE}/${strategyId}/agents`);
  },

  updateAgents(
    strategyId: string,
    data: {
      active_agents?: string[];
      debate_rounds?: number;
      risk_debate_rounds?: number;
      enable_cross_review?: boolean;
    }
  ): Promise<void> {
    return api.put(`${BASE}/${strategyId}/agents`, data);
  },

  // ── Beliefs ─────────────────────────────────────────

  getBeliefs(strategyId: string): Promise<TradingBelief[]> {
    return api.get(`${BASE}/${strategyId}/beliefs`);
  },

  addBelief(
    strategyId: string,
    text: string,
    weight?: number
  ): Promise<TradingBelief> {
    return api.post(`${BASE}/${strategyId}/beliefs`, { text, weight });
  },

  updateBelief(
    strategyId: string,
    beliefId: string,
    data: { text?: string; weight?: number }
  ): Promise<TradingBelief> {
    return api.put(`${BASE}/${strategyId}/beliefs/${beliefId}`, data);
  },

  deleteBelief(strategyId: string, beliefId: string): Promise<void> {
    return api.delete(`${BASE}/${strategyId}/beliefs/${beliefId}`);
  },

  // ── Performance ─────────────────────────────────────

  getAccount(strategyId: string): Promise<Account> {
    return api.get(`${BASE}/${strategyId}/account`);
  },

  getPositions(strategyId: string): Promise<{
    positions: Position[];
    total_value: number;
  }> {
    return api.get(`${BASE}/${strategyId}/positions`);
  },

  getPerformance(
    strategyId: string,
    params?: { period?: string; benchmark?: string }
  ): Promise<PerformanceMetrics> {
    const sp = new URLSearchParams();
    if (params?.period) sp.set("period", params.period);
    if (params?.benchmark) sp.set("benchmark", params.benchmark);
    return api.get(`${BASE}/${strategyId}/performance?${sp.toString()}`);
  },

  getTrades(
    strategyId: string,
    params?: {
      ticker?: string;
      from?: string;
      to?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<PaginatedResponse<Trade>> {
    const sp = new URLSearchParams();
    if (params?.ticker) sp.set("ticker", params.ticker);
    if (params?.from) sp.set("from", params.from);
    if (params?.to) sp.set("to", params.to);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("limit", String(params.limit));
    return api.get(`${BASE}/${strategyId}/trades?${sp.toString()}`);
  },

  getDecisions(
    strategyId: string,
    params?: {
      ticker?: string;
      from?: string;
      to?: string;
    }
  ): Promise<{
    readonly decisions: readonly StrategyDecision[];
    readonly total: number;
  }> {
    const sp = new URLSearchParams();
    if (params?.ticker) sp.set("ticker", params.ticker);
    if (params?.from) sp.set("from", params.from);
    if (params?.to) sp.set("to", params.to);
    return api.get(`${BASE}/${strategyId}/decisions?${sp.toString()}`);
  },

  getDebates(
    strategyId: string,
    params?: { session_id?: string; from?: string; to?: string }
  ): Promise<{ debates: DebateRecord[] }> {
    const sp = new URLSearchParams();
    if (params?.session_id) sp.set("session_id", params.session_id);
    if (params?.from) sp.set("from", params.from);
    if (params?.to) sp.set("to", params.to);
    return api.get(`${BASE}/${strategyId}/debates?${sp.toString()}`);
  },

  getEvents(
    strategyId: string,
    sessionId: string
  ): Promise<{ events: SystemEvent[]; session_id: string }> {
    return api.get(
      `${BASE}/${strategyId}/events?session_id=${sessionId}`
    );
  },

  // ── Approvals ───────────────────────────────────────

  getApprovals(
    strategyId: string
  ): Promise<{ pending: Approval[]; total_pending: number }> {
    return api.get(`${BASE}/${strategyId}/approvals`);
  },
};
