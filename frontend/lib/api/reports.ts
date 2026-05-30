import { api } from "./client";
import type { Report } from "@/lib/types/models";

const BASE_API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export const reportsApi = {
  createStock(ticker: string, sections?: string[]): Promise<Report> {
    return api.post("/reports/stock", { ticker, sections });
  },

  createSector(description: string): Promise<Report> {
    return api.post("/reports/sector", { description });
  },

  list(): Promise<Report[]> {
    return api.get("/reports");
  },

  getDownloadUrl(reportId: string): string {
    return `${BASE_API}/reports/${reportId}/download`;
  },
};
