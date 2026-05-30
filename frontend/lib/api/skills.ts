import { api } from "./client";
import type { Skill, CreateSkillRequest } from "@/lib/types/models";

export const skillsApi = {
  list(params?: {
    category?: string;
    active?: boolean;
  }): Promise<{ skills: Skill[]; total: number }> {
    const sp = new URLSearchParams();
    if (params?.category) sp.set("category", params.category);
    if (params?.active !== undefined)
      sp.set("active", String(params.active));
    return api.get(`/skills?${sp.toString()}`);
  },

  get(skillId: string): Promise<Skill> {
    return api.get(`/skills/${skillId}`);
  },

  create(data: CreateSkillRequest): Promise<Skill> {
    return api.post("/skills", data);
  },

  update(
    skillId: string,
    data: Partial<CreateSkillRequest>
  ): Promise<Skill> {
    return api.put(`/skills/${skillId}`, data);
  },

  delete(skillId: string): Promise<void> {
    return api.delete(`/skills/${skillId}`);
  },

  toggle(skillId: string, isActive: boolean): Promise<void> {
    return api.post(`/skills/${skillId}/toggle`, { is_active: isActive });
  },
};
