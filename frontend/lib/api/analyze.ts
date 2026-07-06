import { api } from "./client";
import type {
  AnalyzeRequest,
  AnalysisHistoryItem,
  AnalysisSessionSnapshot,
} from "@/lib/types/models";

export const analyzeApi = {
  analyze(data: AnalyzeRequest, handlers: Parameters<typeof api.sse>[2]) {
    return api.sse("/analyze", data, handlers);
  },

  getHistory(sessionId: string): Promise<AnalysisSessionSnapshot> {
    return api.get(`analyze/history/${sessionId}`);
  },

  listHistory(
    limit = 30
  ): Promise<{ items: AnalysisHistoryItem[]; total: number }> {
    return api.get(`analyze/history?limit=${limit}`);
  },

  batch(data: {
    tickers: string[];
    mode?: string;
  }): Promise<{ batch_id: string; results: unknown[] }> {
    return api.post("/analyze/batch", data);
  },
};
