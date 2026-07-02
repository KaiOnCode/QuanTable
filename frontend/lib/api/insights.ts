import { api } from "./client";
import type { DailyBrief, InsightFeedback } from "@/lib/types/models";

export const insightsApi = {
  list(params?: {
    from?: string;
    to?: string;
    type?: string;
  }): Promise<{ insights: DailyBrief[] }> {
    const sp = new URLSearchParams();
    if (params?.from) sp.set("from", params.from);
    if (params?.to) sp.set("to", params.to);
    if (params?.type) sp.set("type", params.type);
    return api.get(`/insights?${sp.toString()}`);
  },

  get(insightId: string): Promise<DailyBrief> {
    return api.get(`/insights/${insightId}`);
  },

  feedback(
    insightId: string,
    data: InsightFeedback
  ): Promise<void> {
    return api.post(`/insights/${insightId}/feedback`, data);
  },
};
