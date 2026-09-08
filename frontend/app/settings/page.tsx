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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { settingsApi, type NotificationTestResult } from "@/lib/api/settings";
import { api } from "@/lib/api/client";
import {
  DEEP_THINK_MODEL_OPTIONS,
  DEFAULT_DEEP_THINK_MODEL,
  DEFAULT_QUICK_THINK_MODEL,
  QUICK_THINK_MODEL_OPTIONS,
} from "@/lib/llm-defaults";
import type {
  HealthResponse,
  NotificationChannelName,
  SystemConfig,
} from "@/lib/types/models";
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
  ExternalLink,
} from "lucide-react";

const DEFAULT_SETTINGS: SystemConfig = {
  llm_api_key: "",
  llm_base_url: "https://api.deepseek.com/v1",
  llm_model: DEFAULT_QUICK_THINK_MODEL,
  deep_think_model: DEFAULT_DEEP_THINK_MODEL,
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
  whatsapp_access_token: "",
  whatsapp_phone_number_id: "",
  whatsapp_recipients: [],
  data_cache_ttl_minutes: 15,
  news_fetch_interval_minutes: 30,
  max_concurrent_analyses: 3,
  memory_enabled: true,
  memory_retention_days: 365,
  weekly_reflection_day: "sunday",
  weekly_reflection_time: "18:00",
  mcp_external_servers: {},
  llm_api_key_configured: false,
  llm_api_key_source: "missing",
  llm_api_key_length: 0,
  notification_status: {
    email: { configured: false, missing_fields: ["email_smtp_host", "email_sender", "email_recipients"] },
    telegram: { configured: false, missing_fields: ["telegram_bot_token", "telegram_chat_ids"] },
    wechat: { configured: false, missing_fields: ["wechat_webhook_url"] },
    whatsapp: { configured: false, missing_fields: ["whatsapp_access_token", "whatsapp_phone_number_id", "whatsapp_recipients"] },
  },
};

type ProviderStatus = { name: string; status: string };
type TestState = { kind: "success" | "failure"; message: string };

const NOTIFICATION_FIELD_CHANNELS: Partial<
  Record<keyof SystemConfig, NotificationChannelName>
