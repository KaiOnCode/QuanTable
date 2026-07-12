import { api, apiUrl } from "./client";
import { encodeBacktestIdPathSegment } from "@/lib/backtest-id";
import type { BacktestJobResponse, BacktestRequest } from "@/lib/types/models";

export const backtestApi = {
  create(data: BacktestRequest): Promise<BacktestJobResponse> {
    return api.post("/agent/backtest", data);
  },

  get(backtestId: string): Promise<BacktestJobResponse> {
    return api.get(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}`);
  },

  csvUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/trades.csv`);
  },
};
