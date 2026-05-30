import { api } from "./client";
import type { MemoryRecord, Reflection, PreTradeCheck } from "@/lib/types/models";

export const memoryApi = {
  list(
    strategyId: string,
    params?: {
      ticker?: string;
      limit?: number;
      min_score?: number;
    }
  ): Promise<{ memories: MemoryRecord[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.ticker) sp.set("ticker", params.ticker);
    if (params?.limit) sp.set("limit", String(params.limit));
    if (params?.min_score) sp.set("min_score", String(params.min_score));
    return api.get(
      `/strategies/${strategyId}/memory?${sp.toString()}`
    );
  },

  get(strategyId: string, memoryId: string): Promise<MemoryRecord> {
    return api.get(`/strategies/${strategyId}/memory/${memoryId}`);
  },

  search(
    strategyId: string,
    query: string,
    limit?: number,
    minSimilarity?: number
  ): Promise<{ memories: MemoryRecord[] }> {
    return api.post(`/strategies/${strategyId}/memory/search`, {
      query,
      limit: limit || 10,
      min_similarity: minSimilarity || 0.6,
    });
  },

  getReflections(
    strategyId: string,
    params?: { page?: number; limit?: number }
  ): Promise<{ reflections: Reflection[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.page) sp.set("page", String(params.page));
    if (params?.limit) sp.set("limit", String(params.limit));
    return api.get(
      `/strategies/${strategyId}/reflections?${sp.toString()}`
    );
  },

  getReflection(
    strategyId: string,
    reflectionId: string
  ): Promise<Reflection> {
    return api.get(
      `/strategies/${strategyId}/reflections/${reflectionId}`
    );
  },

  generateReflection(strategyId: string): Promise<Reflection> {
    return api.post(`/strategies/${strategyId}/reflections/generate`);
  },

  getPreTradeCheck(strategyId: string): Promise<PreTradeCheck> {
    return api.get(`/strategies/${strategyId}/pre-trade-check`);
  },
};
