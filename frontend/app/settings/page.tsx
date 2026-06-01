"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

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
import { settingsApi, type NotificationTestResult } from "@/lib/api/settings";
import type { SystemConfig } from "@/lib/types/models";
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
} from "lucide-react";

const DEFAULT_SETTINGS: SystemConfig = {
  llm_api_key: "",
  llm_base_url: "https://api.deepseek.com/v1",
  llm_model: "deepseek-chat",
  deep_think_model: "deepseek-chat",
  email_smtp_host: "",
  email_smtp_port: 587,
  email_username: "",
  email_password: "",
  email_sender: "",
  email_use_tls: true,
  email_recipients: [],
  telegram_bot_token: "",
  telegram_chat_ids: [],
  wechat_webhook_url: "",
  feishu_webhook_url: "",
  discord_webhook_url: "",
  slack_bot_token: "",
  slack_channel_id: "",
  whatsapp_access_token: "",
  whatsapp_phone_number_id: "",
  whatsapp_recipients: [],
  social_webhook_url: "",
  data_cache_ttl_minutes: 15,
  news_fetch_interval_minutes: 30,
  max_concurrent_analyses: 3,
  memory_enabled: true,
  memory_retention_days: 365,
  weekly_reflection_day: "sunday",
  weekly_reflection_time: "18:00",
  mcp_external_servers: {},
};

const toCsv = (items: string[]) => items.join(", ");
const fromCsv = (value: string) =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

