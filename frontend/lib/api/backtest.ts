import { api, apiUrl } from "./client";
import type { BacktestJobResponse, BacktestRequest } from "@/lib/types/models";

export const backtestApi = {
  create(data: BacktestRequest): Promise<BacktestJobResponse> {
    return api.post("/agent/backtest", data);
  },

  get(backtestId: string): Promise<BacktestJobResponse> {
    return api.get(`/agent/backtest/${backtestId}`);
  },

  csvUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${backtestId}/trades.csv`);
  },
};
