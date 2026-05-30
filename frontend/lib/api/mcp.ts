import { api } from "./client";
import type {
  MCPStatus,
  MCPServer,
  AddMCPServerRequest,
} from "@/lib/types/models";

export const mcpApi = {
  status(): Promise<MCPStatus> {
    return api.get("/mcp/status");
  },

  getTools(): Promise<
    { name: string; description: string; parameters: unknown }[]
  > {
    return api.get("/mcp/tools");
  },

  getServers(): Promise<{ servers: MCPServer[] }> {
    return api.get("/mcp/servers");
  },

  addServer(data: AddMCPServerRequest): Promise<MCPServer> {
    return api.post("/mcp/servers", data);
  },

  deleteServer(serverName: string): Promise<void> {
    return api.delete(`/mcp/servers/${serverName}`);
  },

  testServer(serverName: string): Promise<unknown> {
    return api.post(`/mcp/servers/${serverName}/test`);
  },
};
