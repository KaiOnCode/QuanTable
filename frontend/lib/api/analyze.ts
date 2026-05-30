import { api } from "./client";
import type { AnalyzeRequest } from "@/lib/types/models";

export const analyzeApi = {
  analyze(data: AnalyzeRequest): ReturnType<typeof api.sse> {
    return api.sse("/analyze", data, {});
  },

  batch(data: {
    tickers: string[];
    mode?: string;
  }): Promise<{ batch_id: string; results: unknown[] }> {
    return api.post("/analyze/batch", data);
  },
};
