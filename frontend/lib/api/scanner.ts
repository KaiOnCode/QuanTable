import { api } from "./client";
import type {
  ScannerRuleRequest,
  ScannerAgentRequest,
  ScannerBeliefRequest,
  ScanResult,
  ScannerQuery,
} from "@/lib/types/models";

export const scannerApi = {
  scanRule(data: ScannerRuleRequest): Promise<{
    results: ScanResult[];
    total_matches: number;
    scanned_at: string;
  }> {
    return api.post("/scanner/rule", data);
  },

  scanAgent(data: ScannerAgentRequest): Promise<{
    results: ScanResult[];
    total_matches: number;
  }> {
    return api.post("/scanner/agent", data);
  },

  scanBelief(data: ScannerBeliefRequest): Promise<{
    results: ScanResult[];
    total_matches: number;
  }> {
    return api.post("/scanner/belief", data);
  },

  getQueries(): Promise<ScannerQuery[]> {
    return api.get("/scanner/queries");
  },
};
