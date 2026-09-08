import { api } from "./client";
import type {
  Approval,
  ApprovalActionRequest,
} from "@/lib/types/models";

export const approvalsApi = {
  list(params?: { status?: string }): Promise<{
    items: Approval[];
    total: number;
  }> {
    const sp = new URLSearchParams();
    if (params?.status) sp.set("status", params.status);
    return api.get(`/approvals?${sp.toString()}`);
  },

  get(approvalId: string): Promise<Approval> {
    return api.get(`/approvals/${approvalId}`);
  },

  approve(
    approvalId: string,
    data: ApprovalActionRequest
  ): Promise<void> {
    return api.post(`/approvals/${approvalId}/approve`, data);
  },

  reject(
    approvalId: string,
    data: ApprovalActionRequest
  ): Promise<void> {
    return api.post(`/approvals/${approvalId}/reject`, data);
  },

  modify(
    approvalId: string,
    data: ApprovalActionRequest
  ): Promise<void> {
    return api.post(`/approvals/${approvalId}/modify`, data);
  },
};
