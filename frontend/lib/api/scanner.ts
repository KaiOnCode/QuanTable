import { api } from "./client";
import type {
  ScannerRuleRequest,
  ScannerAgentRequest,
  ScannerBeliefRequest,
  ScanRun,
  ScanRunListResponse,
} from "@/lib/types/models";

export const scannerApi = {
  scanRule(data: ScannerRuleRequest): Promise<ScanRun> {
    return api.post("/scanner/rule", data);
  },

  scanAgent(data: ScannerAgentRequest): Promise<ScanRun> {
    return api.post("/agent/scanner", data);
  },

  scanBelief(data: ScannerBeliefRequest): Promise<ScanRun> {
    return api.post("/agent/scanner", data);
  },

  getRun(scanRunId: string): Promise<ScanRun> {
    return api.get(`/scanner/runs/${scanRunId}`);
  },

  listRuns(): Promise<ScanRunListResponse> {
    return api.get("/scanner/runs");
  },
};
