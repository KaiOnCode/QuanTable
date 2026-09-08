import { api } from "./client";
import type {
  RiskOverview,
  StressResult,
  StressTestRequest,
} from "@/lib/types/models";

export const riskApi = {
  overview(strategyId: string, lookbackDays = 252): Promise<RiskOverview> {
    return api.get(`/risk/${strategyId}/overview?lookback_days=${lookbackDays}`);
  },

  stress(
    strategyId: string,
    data: StressTestRequest
  ): Promise<StressResult> {
    return api.post(`/risk/${strategyId}/stress`, data);
  },
};
