import { api } from "./client";
import type { SystemConfig } from "@/lib/types/models";

export type NotificationTestResult = {
  channel: string;
  ok: boolean;
  message: string;
};

export const settingsApi = {
  get(): Promise<SystemConfig> {
    return api.get("/settings");
  },

  update(data: Partial<SystemConfig>): Promise<SystemConfig> {
    return api.put("/settings", data);
  },

  testEmail(): Promise<NotificationTestResult> {
    return api.post("/settings/test-email");
  },

  testTelegram(): Promise<NotificationTestResult> {
    return api.post("/settings/test-telegram");
  },

  testWechat(): Promise<NotificationTestResult> {
    return api.post("/settings/test-wechat");
  },

  testWhatsApp(): Promise<NotificationTestResult> {
    return api.post("/settings/test-whatsapp");
  },
};
