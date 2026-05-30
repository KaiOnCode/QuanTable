import { api } from "./client";
import type { BacktestRequest, BacktestResult } from "@/lib/types/models";

export const backtestApi = {
  create(data: BacktestRequest): Promise<{ backtest_id: string }> {
    return api.post("/backtest", data);
  },

  get(backtestId: string): Promise<BacktestResult> {
    return api.get(`/backtest/${backtestId}`);
  },
};
