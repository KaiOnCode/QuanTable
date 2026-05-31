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
import type { MonitorTask, MonitoringReport, MonitorMode } from "@/lib/types/models";
import { Eye, Plus, Loader2, Play, Trash2, Clock, ChevronRight } from "lucide-react";

const FREQUENCY_OPTIONS = [
  { value: "hourly", label: "Every Hour" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
];

export default function MonitorPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string>("");
  const [showCreate, setShowCreate] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["monitors"],
    queryFn: () => monitorApi.list(),
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
                      <Badge variant="outline" className="text-xs">{m.mode}</Badge>
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {m.schedule?.frequency ?? "daily"}
                      {m.last_run_at && <> · last: {m.last_run_at.slice(5, 16)}</>}
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

  const { data: reportsData, isLoading: reportsLoading } = useQuery({
    queryKey: ["monitors", monitor.id, "reports"],
    queryFn: () => monitorApi.listReports(monitor.id, 10),
    enabled: !!monitor.id,
  });
  const reports = reportsData?.reports ?? [];

  const runMutation = useMutation({
    mutationFn: () => monitorApi.run(monitor.id),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      queryClient.invalidateQueries({ queryKey: ["monitors", monitor.id, "reports"] });
      setViewReport(report);  // Show result immediately from response
    },
    onError: (err: Error) => {
      alert("Run failed: " + err.message);
    },
  });
  const isRunning = runMutation.isPending;

  const deleteMutation = useMutation({
    mutationFn: () => monitorApi.delete(monitor.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["monitors"] });
      setViewReport(null);
    },
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
            {viewReport.generated_at}
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
        {/* Search trace: show user what was actually searched */}
        {((viewReport.raw_data as any)?.search_details as any[])?.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium">Search Trace</h4>
            <div className="text-xs text-muted-foreground space-y-0.5 bg-muted/30 p-2 rounded">
              {((viewReport.raw_data as any).search_details as string[]).map((d, i) => (
                <div key={i}>{d}</div>
              ))}
            </div>
          </div>
        )}
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
          <div>
            <CardTitle className="text-base">{monitor.name}</CardTitle>
            <CardDescription>
              {monitor.mode} · {monitor.schedule?.frequency ?? "daily"}
              {monitor.schedule?.time ? ` @ ${monitor.schedule.time}` : ""}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
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
          <div><span className="text-muted-foreground">Status:</span> <Badge variant="outline">{monitor.status}</Badge></div>
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
                    <span>{r.generated_at?.slice(0, 16)}</span>
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
  const [frequency, setFrequency] = useState("daily");
  const [timeInput, setTimeInput] = useState("09:00");
  const [agentEnabled, setAgentEnabled] = useState(false);

  // Auto-add current input value on submit (so user doesn't lose typed text)
  const finalKeywords = mode === "keyword" && keywordInput.trim()
    ? [...keywords, keywordInput.trim()]
    : keywords;
  const finalTickers = mode === "ticker" && tickerInput.trim()
    ? [...tickers, tickerInput.trim()]
    : tickers;
  const hasTargets = mode === "keyword" ? finalKeywords.length > 0 : finalTickers.length > 0;

  const createMutation = useMutation({
    mutationFn: () => {
      const targets: Record<string, string[]> = {};
      if (mode === "keyword") targets.keywords = finalKeywords;
      if (mode === "ticker") targets.tickers = finalTickers;

      const schedule: Record<string, unknown> = { frequency };
      if (frequency !== "hourly") schedule.time = timeInput;

      return monitorApi.create({
        name: name || "Untitled", description, mode,
        targets, sources: ["news", "prices"], schedule,
        agent: { enabled: agentEnabled },
        output: { format: "summary", language: "zh" },
      } as any);
    },
    onSuccess: onCreated,
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
            <Label>Frequency</Label>
            <Select value={frequency} onValueChange={(v) => v && setFrequency(v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {FREQUENCY_OPTIONS.map((f) => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {frequency !== "hourly" && (
            <div className="space-y-2">
              <Label>Time</Label>
              <Input type="time" value={timeInput} onChange={(e) => setTimeInput(e.target.value)} />
            </div>
          )}
        </div>

        <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
          <div>
            <Label className="text-sm">AI Summary</Label>
            <p className="text-xs text-muted-foreground">Use Agent to generate intelligent summaries</p>
          </div>
          <Button variant={agentEnabled ? "default" : "outline"} size="sm" onClick={() => setAgentEnabled(!agentEnabled)}>
            {agentEnabled ? "Enabled" : "Disabled"}
          </Button>
        </div>

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
      </CardContent>
    </Card>
  );
}
