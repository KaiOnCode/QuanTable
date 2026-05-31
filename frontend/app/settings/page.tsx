"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { settingsApi } from "@/lib/api/settings";
import { api } from "@/lib/api/client";
import type { SystemConfig, HealthResponse } from "@/lib/types/models";
import {
  Settings,
  Brain,
  Bell,
  Database,
  Mail,
  MessageCircle,
  Bot,
  Server,
  Cpu,
  Loader2,
  CheckCircle2,
} from "lucide-react";

export default function SettingsPage() {
  const { data: config, isLoading } = useQuery<SystemConfig>({
    queryKey: ["settings"],
    queryFn: () => settingsApi.get(),
  });

  const { data: dsStatus } = useQuery({
    queryKey: ["data-sources-status"],
    queryFn: () => api.get<Record<string, unknown>>("/data-sources/status"),
  });

  const saveMutation = useMutation({
    mutationFn: (data: Partial<SystemConfig>) => settingsApi.update(data),
    onSuccess: () => alert("Settings saved"),
    onError: (e: Error) => alert("Save failed: " + e.message),
  });

  const handleSave = () => {
    if (!config) return;
    saveMutation.mutate({});
  };

  if (isLoading) {
    return (
      <Shell>
        <div className="p-6 flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </Shell>
    );
  }

  const dataSources = [
    {
      name: "Yahoo Finance",
      status: dsStatus?.providers
        ? (dsStatus.providers as Record<string, { status: string }>).yahoo_finance
            ?.status ?? "unknown"
        : "unknown",
    },
    {
      name: "Google News",
      status: dsStatus?.providers
        ? (dsStatus.providers as Record<string, { status: string }>).google_news?.status ??
          "unknown"
        : "unknown",
    },
    {
      name: "AkShare",
      status: dsStatus?.providers
        ? (dsStatus.providers as Record<string, { status: string }>).akshare?.status ??
          "unknown"
        : "unknown",
    },
    {
      name: "Finnhub",
      status: dsStatus?.providers
        ? (dsStatus.providers as Record<string, { status: string }>).finnhub?.status ??
          "unknown"
        : "unknown",
    },
  ];

  return (
    <Shell>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h2>
          <p className="text-sm text-muted-foreground">
            Configure your Agentic-Quant system — LLM, agents, data, notifications.
          </p>
        </div>

        {/* LLM Configuration */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Cpu className="h-4 w-4" />
              LLM Configuration
            </CardTitle>
            <CardDescription>API keys and model settings.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>API Key</Label>
                <Input
                  type="password"
                  value={config?.llm_api_key ?? "sk-****"}
                  readOnly
                />
              </div>
              <div className="space-y-2">
                <Label>Base URL</Label>
                <Input value={config?.llm_base_url ?? ""} readOnly />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Quick-Think Model</Label>
                <Input value={config?.llm_model ?? ""} readOnly />
              </div>
              <div className="space-y-2">
                <Label>Deep-Think Model</Label>
                <Input value={config?.deep_think_model ?? ""} readOnly />
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  const h = await api.get<HealthResponse>("/health");
                  alert(`Connected — server uptime: ${h.uptime_seconds}s, version: ${h.version}`);
                } catch {
                  alert("Connection failed");
                }
              }}
            >
              Test Connection
            </Button>
          </CardContent>
        </Card>

        {/* Agent Defaults */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Agent Defaults
            </CardTitle>
            <CardDescription>Default agent configuration for new strategies.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                "Market Analyst", "News Analyst", "Fundamentals", "Sentiment",
                "Technical", "Macro", "Company Overview",
                "Bull Researcher", "Bear Researcher",
                "Aggressive Risk", "Safe Risk", "Neutral Risk",
                "Risk Manager", "PM Decision",
              ].map((label) => (
                <div
                  key={label}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <Label className="text-sm cursor-pointer">{label}</Label>
                  <Switch defaultChecked />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div className="space-y-2">
                <Label>Default Debate Rounds</Label>
                <Select defaultValue="2">
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <SelectItem key={n} value={String(n)}>{n} Round{n > 1 ? "s" : ""}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div>
                  <Label className="text-sm">Cross-Review (Dual-LLM)</Label>
                  <p className="text-xs text-muted-foreground">Second LLM reviews high-risk decisions</p>
                </div>
                <Switch defaultChecked={false} />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Data Sources */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-4 w-4" />
              Data Sources
            </CardTitle>
            <CardDescription>External data provider status.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {dataSources.map((ds) => (
                <div key={ds.name} className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        ds.status === "connected" ? "bg-green-500" : ds.status === "disabled" ? "bg-red-500" : "bg-yellow-500"
                      }`}
                    />
                    <span className="text-sm font-medium">{ds.name}</span>
                  </div>
                  <Badge variant="outline">{ds.status}</Badge>
                </div>
              ))}
            </div>
            <div className="mt-4 space-y-2">
              <Label>Data Cache TTL (minutes)</Label>
              <Input
                type="number"
                defaultValue={config?.data_cache_ttl_minutes ?? 15}
                className="max-w-[200px]"
              />
            </div>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-4 w-4" />
              Notifications
            </CardTitle>
            <CardDescription>Multi-channel notification configuration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" /> Email (SMTP)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Input placeholder="SMTP Host" defaultValue={config?.email_smtp_host ?? ""} />
                <Input placeholder="Port" defaultValue={String(config?.email_smtp_port ?? 587)} />
                <Input placeholder="Recipients" />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => settingsApi.testEmail().then(() => alert("Test email sent"))}
              >
                Test Email
              </Button>
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" /> Telegram
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" />
                <Input placeholder="Chat IDs" />
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => settingsApi.testTelegram().then(() => alert("Test telegram sent"))}
              >
                Test Telegram
              </Button>
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Enterprise WeChat</h4>
              <Input placeholder="Webhook URL" className="max-w-lg" />
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium">Feishu (Lark)</h4>
              <Input placeholder="Webhook URL" className="max-w-lg" />
            </div>
          </CardContent>
        </Card>

        {/* Memory & Learning */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="h-4 w-4" />
              Memory &amp; Learning
            </CardTitle>
            <CardDescription>OWM memory system configuration.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-sm">Memory Enabled</Label>
                <p className="text-xs text-muted-foreground">Record and recall trading decisions</p>
              </div>
              <Switch defaultChecked={config?.memory_enabled ?? true} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Retention (days)</Label>
                <Input type="number" defaultValue={config?.memory_retention_days ?? 365} />
              </div>
              <div className="space-y-2">
                <Label>Reflection Day</Label>
                <Select defaultValue={config?.weekly_reflection_day ?? "sunday"}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"].map((d) => (
                      <SelectItem key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Reflection Time</Label>
                <Input type="time" defaultValue={config?.weekly_reflection_time ?? "18:00"} />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* MCP */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="h-4 w-4" />
              MCP Integration
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-sm">MCP Server</Label>
                <p className="text-xs text-muted-foreground">Expose tools to external AI agents</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">Stopped</Badge>
                <Button variant="outline" size="sm">Start</Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Save */}
        <div className="flex justify-end">
          <Button
            onClick={handleSave}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : saveMutation.isSuccess ? (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            ) : null}
            Save Settings
          </Button>
        </div>
      </div>
    </Shell>
  );
}