export default function SettingsPage() {
  const [config, setConfig] = useState<SystemConfig>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingChannel, setTestingChannel] = useState<string | null>(null);

  useEffect(() => {
    settingsApi
      .get()
      .then((data) => setConfig({ ...DEFAULT_SETTINGS, ...data }))
      .catch((error: unknown) => {
        toast.error("Failed to load settings", {
          description: error instanceof Error ? error.message : String(error),
        });
      })
      .finally(() => setLoading(false));
  }, []);

  const updateField = <K extends keyof SystemConfig>(
    key: K,
    value: SystemConfig[K]
  ) => {
    setConfig((current) => ({ ...current, [key]: value }));
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const updated = await settingsApi.update(config);
      setConfig({ ...DEFAULT_SETTINGS, ...updated });
      toast.success("Settings saved");
    } catch (error: unknown) {
      toast.error("Failed to save settings", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async (
    channel: string,
    run: () => Promise<NotificationTestResult>
  ) => {
    setTestingChannel(channel);
    try {
      await settingsApi.update(config);
      const result = await run();
      if (result.ok) {
        toast.success(`${channel} test sent`, { description: result.message });
      } else {
        toast.error(`${channel} test failed`, { description: result.message });
      }
    } catch (error: unknown) {
      toast.error(`${channel} test failed`, {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setTestingChannel(null);
    }
  };

  return (
    <Shell>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h2>
          <p className="text-sm text-muted-foreground">
            Configure your Agentic-Quant system — LLM, agents, notifications, and more.
          </p>
        </div>

        {loading ? (
          <Card>
            <CardContent className="p-8 text-sm text-muted-foreground">
              Loading settings...
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Cpu className="h-4 w-4" />
              LLM Configuration
            </CardTitle>
            <CardDescription>
              API keys and model settings for the AI backend.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="api-key">API Key</Label>
                <Input
                  id="api-key"
                  type="password"
                  placeholder="sk-..."
                  value={config.llm_api_key}
                  onChange={(event) => updateField("llm_api_key", event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="base-url">Base URL</Label>
                <Input
                  id="base-url"
                  placeholder="https://api.openai.com/v1"
                  value={config.llm_base_url}
                  onChange={(event) => updateField("llm_base_url", event.target.value)}
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Quick-Think Model</Label>
                <Select
                  value={config.llm_model}
                  onValueChange={(value) => {
                    if (value) updateField("llm_model", value);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="deepseek-chat">deepseek-chat</SelectItem>
                    <SelectItem value="gpt-4o-mini">gpt-4o-mini</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Deep-Think Model</Label>
                <Select
                  value={config.deep_think_model}
                  onValueChange={(value) => {
                    if (value) updateField("deep_think_model", value);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="deepseek-chat">deepseek-chat</SelectItem>
                    <SelectItem value="claude-sonnet-4-6">claude-sonnet-4-6</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Agent Defaults
            </CardTitle>
            <CardDescription>
              Default agent configuration for new strategies.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[
                { id: "market", label: "Market Analyst" },
                { id: "news", label: "News Analyst" },
                { id: "fundamentals", label: "Fundamentals" },
                { id: "sentiment", label: "Sentiment" },
                { id: "technical", label: "Technical" },
                { id: "macro", label: "Macro" },
                { id: "company_overview", label: "Company Overview" },
                { id: "bull_researcher", label: "Bull Researcher" },
                { id: "bear_researcher", label: "Bear Researcher" },
                { id: "aggressive_risk", label: "Aggressive Risk" },
                { id: "safe_risk", label: "Safe Risk" },
                { id: "neutral_risk", label: "Neutral Risk" },
                { id: "risk_manager", label: "Risk Manager" },
                { id: "pm", label: "PM Decision" },
              ].map((agent) => (
                <div
                  key={agent.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <Label htmlFor={`agent-${agent.id}`} className="text-sm cursor-pointer">
                    {agent.label}
                  </Label>
                  <Switch id={`agent-${agent.id}`} defaultChecked />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Database className="h-4 w-4" />
              Data Sources
            </CardTitle>
            <CardDescription>
              Status and configuration of external data providers.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {[
                { name: "Yahoo Finance", status: "connected", latency: "120ms" },
                { name: "Google News", status: "connected", latency: "350ms" },
                { name: "AkShare", status: "connected", latency: "890ms" },
                { name: "Finnhub", status: "degraded", latency: "2.1s" },
              ].map((ds) => (
                <div
                  key={ds.name}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        ds.status === "connected"
                          ? "bg-green-500"
                          : ds.status === "degraded"
                            ? "bg-yellow-500"
                            : "bg-red-500"
                      }`}
                    />
                    <span className="text-sm font-medium">{ds.name}</span>
                  </div>
                  <div className="flex items-center gap-3 text-sm text-muted-foreground">
                    <Badge
                      variant="outline"
                      className={
                        ds.status === "connected"
                          ? "text-green-500 border-green-500/20"
                          : "text-yellow-500 border-yellow-500/20"
                      }
                    >
                      {ds.status}
                    </Badge>
                    <span>{ds.latency}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 space-y-2">
              <Label>Data Cache TTL (minutes)</Label>
              <Input
                type="number"
                value={config.data_cache_ttl_minutes}
                onChange={(event) =>
                  updateField("data_cache_ttl_minutes", Number(event.target.value))
                }
                className="max-w-[200px]"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-4 w-4" />
              Notifications
            </CardTitle>
            <CardDescription>
              Configure social media and messaging reminders for trading alerts.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Email (SMTP)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Input placeholder="SMTP Host" value={config.email_smtp_host} onChange={(event) => updateField("email_smtp_host", event.target.value)} />
                <Input placeholder="Port" type="number" value={config.email_smtp_port} onChange={(event) => updateField("email_smtp_port", Number(event.target.value))} />
                <Input placeholder="Sender" value={config.email_sender} onChange={(event) => updateField("email_sender", event.target.value)} />
                <Input placeholder="Username" value={config.email_username} onChange={(event) => updateField("email_username", event.target.value)} />
                <Input placeholder="Password" type="password" value={config.email_password} onChange={(event) => updateField("email_password", event.target.value)} />
                <Input placeholder="Recipients (comma-separated)" value={toCsv(config.email_recipients)} onChange={(event) => updateField("email_recipients", fromCsv(event.target.value))} />
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={config.email_use_tls} onCheckedChange={(checked) => updateField("email_use_tls", Boolean(checked))} />
                <Label className="text-sm">Use TLS</Label>
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "Email"} onClick={() => handleTest("Email", settingsApi.testEmail)}>
                Test Email
              </Button>
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Telegram
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" type="password" value={config.telegram_bot_token} onChange={(event) => updateField("telegram_bot_token", event.target.value)} />
                <Input placeholder="Chat IDs (comma-separated)" value={toCsv(config.telegram_chat_ids)} onChange={(event) => updateField("telegram_chat_ids", fromCsv(event.target.value))} />
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "Telegram"} onClick={() => handleTest("Telegram", settingsApi.testTelegram)}>
                Test Telegram
              </Button>
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                WhatsApp Cloud API
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Input placeholder="Access Token" type="password" value={config.whatsapp_access_token} onChange={(event) => updateField("whatsapp_access_token", event.target.value)} />
                <Input placeholder="Phone Number ID" value={config.whatsapp_phone_number_id} onChange={(event) => updateField("whatsapp_phone_number_id", event.target.value)} />
                <Input placeholder="Recipients, e.g. 852..." value={toCsv(config.whatsapp_recipients)} onChange={(event) => updateField("whatsapp_recipients", fromCsv(event.target.value))} />
              </div>
              <p className="text-xs text-muted-foreground">
                Uses Meta WhatsApp Cloud API text messages for social media reminders.
              </p>
              <Button variant="outline" size="sm" disabled={testingChannel === "WhatsApp"} onClick={() => handleTest("WhatsApp", settingsApi.testWhatsApp)}>
                Test WhatsApp
              </Button>
            </div>
            <Separator />
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <WebhookInput label="Enterprise WeChat" value={config.wechat_webhook_url} onChange={(value) => updateField("wechat_webhook_url", value)} onTest={() => handleTest("WeChat", settingsApi.testWechat)} disabled={testingChannel === "WeChat"} />
              <WebhookInput label="Feishu (Lark)" value={config.feishu_webhook_url} onChange={(value) => updateField("feishu_webhook_url", value)} onTest={() => handleTest("Feishu", settingsApi.testFeishu)} disabled={testingChannel === "Feishu"} />
              <WebhookInput label="Discord" value={config.discord_webhook_url} onChange={(value) => updateField("discord_webhook_url", value)} onTest={() => handleTest("Discord", settingsApi.testDiscord)} disabled={testingChannel === "Discord"} />
              <WebhookInput label="Generic Webhook" value={config.social_webhook_url} onChange={(value) => updateField("social_webhook_url", value)} />
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Slack
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" type="password" value={config.slack_bot_token} onChange={(event) => updateField("slack_bot_token", event.target.value)} />
                <Input placeholder="Channel ID" value={config.slack_channel_id} onChange={(event) => updateField("slack_channel_id", event.target.value)} />
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "Slack"} onClick={() => handleTest("Slack", settingsApi.testSlack)}>
                Test Slack
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Brain className="h-4 w-4" />
              Memory & Learning
            </CardTitle>
            <CardDescription>
              Configure the OWM memory system and learning behavior.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-sm">Memory Enabled</Label>
                <p className="text-xs text-muted-foreground">
                  Record and recall trading decisions
                </p>
              </div>
              <Switch checked={config.memory_enabled} onCheckedChange={(checked) => updateField("memory_enabled", Boolean(checked))} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Memory Retention (days)</Label>
                <Input type="number" value={config.memory_retention_days} onChange={(event) => updateField("memory_retention_days", Number(event.target.value))} />
              </div>
              <div className="space-y-2">
                <Label>Weekly Reflection Day</Label>
                <Select
                  value={config.weekly_reflection_day}
                  onValueChange={(value) => {
                    if (value) updateField("weekly_reflection_day", value);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[
                      "monday",
                      "tuesday",
                      "wednesday",
                      "thursday",
                      "friday",
                      "saturday",
                      "sunday",
                    ].map((day) => (
                      <SelectItem key={day} value={day}>
                        {day.charAt(0).toUpperCase() + day.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Reflection Time</Label>
                <Input type="time" value={config.weekly_reflection_time} onChange={(event) => updateField("weekly_reflection_time", event.target.value)} />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Server className="h-4 w-4" />
              MCP Integration
            </CardTitle>
            <CardDescription>
              Model Context Protocol — expose tools and load external servers.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-sm">MCP Server</Label>
                <p className="text-xs text-muted-foreground">
                  Expose Agentic-Quant tools to external AI agents (stdio / SSE / HTTP)
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">Stopped</Badge>
                <Button variant="outline" size="sm">Start</Button>
              </div>
            </div>
            <Separator />
            <div>
              <h4 className="text-sm font-medium mb-3">External MCP Servers</h4>
              <div className="p-8">
                <EmptyState
                  title="No external servers"
                  description="Add external MCP servers to extend agent capabilities with third-party tools."
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button disabled={saving} onClick={saveSettings}>
            {saving ? "Saving..." : "Save Settings"}
          </Button>
        </div>
      </div>
    </Shell>
  );
}

function WebhookInput({
  label,
  value,
  onChange,
  onTest,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onTest?: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium flex items-center gap-2">
        <MessageCircle className="h-4 w-4" />
        {label}
      </h4>
      <Input placeholder="Webhook URL" value={value} onChange={(event) => onChange(event.target.value)} />
      {onTest ? (
        <Button variant="outline" size="sm" disabled={disabled} onClick={onTest}>
          Test {label}
        </Button>
      ) : null}
    </div>
  );
}
