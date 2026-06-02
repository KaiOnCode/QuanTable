"use client";

import { useState } from "react";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ActionBadge, DirectionBadge } from "@/components/shared/badges";
import {
  Zap,
  Send,
  Loader2,
  CheckCircle2,
  Clock,
  AlertCircle,
  TrendingUp,
  Shield,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import { createSSEStream } from "@/lib/api/client";
import type {
  SSEProgressEvent,
  SSEDebateEvent,
  SSEResultEvent,
} from "@/lib/types/models";

type AgentStatus = {
  name: string;
  status: "waiting" | "started" | "tool_call" | "tool_result" | "completed" | "error";
  duration_ms?: number;
  error?: string;
  stage: number;
};

const AGENTS = [
  { name: "company_overview", label: "Company Overview", stage: 0 },
  { name: "market_analyst", label: "Market Analyst", stage: 1 },
  { name: "news_analyst", label: "News Analyst", stage: 1 },
  { name: "fundamentals_analyst", label: "Fundamentals", stage: 1 },
  { name: "sentiment_analyst", label: "Sentiment", stage: 1 },
  { name: "technical_analyst", label: "Technical", stage: 1 },
  { name: "macro_analyst", label: "Macro", stage: 1 },
  { name: "bull_researcher", label: "Bull Researcher", stage: 2 },
  { name: "bear_researcher", label: "Bear Researcher", stage: 2 },
  { name: "aggressive_risk", label: "Aggressive Risk", stage: 3 },
  { name: "safe_risk", label: "Safe Risk", stage: 3 },
  { name: "neutral_risk", label: "Neutral Risk", stage: 3 },
  { name: "risk_manager", label: "Risk Manager", stage: 4 },
  { name: "PM_agent", label: "PM Decision", stage: 5 },
];

const STAGE_LABELS: Record<number, string> = {
  0: "Context",
  1: "Analysis",
  2: "Debate",
  3: "Risk Assessment",
  4: "Risk Synthesis",
  5: "Final Decision",
};

function parseReport(report: string): { direction?: string; timeframe?: string; confidence?: string; oneliner?: string; body: string } {
  const lines = report.split("\n");
  const result: any = {};
  let bodyStart = 0;
  for (let i = 0; i < Math.min(lines.length, 8); i++) {
    const line = lines[i].trim();
    const m = line.match(/^(方向|时间范围|置信度|一句话结论)[：:]\s*(.+)/);
    if (m) {
      const keyMap: Record<string, string> = { "方向": "direction", "时间范围": "timeframe", "置信度": "confidence", "一句话结论": "oneliner" };
      result[keyMap[m[1]] || m[1]] = m[2];
      bodyStart = i + 1;
    } else if (line === "" && bodyStart > 0) {
      bodyStart = i + 1;
      break;
    }
  }
  result.body = lines.slice(bodyStart).join("\n").trim();
  return result;
}

function ReportCard({ result }: { result: SSEResultEvent }) {
  const [showFull, setShowFull] = useState(false);
  const parsed = result.report ? parseReport(result.report) : null;
  const oneliner = parsed?.oneliner || "";
  const bodyText = parsed?.body || result.report || "";
  const confidence = result.confidence;
  const confidencePct = Math.round(confidence * 100);
  const barColor = confidencePct >= 70 ? "bg-green-500" : confidencePct >= 40 ? "bg-yellow-500" : "bg-red-500";
  const news = result.news_articles || [];

  return (
    <div className="space-y-4">
      {/* Decision Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Analysis Result</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Badge Row */}
          <div className="flex items-center gap-3 flex-wrap">
            <ActionBadge action={result.action} />
            <DirectionBadge direction={result.direction} />
            {result.timeframe && <Badge variant="outline">{result.timeframe}</Badge>}
          </div>

          {/* Confidence Bar */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Confidence</span>
              <span className="font-mono font-bold">{confidencePct}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${confidencePct}%` }} />
            </div>
          </div>

          {/* One-liner */}
          {oneliner && (
            <div className="p-3 rounded-lg bg-primary/5 border border-primary/10">
              <p className="text-sm font-medium">{oneliner}</p>
            </div>
          )}

          {/* Expandable full report */}
          {bodyText && bodyText !== oneliner && (
            <div>
              <Button variant="ghost" size="sm" onClick={() => setShowFull(!showFull)}>
                {showFull ? "Hide Full Report" : "Show Full Report"}
              </Button>
              {showFull && (
                <div className="mt-2 p-4 rounded-lg bg-muted/30 text-sm leading-relaxed max-h-96 overflow-y-auto prose prose-sm dark:prose-invert max-w-none">
                  <ReactMarkdown>{bodyText}</ReactMarkdown>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* News Sources */}
      {news.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">News Sources ({news.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {news.map((a, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className="text-muted-foreground shrink-0 mt-0.5">{i + 1}.</span>
                  <div className="min-w-0">
                    <a href={a.url} target="_blank" rel="noopener noreferrer"
                       className="text-primary hover:underline truncate block">
                      {a.title}
                    </a>
                    <div className="text-xs text-muted-foreground">
                      {a.source}{a.published_at ? ` · ${a.published_at.slice(0, 10)}` : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function QuickAskPage() {
  const [ticker, setTicker] = useState("");
  const [mode, setMode] = useState<"fast" | "standard" | "deep">("standard");
  const [analyzing, setAnalyzing] = useState(false);
  const [agentStatuses, setAgentStatuses] = useState<Map<string, AgentStatus>>(
    new Map()
  );
  const [result, setResult] = useState<SSEResultEvent | null>(null);
  const [debates, setDebates] = useState<SSEDebateEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [abortController, setAbortController] =
    useState<AbortController | null>(null);

  const handleAnalyze = () => {
    if (!ticker.trim() || analyzing) return;

    setAnalyzing(true);
    setResult(null);
    setDebates([]);
    setError(null);

    // Immediately mark PM as "started" so user sees feedback
    const initialStatuses = new Map<string, AgentStatus>();
    AGENTS.forEach((a) => {
      initialStatuses.set(a.name, {
        name: a.name,
        status: "waiting",
        stage: a.stage,
      });
    });
    setAgentStatuses(initialStatuses);

    const controller = createSSEStream(
      "/analyze",
      {
        ticker: ticker.toUpperCase(),
        mode,
        active_agents: AGENTS.map((a) => a.name),
        enable_debate: mode === "deep",
        debate_rounds: mode === "deep" ? 2 : 0,
      },
      {
        onProgress: (event: SSEProgressEvent) => {
          setAgentStatuses((prev) => {
            const next = new Map(prev);
            next.set(event.agent, {
              name: event.agent,
              status: event.status,
              duration_ms: event.duration_ms,
              stage:
                AGENTS.find((a) => a.name === event.agent)?.stage || 0,
            });
            return next;
          });
        },
        onDebate: (event: SSEDebateEvent) => {
          setDebates((prev) => [...prev, event]);
        },
        onResult: (event: SSEResultEvent) => {
          setResult(event);
          setAnalyzing(false);
        },
        onError: (event) => {
          setAnalyzing(false);
          setError(`[${event.agent}] ${event.error}`);
        },
        onComplete: () => {
          setAnalyzing(false);
        },
      }
    );
    setAbortController(controller);
  };

  const handleCancel = () => {
    abortController?.abort();
    setAnalyzing(false);
  };

  const getStageAgents = (stage: number) => {
    const statuses = AGENTS.filter((a) => a.stage === stage).map((a) => ({
      label: a.label,
      ...agentStatuses.get(a.name),
    }));
    return statuses;
  };

  return (
    <Shell>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        {/* Input */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Quick Ask
            </CardTitle>
            <CardDescription>
              Enter a ticker symbol to get AI-powered investment analysis
              with multi-agent debate.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <div className="flex-1">
                <Input
                  placeholder="Enter ticker symbol (e.g. AAPL, TSLA)"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  onKeyDown={(e) =>
                    e.key === "Enter" && handleAnalyze()
                  }
                  disabled={analyzing}
                  className="font-mono text-lg h-12"
                />
              </div>
              <Select
                value={mode}
                onValueChange={(v) =>
                  setMode(v as "fast" | "standard" | "deep")
                }
                disabled={analyzing}
              >
                <SelectTrigger className="w-32 h-12">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="fast">Fast</SelectItem>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="deep">Deep</SelectItem>
                </SelectContent>
              </Select>
              {analyzing ? (
                <Button variant="destructive" onClick={handleCancel}>
                  Cancel
                </Button>
              ) : (
                <Button
                  onClick={handleAnalyze}
                  disabled={!ticker.trim()}
                  className="h-12 px-6"
                  title={!ticker.trim() ? "Enter a ticker symbol first" : "Start analysis"}
                >
                  <Send className="mr-2 h-4 w-4" />
                  {!ticker.trim() ? "Enter Ticker" : "Analyze"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Analysis Progress */}
        {analyzing && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Analysis Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[0, 1, 2, 3, 4, 5].map((stage) => {
                  const agents = getStageAgents(stage);
                  const allDone = agents.every(
                    (a) => a?.status === "completed"
                  );
                  const hasError = agents.some(
                    (a) => a?.status === "error"
                  );
                  const inProgress = agents.some(
                    (a) =>
                      a?.status === "started" ||
                      a?.status === "tool_call"
                  );

                  return (
                    <div key={stage}>
                      <div className="flex items-center gap-2 mb-2">
                        {allDone ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500" />
                        ) : hasError ? (
                          <AlertCircle className="h-4 w-4 text-red-500" />
                        ) : inProgress ? (
                          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                        ) : (
                          <Clock className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="text-sm font-medium">
                          {STAGE_LABELS[stage]}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 ml-6">
                        {agents.map((agent) => (
                          <div
                            key={agent?.name}
                            className="flex items-center gap-2 p-2 rounded bg-muted/50 text-xs"
                          >
                            {agent?.status === "completed" ? (
                              <CheckCircle2 className="h-3 w-3 text-green-500 shrink-0" />
                            ) : agent?.status === "error" ? (
                              <AlertCircle className="h-3 w-3 text-red-500 shrink-0" />
                            ) : agent?.status === "started" ||
                              agent?.status === "tool_call" ? (
                              <Loader2 className="h-3 w-3 animate-spin text-blue-500 shrink-0" />
                            ) : (
                              <Clock className="h-3 w-3 text-muted-foreground shrink-0" />
                            )}
                            <span className="truncate">{agent?.label}</span>
                            {agent?.duration_ms && (
                              <span className="text-muted-foreground ml-auto">
                                {(agent.duration_ms / 1000).toFixed(1)}s
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error */}
        {error && (
          <Card className="border-destructive">
            <CardHeader>
              <CardTitle className="text-destructive text-base">
                Connection Error
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm">{error}</p>
              <p className="text-xs text-muted-foreground mt-2">
                Make sure the backend server is running at{" "}
                <code className="bg-muted px-1 rounded">
                  {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api"}
                </code>
              </p>
            </CardContent>
          </Card>
        )}

        {/* Result */}
        {result && (
          <div className="space-y-4">
            <ReportCard result={result} />

            {/* Debate Records */}
            {debates.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Agent Debate History
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-80">
                    <div className="space-y-4">
                      {debates.map((debate, i) => (
                        <div key={i}>
                          <Badge variant="outline" className="mb-2">
                            {debate.type === "investment"
                              ? `Debate Round ${debate.round}`
                              : `Risk Round ${debate.round}`}
                          </Badge>
                          {debate.type === "investment" ? (
                            <div className="grid grid-cols-2 gap-3">
                              <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                                <div className="flex items-center gap-2 mb-1">
                                  <TrendingUp className="h-4 w-4 text-green-500" />
                                  <span className="text-sm font-medium">
                                    Bull Case
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {debate.bull_claim}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                <div className="flex items-center gap-2 mb-1">
                                  <TrendingUp className="h-4 w-4 text-red-500 rotate-180" />
                                  <span className="text-sm font-medium">
                                    Bear Case
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {debate.bear_claim}
                                </p>
                              </div>
                            </div>
                          ) : (
                            <div className="grid grid-cols-3 gap-3">
                              <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                                <div className="flex items-center gap-2 mb-1">
                                  <Shield className="h-4 w-4 text-red-500" />
                                  <span className="text-sm font-medium">
                                    Aggressive
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {debate.aggressive}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
                                <div className="flex items-center gap-2 mb-1">
                                  <Shield className="h-4 w-4 text-blue-500" />
                                  <span className="text-sm font-medium">
                                    Neutral
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {debate.neutral}
                                </p>
                              </div>
                              <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                                <div className="flex items-center gap-2 mb-1">
                                  <Shield className="h-4 w-4 text-green-500" />
                                  <span className="text-sm font-medium">
                                    Safe
                                  </span>
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  {debate.safe}
                                </p>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Empty state when nothing has been done */}
        {!result && !analyzing && !error && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setMode("fast")}
            >
              <CardHeader>
                <CardTitle className="text-sm">Fast Mode</CardTitle>
                <CardDescription>
                  Market + News only. Quick overview in seconds.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card
              className="cursor-pointer hover:border-primary/50 transition-colors border-primary/50"
              onClick={() => setMode("standard")}
            >
              <CardHeader>
                <CardTitle className="text-sm">Standard Mode</CardTitle>
                <CardDescription>
                  All 6 analysts. Full report with multi-angle analysis.
                </CardDescription>
              </CardHeader>
            </Card>
            <Card
              className="cursor-pointer hover:border-primary/50 transition-colors"
              onClick={() => setMode("deep")}
            >
              <CardHeader>
                <CardTitle className="text-sm">Deep Mode</CardTitle>
                <CardDescription>
                  Full debate (Bull vs Bear + Risk 3-way). Most thorough.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        )}
      </div>
    </Shell>
  );
}