> = {
  email_smtp_host: "email",
  email_smtp_port: "email",
  email_username: "email",
  email_password: "email",
  email_sender: "email",
  email_use_tls: "email",
  email_recipients: "email",
  telegram_bot_token: "telegram",
  telegram_chat_ids: "telegram",
  wechat_webhook_url: "wechat",
  whatsapp_access_token: "whatsapp",
  whatsapp_phone_number_id: "whatsapp",
  whatsapp_recipients: "whatsapp",
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
  const [saved, setSaved] = useState(false);
  const [testingChannel, setTestingChannel] = useState<string | null>(null);
  const [testStates, setTestStates] = useState<Partial<Record<NotificationChannelName, TestState>>>({});
  const [dataSources, setDataSources] = useState<ProviderStatus[]>([]);

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

    api
      .get<Record<string, unknown>>("/data-sources/status")
      .then((status) => {
        const providers = status.providers as
          | Record<string, { status?: string }>
          | undefined;
        setDataSources([
          { name: "Yahoo Finance", status: providers?.yahoo_finance?.status ?? "unknown" },
          { name: "Google News", status: providers?.google_news?.status ?? "unknown" },
          { name: "AkShare", status: providers?.akshare?.status ?? "unknown" },
          { name: "Finnhub", status: providers?.finnhub?.status ?? "unknown" },
        ]);
      })
      .catch(() => {
        setDataSources([
          { name: "Yahoo Finance", status: "unknown" },
          { name: "Google News", status: "unknown" },
          { name: "AkShare", status: "unknown" },
          { name: "Finnhub", status: "unknown" },
        ]);
      });
  }, []);

  const updateField = <K extends keyof SystemConfig>(
    key: K,
    value: SystemConfig[K]
  ) => {
    setSaved(false);
    setConfig((current) => ({ ...current, [key]: value }));
    const channel = NOTIFICATION_FIELD_CHANNELS[key];
    if (channel) {
      setTestStates((current) => {
        const next = { ...current };
        delete next[channel];
        return next;
      });
    }
  };

  const saveSettings = async () => {
    setSaving(true);
    try {
      const updated = await settingsApi.update(config);
      setConfig({ ...DEFAULT_SETTINGS, ...updated });
      setSaved(true);
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
    channel: NotificationChannelName,
    label: string,
    run: () => Promise<NotificationTestResult>
  ) => {
    setTestingChannel(label);
    setTestStates((current) => ({ ...current, [channel]: undefined }));
    try {
      const updated = await settingsApi.update(config);
      setConfig({ ...DEFAULT_SETTINGS, ...updated });
      const result = await run();
      setTestStates((current) => ({
        ...current,
        [channel]: { kind: result.ok ? "success" : "failure", message: result.message },
      }));
      if (result.ok) {
        toast.success(`${label} test sent`, { description: result.message });
      } else {
        toast.error(`${label} test failed`, { description: result.message });
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      setTestStates((current) => ({ ...current, [channel]: { kind: "failure", message } }));
      toast.error(`${label} test failed`, {
        description: message,
      });
    } finally {
      setTestingChannel(null);
    }
  };

  if (loading) {
    return (
      <Shell>
        <div className="p-6 flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="p-6 max-w-4xl mx-auto space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h2>
          <p className="text-sm text-muted-foreground">
            Configure Agentic-Quant system settings, notifications, memory, and integrations.
          </p>
        </div>

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
                <div className="flex items-center justify-between gap-2">
                  <Label>API Key</Label>
                  <div className="flex items-center gap-2">
                    <Badge variant={config.llm_api_key_configured ? "secondary" : "destructive"}>
                      {config.llm_api_key_source === "properties.env"
                        ? "properties.env"
                        : config.llm_api_key_source === "settings"
                          ? "settings"
                          : "missing"}
                    </Badge>
                    {config.llm_api_key_configured && (
                      <span className="text-xs text-muted-foreground">
                        {config.llm_api_key_length ?? config.llm_api_key.length} chars
                      </span>
                    )}
                  </div>
                </div>
                <Input
                  type="password"
                  value={config.llm_api_key}
                  onChange={(event) => updateField("llm_api_key", event.target.value)}
                  placeholder="sk-..."
                />
              </div>
              <div className="space-y-2">
                <Label>Base URL</Label>
                <Input
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
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {QUICK_THINK_MODEL_OPTIONS.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
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
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {DEEP_THINK_MODEL_OPTIONS.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                try {
                  const health = await api.get<HealthResponse>("/health");
                  toast.success("Connection healthy", {
                    description: `Uptime ${health.uptime_seconds}s, version ${health.version}`,
                  });
                } catch (error: unknown) {
                  toast.error("Connection failed", {
                    description: error instanceof Error ? error.message : String(error),
                  });
                }
              }}
            >
              Test Connection
            </Button>
          </CardContent>
        </Card>

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
                "Technical", "Macro", "Company Overview", "Bull Researcher",
                "Bear Researcher", "Aggressive Risk", "Safe Risk", "Neutral Risk",
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
                    {[1, 2, 3, 4, 5].map((rounds) => (
                      <SelectItem key={rounds} value={String(rounds)}>
                        {rounds} Round{rounds > 1 ? "s" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div>
                  <Label className="text-sm">Cross-Review</Label>
                  <p className="text-xs text-muted-foreground">Second model reviews high-risk decisions</p>
                </div>
                <Switch defaultChecked={false} />
              </div>
            </div>
          </CardContent>
        </Card>

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
              {dataSources.map((source) => (
                <div
                  key={source.name}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        source.status === "connected"
                          ? "bg-green-500"
                          : source.status === "disabled"
                            ? "bg-red-500"
                            : "bg-yellow-500"
                      }`}
                    />
                    <span className="text-sm font-medium">{source.name}</span>
                  </div>
                  <Badge variant="outline">{source.status}</Badge>
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
            <CardDescription>Configure channels used by analysis, approval, and watchlist events.</CardDescription>
            <a
              className="inline-flex items-center gap-1 text-xs text-primary underline underline-offset-4"
              href="https://github.com/DrEden33773/COMP7705-Agent-Quant/blob/dev/docs/notifications.md"
              target="_blank"
              rel="noreferrer"
            >
              Full notification setup guide <ExternalLink className="h-3 w-3" />
            </a>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" /> Email (SMTP)
              </h4>
              <NotificationStatus status={config.notification_status.email} testState={testStates.email} pending={testingChannel === "Email"} />
              <p className="text-xs text-muted-foreground">Required: SMTP host, sender, and recipients. Authentication and app-password requirements vary by provider.</p>
              <a className="text-xs text-primary underline" href="https://www.rfc-editor.org/info/rfc5321/" target="_blank" rel="noreferrer">SMTP reference</a>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                <Input placeholder="SMTP Host" value={config.email_smtp_host} onChange={(event) => updateField("email_smtp_host", event.target.value)} />
                <Input placeholder="Port" type="number" value={config.email_smtp_port} onChange={(event) => updateField("email_smtp_port", Number(event.target.value))} />
                <Input placeholder="Sender" value={config.email_sender} onChange={(event) => updateField("email_sender", event.target.value)} />
                <Input placeholder="Username" value={config.email_username} onChange={(event) => updateField("email_username", event.target.value)} />
                <Input placeholder="Password" type="password" value={config.email_password} onChange={(event) => updateField("email_password", event.target.value)} />
                <Input placeholder="Recipients, comma-separated" value={toCsv(config.email_recipients)} onChange={(event) => updateField("email_recipients", fromCsv(event.target.value))} />
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={config.email_use_tls} onCheckedChange={(checked) => updateField("email_use_tls", Boolean(checked))} />
                <Label className="text-sm">Use TLS</Label>
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "Email"} onClick={() => handleTest("email", "Email", settingsApi.testEmail)}>
                Test Email
              </Button>
            </div>
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" /> Telegram
              </h4>
              <NotificationStatus status={config.notification_status.telegram} testState={testStates.telegram} pending={testingChannel === "Telegram"} />
              <p className="text-xs text-muted-foreground">Create a bot with BotFather, start a chat or add it to a group, then enter the token and chat IDs.</p>
              <a className="text-xs text-primary underline" href="https://core.telegram.org/bots/tutorial" target="_blank" rel="noreferrer">Telegram setup guide</a>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" type="password" value={config.telegram_bot_token} onChange={(event) => updateField("telegram_bot_token", event.target.value)} />
                <Input placeholder="Chat IDs, comma-separated" value={toCsv(config.telegram_chat_ids)} onChange={(event) => updateField("telegram_chat_ids", fromCsv(event.target.value))} />
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "Telegram"} onClick={() => handleTest("telegram", "Telegram", settingsApi.testTelegram)}>
                Test Telegram
              </Button>
            </div>
            <Separator />
            <WebhookInput
              label="Enterprise WeChat"
              status={config.notification_status.wechat}
              testState={testStates.wechat}
              value={config.wechat_webhook_url}
              onChange={(value) => updateField("wechat_webhook_url", value)}
              onTest={() => handleTest("wechat", "WeChat", settingsApi.testWechat)}
              disabled={testingChannel === "WeChat"}
            />
            <Separator />
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" /> WhatsApp Cloud API
              </h4>
              <NotificationStatus status={config.notification_status.whatsapp} testState={testStates.whatsapp} pending={testingChannel === "WhatsApp"} />
              <p className="text-xs text-muted-foreground">Required: Cloud API token, phone number ID, and E.164 recipients. Templates/session rules still apply.</p>
              <a className="text-xs text-primary underline" href="https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages" target="_blank" rel="noreferrer">WhatsApp Cloud API guide</a>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                <Input placeholder="Access Token" type="password" value={config.whatsapp_access_token} onChange={(event) => updateField("whatsapp_access_token", event.target.value)} />
                <Input placeholder="Phone Number ID" value={config.whatsapp_phone_number_id} onChange={(event) => updateField("whatsapp_phone_number_id", event.target.value)} />
                <Input placeholder="Recipients, comma-separated" value={toCsv(config.whatsapp_recipients)} onChange={(event) => updateField("whatsapp_recipients", fromCsv(event.target.value))} />
              </div>
              <Button variant="outline" size="sm" disabled={testingChannel === "WhatsApp"} onClick={() => handleTest("whatsapp", "WhatsApp", settingsApi.testWhatsApp)}>
                Test WhatsApp
              </Button>
            </div>
          </CardContent>
        </Card>

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
              <Switch checked={config.memory_enabled} onCheckedChange={(checked) => updateField("memory_enabled", Boolean(checked))} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Retention (days)</Label>
                <Input type="number" value={config.memory_retention_days} onChange={(event) => updateField("memory_retention_days", Number(event.target.value))} />
              </div>
              <div className="space-y-2">
                <Label>Reflection Day</Label>
                <Select
                  value={config.weekly_reflection_day}
                  onValueChange={(value) => {
                    if (value) updateField("weekly_reflection_day", value);
                  }}
                >
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"].map((day) => (
                      <SelectItem key={day} value={day}>{day.charAt(0).toUpperCase() + day.slice(1)}</SelectItem>
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
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
              <div>
                <Label className="text-sm">MCP Server</Label>
                <p className="text-xs text-muted-foreground">
                  Server management is not available in this build.
                </p>
              </div>
              <Badge variant="outline">Unavailable</Badge>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end">
          <Button onClick={saveSettings} disabled={saving}>
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : saved ? (
              <CheckCircle2 className="mr-2 h-4 w-4" />
            ) : null}
            Save Settings
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
  status,
  testState,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onTest: () => void;
  disabled?: boolean;
  status: SystemConfig["notification_status"]["wechat"];
  testState?: TestState;
}) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium flex items-center gap-2">
        <MessageCircle className="h-4 w-4" />
        {label}
      </h4>
      <NotificationStatus status={status} testState={testState} pending={Boolean(disabled)} />
      <p className="text-xs text-muted-foreground">Add an Enterprise WeChat group bot and paste its webhook URL.</p>
      <a className="text-xs text-primary underline" href="https://developer.work.weixin.qq.com/document/path/91770" target="_blank" rel="noreferrer">Enterprise WeChat bot guide</a>
      <Input placeholder="Webhook URL" value={value} onChange={(event) => onChange(event.target.value)} />
      <Button variant="outline" size="sm" disabled={disabled} onClick={onTest}>
        Test {label}
      </Button>
    </div>
  );
}

function NotificationStatus({
  status,
  testState,
  pending,
}: {
  status: SystemConfig["notification_status"][NotificationChannelName];
  testState?: TestState;
  pending: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" aria-live="polite">
      <Badge variant={status.configured ? "secondary" : "destructive"}>
        {status.configured ? "Configured" : "Incomplete"}
      </Badge>
      {!status.configured && <span className="text-muted-foreground">Missing: {status.missing_fields.join(", ")}</span>}
      {pending && <span>Test pending…</span>}
      {!pending && testState && (
        <span className={testState.kind === "success" ? "text-green-700" : "text-destructive"}>
          Test {testState.kind}: {testState.message}
        </span>
      )}
    </div>
  );
}
