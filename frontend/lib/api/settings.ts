import { api } from "./client";
import type { SystemConfig } from "@/lib/types/models";

export const settingsApi = {
  get(): Promise<SystemConfig> {
    return api.get("/settings");
  },

  update(data: Partial<SystemConfig>): Promise<SystemConfig> {
    return api.put("/settings", data);
  },

  testEmail(): Promise<void> {
    return api.post("/settings/test-email");
  },

  testTelegram(): Promise<void> {
    return api.post("/settings/test-telegram");
  },

  testWechat(): Promise<void> {
    return api.post("/settings/test-wechat");
  },

  testFeishu(): Promise<void> {
    return api.post("/settings/test-feishu");
  },
};
