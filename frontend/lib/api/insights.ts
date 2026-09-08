import { api } from "./client";
import type {
  DailyBrief,
  InsightFeedback,
  InsightGenerationJob,
} from "@/lib/types/models";
import { encodeInsightGenerationIdPathSegment } from "@/lib/insight-generation-state";

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

  generate(generationId: string, hours: number): Promise<InsightGenerationJob> {
    return api.post(
      `/insights/generate?hours=${hours}&generation_id=${encodeInsightGenerationIdPathSegment(generationId)}`,
      undefined,
      { keepalive: true },
    );
  },

  getGeneration(generationId: string): Promise<InsightGenerationJob> {
    return api.get(
      `/insights/generate/${encodeInsightGenerationIdPathSegment(generationId)}`,
    );
  },

  feedback(
    insightId: string,
    data: InsightFeedback
  ): Promise<void> {
    return api.post(`/insights/${insightId}/feedback`, data);
  },
};
