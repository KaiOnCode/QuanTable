import { api } from "./client";
import type { MonitorTask, MonitoringReport, CreateMonitorRequest, UpdateMonitorRequest } from "@/lib/types/models";

export const monitorApi = {
  list(params?: { status?: string }): Promise<{ monitors: MonitorTask[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.status) sp.set("status", params.status);
    return api.get(`/monitors?${sp.toString()}`);
  },

  create(data: CreateMonitorRequest): Promise<MonitorTask> {
    return api.post("/monitors", data);
  },

  get(monitorId: string): Promise<MonitorTask> {
    return api.get(`/monitors/${monitorId}`);
  },

  update(monitorId: string, data: UpdateMonitorRequest): Promise<MonitorTask> {
    return api.put(`/monitors/${monitorId}`, data);
  },

  delete(monitorId: string): Promise<void> {
    return api.delete(`/monitors/${monitorId}`);
  },

  run(monitorId: string): Promise<MonitoringReport & { report_id: string }> {
    return api.post(`/monitors/${monitorId}/run`);
  },

  listReports(monitorId: string, limit?: number): Promise<{ reports: MonitoringReport[]; total: number }> {
    return api.get(`/monitors/${monitorId}/reports?limit=${limit ?? 20}`);
  },
};
