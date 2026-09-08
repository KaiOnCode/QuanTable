"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/shared/empty-state";
import { monitorApi } from "@/lib/api/monitor";
import { formatDateTime } from "@/lib/utils";
import type { MonitorTask, MonitoringReport, MonitorMode } from "@/lib/types/models";
import { Eye, Plus, Loader2, Play, Trash2, Clock, ChevronRight, Pencil, Check, X, ExternalLink, Pause, Power } from "lucide-react";
import { Markdown } from "@/components/markdown";

// Human-readable cron descriptions
function cronLabel(expr?: string): string {
  if (!expr) return "Manual only";
  const map: Record<string, string> = {
    "0 * * * *": "Every hour",
    "0 9 * * *": "Daily 9 AM",
    "0 9 * * 1-5": "Weekdays 9 AM",
    "0 9 * * 1": "Weekly Mon 9 AM",
    "0 18 * * *": "Daily 6 PM",
  };
  return map[expr] || expr;
}

export default function MonitorPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string>("");
  const [showCreate, setShowCreate] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["monitors"],
    queryFn: () => monitorApi.list(),
    refetchInterval: (query) => {
      const monitors = query.state.data?.monitors ?? [];
      return monitors.some((m) => m.run_status === "running") ? 2000 : false;
    },
  });
  const monitors = data?.monitors ?? [];
  const selected = monitors.find((m) => m.id === selectedId);

  // Set initial selection
  if (!selectedId && monitors.length > 0 && !isLoading) {
    setSelectedId(monitors[0].id);
  }

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Eye className="h-5 w-5" /> Monitor
            </h2>
            <p className="text-sm text-muted-foreground">
              Continuous monitoring tasks — track keywords, tickers, or domains.
            </p>
          </div>
          <Button onClick={() => setShowCreate(!showCreate)}>
            <Plus className="mr-2 h-4 w-4" />
            {showCreate ? "Cancel" : "New Monitor"}
          </Button>
        </div>

        {/* Create Form */}
        {showCreate && (
          <CreateMonitorForm
            onCreated={(m) => {
              queryClient.invalidateQueries({ queryKey: ["monitors"] });
              setSelectedId(m.id);
              setShowCreate(false);
            }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        {isLoading ? (
          <Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>
        ) : monitors.length === 0 ? (
          <Card>
            <CardContent className="pt-8">
              <EmptyState title="No monitors" description="Create a monitoring task to track keywords, tickers, or investment themes."
                action={<Button onClick={() => setShowCreate(true)}><Plus className="mr-2 h-4 w-4" /> New Monitor</Button>}
              />
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Task List */}
            <Card className="lg:col-span-1">
              <CardHeader><CardTitle className="text-base">Tasks</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                {monitors.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setSelectedId(m.id)}
                    className={`w-full text-left p-3 rounded-lg transition-colors ${
                      selectedId === m.id ? "bg-primary/10 border border-primary/20" : "hover:bg-muted/50 border border-transparent"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm truncate">{m.name}</span>
                      <div className="flex items-center gap-1">
                        {m.run_status === "running" && (
                          <Badge variant="secondary" className="text-xs">
                            Running
                          </Badge>
                        )}
                        {m.run_status === "failed" && (
                          <Badge variant="destructive" className="text-xs">
                            Failed
                          </Badge>
                        )}
                        <Badge variant="outline" className="text-xs">{m.mode}</Badge>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {cronLabel(m.cron_expression)}
                      {m.last_run_at && <> · last: {formatDateTime(m.last_run_at)}</>}
                    </div>
                  </button>
                ))}
              </CardContent>
            </Card>

            {/* Detail + Reports */}
            <Card className="lg:col-span-2">
              {selected ? (
                <MonitorDetail monitor={selected} />
              ) : (
                <CardContent className="pt-8">
                  <EmptyState title="Select a monitor" description="Choose a task from the list to view details and reports." />
                </CardContent>
              )}
            </Card>
          </div>
        )}
      </div>
    </Shell>
  );
}

function MonitorDetail({ monitor }: { monitor: MonitorTask }) {
  const queryClient = useQueryClient();
  const [viewReport, setViewReport] = useState<MonitoringReport | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameVal, setRenameVal] = useState("");

  const { data: reportsData, isLoading: reportsLoading } = useQuery({
    queryKey: ["monitors", monitor.id, "reports"],
    queryFn: () => monitorApi.listReports(monitor.id, 10),
    enabled: !!monitor.id,
    refetchInterval: monitor.run_status === "running" ? 2000 : false,
  });
  const reports = reportsData?.reports ?? [];

  const runMutation = useMutation({
    mutationFn: () => monitorApi.run(monitor.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      queryClient.invalidateQueries({ queryKey: ["monitors", monitor.id, "reports"] });
    },
    onError: (err: Error) => {
      alert("Run failed: " + err.message);
    },
  });
  const isRunning = monitor.run_status === "running" || runMutation.isPending;

  const deleteMutation = useMutation({
    mutationFn: () => monitorApi.delete(monitor.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      setViewReport(null);
    },
  });

  const renameMutation = useMutation({
    mutationFn: (name: string) => monitorApi.update(monitor.id, { name } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      setRenaming(false);
    },
  });

  const toggleStatus = useMutation({
    mutationFn: () => monitorApi.update(monitor.id, { status: monitor.status === "active" ? "paused" : "active" } as any),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["monitors"] }),
  });

  const targets = monitor.targets ?? {};
  const keywords = targets.keywords ?? [];
  const tickers = targets.tickers ?? [];

  if (viewReport) {
    return (
      <CardContent className="pt-4 space-y-4">
        <Button variant="ghost" size="sm" onClick={() => setViewReport(null)}>
          <ChevronRight className="mr-1 h-4 w-4 rotate-180" /> Back
        </Button>
        <div>
          <h3 className="font-semibold text-lg">Report</h3>
          <p className="text-xs text-muted-foreground">
            {formatDateTime(viewReport.generated_at)}
            {(viewReport.raw_data as any)?.elapsed_ms != null && (
              <> · took {((viewReport.raw_data as any).elapsed_ms / 1000).toFixed(1)}s</>
            )}
          </p>
        </div>
        <p className="text-sm">{viewReport.summary}</p>
        {viewReport.key_findings?.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium">Key Findings</h4>
            <ul className="list-disc list-inside text-sm text-muted-foreground">
              {viewReport.key_findings.map((f: string, i: number) => <li key={i}>{f}</li>)}
            </ul>
          </div>
        )}
        {/* Full report content */}
        {viewReport.content_text && (
          <div className="text-sm leading-relaxed bg-muted/20 p-3 rounded max-h-96 overflow-y-auto prose prose-sm dark:prose-invert max-w-none">
            <Markdown>{viewReport.content_text}</Markdown>
          </div>
        )}

        {/* Collected news (traceability) — from fresh run OR historical raw_data */}
        {(() => {
          const news = ((viewReport as any).collected_news as any[]) ||
                       ((viewReport.raw_data as any)?.collected_news as any[]);
          if (!news || news.length === 0) return null;
          return (
            <div className="space-y-1">
              <h4 className="text-sm font-medium">News Sources ({news.length})</h4>
              <div className="text-xs space-y-1 max-h-40 overflow-y-auto">
                {news.map((a: any, i: number) => (
                  <div key={i} className="flex items-start gap-1">
                    <span className="text-muted-foreground shrink-0">{i+1}.</span>
                    {a.url ? (
                      <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline truncate">
                        {a.title || a.url}
                      </a>
                    ) : (
                      <span className="truncate">{a.title || "(no link)"}</span>
                    )}
                    {a.source && <span className="text-muted-foreground shrink-0">({a.source})</span>}
                  </div>
                ))}
              </div>
            </div>
          );
        })()}
        <div className="flex items-center gap-2">
          <Badge variant="outline">Sentiment: {viewReport.sentiment}</Badge>
          {viewReport.related_tickers?.map((t: string) => (
            <Badge key={t} variant="secondary" className="font-mono text-xs">${t}</Badge>
          ))}
        </div>
      </CardContent>
    );
  }

  return (
    <>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex-1 min-w-0">
            {renaming ? (
              <div className="flex items-center gap-1">
                <Input value={renameVal} onChange={(e) => setRenameVal(e.target.value)}
                  className="h-7 w-48 text-sm" autoFocus
                  onKeyDown={(e) => { if (e.key==="Enter") renameMutation.mutate(renameVal); if (e.key==="Escape") setRenaming(false); }} />
                <Button size="icon-sm" variant="ghost" onClick={() => renameMutation.mutate(renameVal)} disabled={renameMutation.isPending}><Check className="h-3.5 w-3.5" /></Button>
                <Button size="icon-sm" variant="ghost" onClick={() => setRenaming(false)}><X className="h-3.5 w-3.5" /></Button>
              </div>
            ) : (
              <CardTitle className="text-base flex items-center gap-1">
                <span className="truncate">{monitor.name}</span>
                <Button size="icon-sm" variant="ghost" onClick={() => { setRenaming(true); setRenameVal(monitor.name); }}>
                  <Pencil className="h-3 w-3 text-muted-foreground" />
                </Button>
              </CardTitle>
            )}
            <CardDescription>
              {monitor.mode} · {cronLabel(monitor.cron_expression)}
            </CardDescription>
            {monitor.run_status === "running" && (
              <Badge variant="secondary" className="mt-2 gap-1">
                <Loader2 className="h-3 w-3 animate-spin" />
                Running
              </Badge>
            )}
            {monitor.run_status === "failed" && monitor.last_run_error && (
              <p className="mt-2 text-xs text-destructive">
                {monitor.last_run_error}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => toggleStatus.mutate()} disabled={toggleStatus.isPending}
              title={monitor.status === "active" ? "Pause scheduling" : "Resume scheduling"}>
              {monitor.status === "active" ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>
            <Button size="sm" onClick={() => runMutation.mutate()} disabled={isRunning}>
              {isRunning ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />}
              {isRunning ? "Running..." : "Run Now"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => { if (confirm("Delete?")) deleteMutation.mutate(); }}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Config summary */}
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span className="text-muted-foreground">Mode:</span> <Badge variant="outline" className="text-xs">{monitor.mode}</Badge></div>
          <div><span className="text-muted-foreground">Schedule:</span> <span className="text-xs">{cronLabel(monitor.cron_expression)}</span></div>
          {monitor.description && (
            <div className="col-span-2">
              <span className="text-muted-foreground">Description:</span>{" "}
              <span className="text-xs">{monitor.description}</span>
            </div>
          )}
          {keywords.length > 0 && (
            <div className="col-span-2">
              <span className="text-muted-foreground">Keywords:</span>{" "}
              {keywords.map((k: string) => <Badge key={k} variant="secondary" className="text-xs mr-1">{k}</Badge>)}
            </div>
          )}
          {tickers.length > 0 && (
            <div className="col-span-2">
              <span className="text-muted-foreground">Tickers:</span>{" "}
              {tickers.map((t: string) => <Badge key={t} variant="secondary" className="font-mono text-xs mr-1">${t}</Badge>)}
            </div>
          )}
          {(monitor.expanded_keywords?.length ?? 0) > 0 && (
            <div className="col-span-2">
              <span className="text-muted-foreground">LLM Keywords:</span>{" "}
              {monitor.expanded_keywords!.map((k: string) => <Badge key={k} variant="outline" className="text-xs mr-1">{k}</Badge>)}
            </div>
          )}
          {(monitor.expanded_tickers?.length ?? 0) > 0 && (
            <div className="col-span-2">
              <span className="text-muted-foreground">LLM Tickers:</span>{" "}
              {monitor.expanded_tickers!.map((t: string) => <Badge key={t} variant="outline" className="font-mono text-xs mr-1">${t}</Badge>)}
            </div>
          )}
        </div>

        <Separator />

        {/* Reports */}
        <div>
          <h4 className="text-sm font-medium mb-2">Recent Reports ({reports.length})</h4>
          {reportsLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : reports.length === 0 ? (
            <p className="text-xs text-muted-foreground">No reports yet. Click "Run" to generate one.</p>
          ) : (
            <div className="space-y-2">
              {reports.slice(0, 5).map((r: MonitoringReport) => (
                <button
                  key={r.id}
                  onClick={() => setViewReport(r)}
                  className="w-full text-left p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <p className="text-sm truncate">{r.summary}</p>
                  <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                    <span>{formatDateTime(r.generated_at)}</span>
                    <Badge variant="outline" className="text-xs">{r.sentiment}</Badge>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </>
  );
}

function CreateMonitorForm({ onCreated, onCancel }: { onCreated: (m: MonitorTask) => void; onCancel: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<MonitorMode>("keyword");
  const [keywordInput, setKeywordInput] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [tickerInput, setTickerInput] = useState("");
  const [tickers, setTickers] = useState<string[]>([]);
  const [cronExpression, setCronExpression] = useState("0 9 * * 1-5");
  const [cronPreset, setCronPreset] = useState("weekdays");
  const [expandKeywords, setExpandKeywords] = useState(false);

  // Auto-add current input value on submit (so user doesn't lose typed text)
  const finalKeywords = mode === "keyword" && keywordInput.trim()
    ? [...keywords, keywordInput.trim()]
    : keywords;
  const finalTickers = mode === "ticker" && tickerInput.trim()
    ? [...tickers, tickerInput.trim()]
    : tickers;
  const hasTargets = mode === "keyword" ? finalKeywords.length > 0 : finalTickers.length > 0;

  const [expandedResult, setExpandedResult] = useState<{keywords: string[]; tickers: string[]} | null>(null);
  const [createdMonitor, setCreatedMonitor] = useState<any>(null);

  const createMutation = useMutation({
    mutationFn: () => {
      const targets: Record<string, string[]> = {};
      if (mode === "keyword") targets.keywords = finalKeywords;
      if (mode === "ticker") targets.tickers = finalTickers;

      return monitorApi.create({
        name: name || "Untitled", description, mode,
        targets, sources: ["news", "prices"],
        schedule: { frequency: "daily" },
        agent: { enabled: true },
        output: { format: "summary", language: "zh" },
        cron_expression: cronExpression,
        expand_keywords: expandKeywords,
      } as any);
    },
    onSuccess: (result: any) => {
      if (result.expanded_keywords?.length > 0 || result.expanded_tickers?.length > 0) {
        setCreatedMonitor(result);
        setExpandedResult({ keywords: result.expanded_keywords || [], tickers: result.expanded_tickers || [] });
      } else {
        onCreated(result);
      }
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Create Monitor Task</CardTitle>
        <CardDescription>Define what to track and how often.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Name *</Label>
            <Input placeholder="AI Chip Watch" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Mode</Label>
            <Select value={mode} onValueChange={(v) => v && setMode(v as MonitorMode)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="keyword">Keyword Search</SelectItem>
                <SelectItem value="ticker">Ticker Monitor</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <Label>Description</Label>
          <Textarea placeholder="What are you monitoring?" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
        </div>

        {mode === "keyword" ? (
          <div className="space-y-2">
            <Label>Keywords</Label>
            <div className="flex items-center gap-2">
              <Input placeholder="GPU" value={keywordInput} onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (keywordInput.trim()) { setKeywords([...keywords, keywordInput.trim()]); setKeywordInput(""); } } }} />
              <Button type="button" variant="outline" size="sm" onClick={() => { if (keywordInput.trim()) { setKeywords([...keywords, keywordInput.trim()]); setKeywordInput(""); } }}>
                Add</Button>
            </div>
            <div className="flex gap-1 flex-wrap">{keywords.map((k) => <Badge key={k} variant="secondary" className="text-xs">{k}</Badge>)}</div>
          </div>
        ) : (
          <div className="space-y-2">
            <Label>Tickers</Label>
            <div className="flex items-center gap-2">
              <Input placeholder="AAPL" value={tickerInput} onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (tickerInput.trim()) { setTickers([...tickers, tickerInput.trim()]); setTickerInput(""); } } }} />
              <Button type="button" variant="outline" size="sm" onClick={() => { if (tickerInput.trim()) { setTickers([...tickers, tickerInput.trim()]); setTickerInput(""); } }}>
                Add</Button>
            </div>
            <div className="flex gap-1 flex-wrap">{tickers.map((t) => <Badge key={t} variant="secondary" className="font-mono text-xs">${t}</Badge>)}</div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label>Schedule</Label>
            <Select value={cronPreset} onValueChange={(v) => {
              if (!v) return;
              setCronPreset(v);
              const presets: Record<string, string> = {
                "hourly": "0 * * * *",
                "daily9": "0 9 * * *",
                "weekdays": "0 9 * * 1-5",
                "weekly": "0 9 * * 1",
                "daily18": "0 18 * * *",
              };
              setCronExpression(presets[v] || "0 9 * * 1-5");
            }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="hourly">Every Hour</SelectItem>
                <SelectItem value="daily9">Daily 9 AM</SelectItem>
                <SelectItem value="weekdays">Weekdays 9 AM</SelectItem>
                <SelectItem value="weekly">Weekly Monday 9 AM</SelectItem>
                <SelectItem value="daily18">Daily 6 PM</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Cron (custom)</Label>
            <Input placeholder="0 9 * * 1-5" value={cronExpression} onChange={(e) => { setCronExpression(e.target.value); setCronPreset(""); }} />
          </div>
        </div>

        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div>
            <Label className="text-sm">Auto-expand Keywords</Label>
            <p className="text-xs text-muted-foreground">LLM suggests keywords & tickers on creation</p>
          </div>
          <Button variant={expandKeywords ? "default" : "outline"} size="sm" onClick={() => setExpandKeywords(!expandKeywords)}>
            {expandKeywords ? "Enabled" : "Disabled"}
          </Button>
        </div>

        {expandedResult && (
          <div className="p-3 rounded-lg bg-primary/5 border border-primary/10 space-y-2">
            <p className="text-sm font-medium">LLM Suggested Keywords & Tickers</p>
            {expandedResult.keywords.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {expandedResult.keywords.map((k) => <Badge key={k} className="text-xs">{k}</Badge>)}
              </div>
            )}
            {expandedResult.tickers.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {expandedResult.tickers.map((t) => <Badge key={t} variant="secondary" className="font-mono text-xs">{t}</Badge>)}
              </div>
            )}
            <div className="flex gap-2">
              <Button size="sm" onClick={() => {
                setKeywords([...keywords, ...expandedResult.keywords.filter((k: string) => !keywords.includes(k))]);
                setTickers([...tickers, ...expandedResult.tickers.filter((t: string) => !tickers.includes(t))]);
                setExpandedResult(null);
                onCreated(createdMonitor);
              }}>Accept & Save</Button>
              <Button size="sm" variant="outline" onClick={() => { setExpandedResult(null); onCreated(createdMonitor); }}>Skip</Button>
            </div>
          </div>
        )}

        {!expandedResult && (
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            <Button
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !name.trim() || !hasTargets}
              title={!hasTargets ? "Add at least one keyword or ticker first" : ""}
            >
              {createMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Create
            </Button>
            {!hasTargets && (
              <p className="text-xs text-destructive mt-1">
                Add at least one keyword or ticker (type and press Enter or click Add).
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
