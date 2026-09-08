import { api, apiUrl } from "./client";
import type {
  ReportJob,
  ReportListResponse,
  SectorReportRequest,
  StockReportRequest,
} from "@/lib/types/models";

export const reportsApi = {
  createStock(request: StockReportRequest): Promise<ReportJob> {
    return api.post("/reports/stock", request);
  },

  createSector(request: SectorReportRequest): Promise<ReportJob> {
    return api.post("/reports/sector", request);
  },

  list(): Promise<ReportListResponse> {
    return api.get("/reports");
  },

  get(reportId: string): Promise<ReportJob> {
    return api.get(`/reports/${reportId}`);
  },

  getDownloadUrl(reportId: string): string {
    return apiUrl(`/reports/${reportId}/download`);
  },
};
