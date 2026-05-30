import { api } from "./client";
import type { VarResponse, StressTestRequest } from "@/lib/types/models";

export const riskApi = {
  getVar(
    strategyId: string,
    confidence = 0.95
  ): Promise<VarResponse> {
    return api.get(
      `/risk/${strategyId}/var?confidence=${confidence}`
    );
  },

  stressTest(
    strategyId: string,
    data: StressTestRequest
  ): Promise<unknown> {
    return api.post(`/risk/${strategyId}/stress`, data);
  },

  getCorrelation(strategyId: string): Promise<unknown> {
    return api.get(`/risk/${strategyId}/correlation`);
  },

  getConcentration(strategyId: string): Promise<unknown> {
    return api.get(`/risk/${strategyId}/concentration`);
  },
};
