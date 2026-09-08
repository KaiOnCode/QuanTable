import { api, apiUrl } from "./client";
import { encodeBacktestIdPathSegment } from "@/lib/backtest-id";
import type {
  BacktestJobAcceptedResponse,
  BacktestJobResponse,
  BacktestRequest,
} from "@/lib/types/models";

export const backtestApi = {
  create(data: BacktestRequest): Promise<BacktestJobAcceptedResponse> {
    return api.post("/agent/backtest", data);
  },

  get(backtestId: string): Promise<BacktestJobResponse> {
    return api.get(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}`);
  },

  replay(backtestId: string): Promise<BacktestJobAcceptedResponse> {
    return api.post(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/replay`);
  },

  tradesCsvUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/trades.csv`);
  },

  closedTradesCsvUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/closed-trades.csv`);
  },

  decisionsCsvUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/decisions.csv`);
  },

  decisionsJsonUrl(backtestId: string): string {
    return apiUrl(`/agent/backtest/${encodeBacktestIdPathSegment(backtestId)}/decisions.json`);
  },
};
