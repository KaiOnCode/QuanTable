"use client";

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

export default function SettingsPage() {
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

        {/* LLM Configuration */}
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
                  value="sk-****hidden****"
                  readOnly
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="base-url">Base URL</Label>
                <Input
                  id="base-url"
                  placeholder="https://api.openai.com/v1"
                  defaultValue="https://api.deepseek.com/v1"
                />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Quick-Think Model</Label>
                <Select defaultValue="deepseek-chat">
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
                <Select defaultValue="deepseek-chat">
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
            <Button variant="outline" size="sm">
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
            <CardDescription>
              Default agent configuration for new strategies.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
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
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div className="space-y-2">
                <Label>Default Debate Rounds</Label>
                <Select defaultValue="2">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1 Round</SelectItem>
                    <SelectItem value="2">2 Rounds</SelectItem>
                    <SelectItem value="3">3 Rounds</SelectItem>
                    <SelectItem value="4">4 Rounds</SelectItem>
                    <SelectItem value="5">5 Rounds</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div>
                  <Label className="text-sm">Cross-Review (Dual-LLM)</Label>
                  <p className="text-xs text-muted-foreground">
                    Second LLM reviews high-risk decisions
                  </p>
                </div>
                <Switch id="cross-review" defaultChecked={false} />
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
              <Input type="number" defaultValue={15} className="max-w-[200px]" />
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
            <CardDescription>
              Multi-channel notification configuration.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Email */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Email (SMTP)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Input placeholder="SMTP Host" defaultValue="smtp.gmail.com" />
                <Input placeholder="Port" defaultValue="587" />
                <Input placeholder="Recipients (comma-separated)" />
              </div>
              <Button variant="outline" size="sm">
                Test Email
              </Button>
            </div>
            <Separator />
            {/* Telegram */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Telegram
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" />
                <Input placeholder="Chat IDs (comma-separated)" />
              </div>
              <Button variant="outline" size="sm">
                Test Telegram
              </Button>
            </div>
            <Separator />
            {/* WeChat */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Enterprise WeChat
              </h4>
              <Input placeholder="Webhook URL" className="max-w-lg" />
            </div>
            <Separator />
            {/* Feishu */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Feishu (Lark)
              </h4>
              <Input placeholder="Webhook URL" className="max-w-lg" />
            </div>
            <Separator />
            {/* Discord */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Discord
              </h4>
              <Input placeholder="Webhook URL" className="max-w-lg" />
            </div>
            <Separator />
            {/* Slack */}
            <div className="space-y-3">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <MessageCircle className="h-4 w-4" />
                Slack
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Input placeholder="Bot Token" />
                <Input placeholder="Channel ID" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Memory & Learning */}
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
              <Switch id="memory-enabled" defaultChecked />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Memory Retention (days)</Label>
                <Input type="number" defaultValue={365} />
              </div>
              <div className="space-y-2">
                <Label>Weekly Reflection Day</Label>
                <Select defaultValue="sunday">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].map(
                      (d) => (
                        <SelectItem key={d} value={d}>
                          {d.charAt(0).toUpperCase() + d.slice(1)}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Reflection Time</Label>
                <Input type="time" defaultValue="18:00" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* MCP Integration */}
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
                <Button variant="outline" size="sm">
                  Start
                </Button>
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

        {/* Save */}
        <div className="flex justify-end">
          <Button>Save Settings</Button>
        </div>
      </div>
    </Shell>
  );
}
