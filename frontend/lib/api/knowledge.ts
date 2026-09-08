import { api } from "./client";
import type {
  KnowledgeEntry,
  CreateKnowledgeEntryRequest,
  Hypothesis,
  CreateHypothesisRequest,
} from "@/lib/types/models";

export const knowledgeApi = {
  list(
    strategyId: string,
    params?: {
      type?: string;
      page?: number;
      limit?: number;
    }
  ): Promise<{ entries: KnowledgeEntry[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.type) sp.set("type", params.type);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("limit", String(params.limit));
    return api.get(
      `/strategies/${strategyId}/knowledge?${sp.toString()}`
    );
  },

  create(
    strategyId: string,
    data: CreateKnowledgeEntryRequest
  ): Promise<KnowledgeEntry> {
    return api.post(`/strategies/${strategyId}/knowledge`, data);
  },

  update(
    strategyId: string,
    entryId: string,
    data: Partial<CreateKnowledgeEntryRequest>
  ): Promise<KnowledgeEntry> {
    return api.put(
      `/strategies/${strategyId}/knowledge/${entryId}`,
      data
    );
  },

  delete(strategyId: string, entryId: string): Promise<void> {
    return api.delete(`/strategies/${strategyId}/knowledge/${entryId}`);
  },

  search(
    strategyId: string,
    q: string,
    type?: string
  ): Promise<{ entries: KnowledgeEntry[] }> {
    const sp = new URLSearchParams();
    sp.set("q", q);
    if (type) sp.set("type", type);
    return api.get(
      `/strategies/${strategyId}/knowledge/search?${sp.toString()}`
    );
  },

  // ── Hypotheses ───────────────────────────────────────

  listHypotheses(
    strategyId: string,
    params?: { status?: string }
  ): Promise<{ hypotheses: Hypothesis[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.status) sp.set("status", params.status);
    return api.get(
      `/strategies/${strategyId}/hypotheses?${sp.toString()}`
    );
  },

  createHypothesis(
    strategyId: string,
    data: CreateHypothesisRequest
  ): Promise<Hypothesis> {
    return api.post(`/strategies/${strategyId}/hypotheses`, data);
  },

  getHypothesis(
    strategyId: string,
    hypothesisId: string
  ): Promise<Hypothesis> {
    return api.get(
      `/strategies/${strategyId}/hypotheses/${hypothesisId}`
    );
  },

  updateHypothesis(
    strategyId: string,
    hypothesisId: string,
    data: Partial<Hypothesis>
  ): Promise<Hypothesis> {
    return api.put(
      `/strategies/${strategyId}/hypotheses/${hypothesisId}`,
      data
    );
  },

  addEvidence(
    strategyId: string,
    hypothesisId: string,
    sessionId: string,
    result: string,
    note: string
  ): Promise<void> {
    return api.post(
      `/strategies/${strategyId}/hypotheses/${hypothesisId}/evidence`,
      { session_id: sessionId, result, note }
    );
  },
};
