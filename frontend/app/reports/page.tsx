"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { analyzeApi } from "@/lib/api/analyze";
import { reportsApi } from "@/lib/api/reports";
import { scannerApi } from "@/lib/api/scanner";
import { strategiesApi } from "@/lib/api/strategies";
import type {
  AnalysisSessionSnapshot,
  ReportJob,
  ScanRun,
  SectorReportSection,
  StockReportSection,
} from "@/lib/types/models";
import { formatDateTime } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  Clock,
  Download,
  FileText,
  Loader2,
  PieChart,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

const stockSections: readonly { value: StockReportSection; label: string }[] = [
  { value: "decision", label: "Decision" },
  { value: "market", label: "Market" },
  { value: "news", label: "News" },
  { value: "fundamentals", label: "Fundamentals" },
  { value: "risk", label: "Risk" },
];

const sectorSections: readonly SectorReportSection[] = [
  "overview",
  "constituents",
  "decision",
  "data_gaps",
  "sources",
];

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "The report request could not be completed.";
}

function statusVariant(status: ReportJob["status"]): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") return "default";
  if (status === "failed") return "destructive";
  return status === "running" ? "secondary" : "outline";
}

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const [ticker, setTicker] = useState("AAPL");
  const [strategyId, setStrategyId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [selectedSections, setSelectedSections] = useState<readonly StockReportSection[]>([
    "decision",
    "market",
    "news",
    "fundamentals",
    "risk",
  ]);
  const [theme, setTheme] = useState("");
  const [sectorStage, setSectorStage] = useState<
    "idle" | "scanning" | "reporting" | "completed" | "scanner_failed" | "report_failed"
  >("idle");

  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list({ limit: 100 }),
    retry: false,
  });
  const strategies = strategiesQuery.data?.items ?? [];
  const effectiveStrategyId = strategies.some((strategy) => strategy.id === strategyId)
    ? strategyId
    : strategies[0]?.id ?? "";

  const analysesQuery = useQuery({
    queryKey: ["reports", "completed-analyses"],
    queryFn: async () => {
      const history = await analyzeApi.listHistory(100);
      const completed = history.items.filter((item) => item.status === "completed");
      return Promise.all(completed.map((item) => analyzeApi.getHistory(item.session_id)));
    },
    retry: false,
  });
  const matchingAnalyses = useMemo(
    () => (analysesQuery.data ?? []).filter((analysis) =>
      analysis.status === "completed"
      && analysis.ticker.toUpperCase() === ticker.trim().toUpperCase()
      && analysis.request.strategy_id === effectiveStrategyId
      && analysis.result !== null,
    ),
    [analysesQuery.data, effectiveStrategyId, ticker],
  );
  const effectiveSessionId = matchingAnalyses.some((analysis) => analysis.session_id === sessionId)
    ? sessionId
    : matchingAnalyses[0]?.session_id ?? "";

  const reportsQuery = useQuery({
    queryKey: ["reports"],
    queryFn: () => reportsApi.list(),
    retry: false,
    refetchInterval: (query) => query.state.data?.items.some(
      (report) => report.status === "pending" || report.status === "running",
    ) ? 750 : false,
  });

  const stockMutation = useMutation({
    mutationFn: () => reportsApi.createStock({
      ticker: ticker.trim().toUpperCase(),
      strategy_id: effectiveStrategyId,
      session_id: effectiveSessionId,
      sections: selectedSections,
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });

  const sectorMutation = useMutation({
    mutationFn: async () => {
      setSectorStage("scanning");
      let scan: ScanRun;
      try {
        scan = await scannerApi.scanAgent({ mode: "agent", query: theme.trim() });
      } catch (error) {
        setSectorStage("scanner_failed");
        throw error;
      }
      if (scan.status !== "completed" || !scan.result || scan.result.matched_count === 0) {
        setSectorStage("scanner_failed");
        throw new Error("Scanner completed without matched tickers. Refine the theme and try again.");
      }
      setSectorStage("reporting");
      try {
        return await reportsApi.createSector({ scan_run_id: scan.id, sections: sectorSections });
      } catch (error) {
        setSectorStage("report_failed");
        throw error;
      }
    },
    onSuccess: async () => {
      setSectorStage("completed");
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
    },
  });

  const toggleSection = (section: StockReportSection) => {
    setSelectedSections((current) => current.includes(section)
      ? current.filter((item) => item !== section)
      : [...current, section]);
  };

  const stockReady = effectiveStrategyId.length > 0
    && effectiveSessionId.length > 0
    && selectedSections.length > 0
    && ticker.trim().length > 0;

  return (
    <Shell>
      <main className="min-w-0 space-y-6 p-4 sm:p-6">
        <header className="space-y-1">
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <FileText className="h-5 w-5" />
            Reports
          </h1>
          <p className="text-sm text-muted-foreground">
            Generate auditable PDFs from completed analyses and persisted scanner runs.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-2" aria-label="Report generators">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <TrendingUp className="h-4 w-4" /> Stock source report
              </CardTitle>
              <CardDescription>
                Select one completed analysis. Report generation never starts a new analysis.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="report-ticker">Ticker</Label>
                  <Input id="report-ticker" value={ticker} onChange={(event) => {
                    setTicker(event.target.value);
                    setSessionId("");
                  }} className="font-mono uppercase" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="report-strategy">Strategy</Label>
                  <Select value={effectiveStrategyId} onValueChange={(value) => {
                    setStrategyId(value ?? "");
                    setSessionId("");
                  }} disabled={strategies.length === 0}>
                    <SelectTrigger id="report-strategy" className="w-full"><SelectValue placeholder="Select strategy" /></SelectTrigger>
                    <SelectContent>{strategies.map((strategy) => (
                      <SelectItem key={strategy.id} value={strategy.id}>{strategy.name}</SelectItem>
                    ))}</SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="report-analysis">Completed analysis source</Label>
                <Select value={effectiveSessionId} onValueChange={(value) => setSessionId(value ?? "")} disabled={matchingAnalyses.length === 0}>
                  <SelectTrigger id="report-analysis" className="w-full"><SelectValue placeholder="No matching completed analysis" /></SelectTrigger>
                  <SelectContent>{matchingAnalyses.map((analysis: AnalysisSessionSnapshot) => (
                    <SelectItem key={analysis.session_id} value={analysis.session_id}>
                      {analysis.ticker} · {formatDateTime(analysis.completed_at ?? analysis.updated_at ?? analysis.created_at)}
                    </SelectItem>
                  ))}</SelectContent>
                </Select>
              </div>

              {analysesQuery.isError ? (
                <p className="text-sm text-destructive" role="alert">{messageFor(analysesQuery.error)}</p>
              ) : matchingAnalyses.length === 0 ? (
                <div className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                  No completed analysis matches this ticker and strategy. Run it in Quick Ask, then refresh sources.
                </div>
              ) : null}

              <fieldset className="space-y-2">
                <legend className="text-sm font-medium">Included sections</legend>
                <div className="flex flex-wrap gap-2">
                  {stockSections.map((section) => {
                    const selected = selectedSections.includes(section.value);
                    return (
                      <Button key={section.value} type="button" size="sm" variant={selected ? "secondary" : "outline"} aria-pressed={selected} onClick={() => toggleSection(section.value)}>
                        {selected ? <Check className="h-3.5 w-3.5" /> : null}{section.label}
                      </Button>
                    );
                  })}
                </div>
              </fieldset>

              <Button className="w-full" disabled={!stockReady || stockMutation.isPending} onClick={() => stockMutation.mutate()}>
                {stockMutation.isPending ? <Loader2 className="animate-spin" /> : <FileText />}
                Generate stock report
              </Button>
              {stockMutation.isError ? <p className="text-sm text-destructive" role="alert">{messageFor(stockMutation.error)}</p> : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <PieChart className="h-4 w-4" /> Sector scanner report
              </CardTitle>
              <CardDescription>
                Stage 1 compiles and persists an Agent Scanner run. Stage 2 reports only its matched tickers.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="report-theme">Sector or theme</Label>
                <Input id="report-theme" value={theme} onChange={(event) => setTheme(event.target.value)} placeholder="Semiconductors with strong momentum" />
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground" aria-live="polite">
                <div className="rounded-lg border p-3"><span className="font-medium text-foreground">1. Scanner</span><br />{
                  sectorStage === "scanning" ? "Running…"
                    : sectorStage === "scanner_failed" ? "Failed"
                      : sectorStage === "idle" ? "Ready" : "Completed"
                }</div>
                <div className="rounded-lg border p-3"><span className="font-medium text-foreground">2. Report</span><br />{
                  sectorStage === "reporting" ? "Submitting…"
                    : sectorStage === "completed" ? "Accepted"
                      : sectorStage === "report_failed" ? "Failed" : "Waiting"
                }</div>
              </div>
              <Button className="w-full" variant="outline" disabled={theme.trim().length === 0 || sectorMutation.isPending} onClick={() => sectorMutation.mutate()}>
                {sectorMutation.isPending ? <Loader2 className="animate-spin" /> : <FileText />}
                Generate sector report
              </Button>
              {sectorMutation.isError ? <p className="text-sm text-destructive" role="alert">{messageFor(sectorMutation.error)}</p> : null}
            </CardContent>
          </Card>
        </section>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base"><Clock className="h-4 w-4" />Report history</CardTitle>
              <CardDescription>Persisted jobs survive reloads. Downloads appear only after completion.</CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={() => reportsQuery.refetch()} disabled={reportsQuery.isFetching}>
              <RefreshCw className={reportsQuery.isFetching ? "animate-spin" : ""} />Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {reportsQuery.isError ? (
              <EmptyState icon={<AlertTriangle />} title="Report history unavailable" description={messageFor(reportsQuery.error)} action={<Button variant="outline" onClick={() => reportsQuery.refetch()}>Retry</Button>} />
            ) : reportsQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 className="animate-spin" />Loading report history…</div>
            ) : (reportsQuery.data?.items.length ?? 0) === 0 ? (
              <EmptyState title="No reports yet" description="Source-driven report jobs will appear here." />
            ) : (
              <>
              <div className="space-y-3 md:hidden">
                {reportsQuery.data?.items.map((report) => (
                  <article key={report.id} className="space-y-3 rounded-lg border p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate font-medium">{report.title}</h3>
                        <p className="font-mono text-xs text-muted-foreground">{report.tickers.join(", ")}</p>
                      </div>
                      <Badge variant={statusVariant(report.status)} className="shrink-0 capitalize">{report.status}</Badge>
                    </div>
                    <div className="flex items-end justify-between gap-3">
                      <div className="text-xs text-muted-foreground">
                        <p className="capitalize">{report.report_type} · {report.source_ids.length} source{report.source_ids.length === 1 ? "" : "s"}</p>
                        <p>{formatDateTime(report.updated_at)}</p>
                        {report.error ? <p className="mt-1 text-destructive">{report.error}</p> : null}
                      </div>
                      <Button size="sm" variant="outline" disabled={report.status !== "completed"} onClick={() => { window.location.href = reportsApi.getDownloadUrl(report.id); }} aria-label={`Download ${report.title}`}>
                        {report.status === "completed" ? <Download /> : report.status === "failed" ? <AlertTriangle /> : <Loader2 className="animate-spin" />}
                        Download
                      </Button>
                    </div>
                  </article>
                ))}
              </div>
              <div className="hidden overflow-x-auto md:block">
                <Table className="min-w-[760px]">
                  <TableHeader><TableRow><TableHead>Title</TableHead><TableHead>Type</TableHead><TableHead>Sources</TableHead><TableHead>Status</TableHead><TableHead>Updated</TableHead><TableHead className="text-right">Download</TableHead></TableRow></TableHeader>
                  <TableBody>{reportsQuery.data?.items.map((report) => (
                    <TableRow key={report.id}>
                      <TableCell><div className="font-medium">{report.title}</div><div className="font-mono text-xs text-muted-foreground">{report.tickers.join(", ")}</div></TableCell>
                      <TableCell className="capitalize">{report.report_type}</TableCell>
                      <TableCell>{report.source_ids.length} persisted artifact{report.source_ids.length === 1 ? "" : "s"}</TableCell>
                      <TableCell><Badge variant={statusVariant(report.status)} className="capitalize">{report.status}</Badge>{report.error ? <p className="mt-1 max-w-48 text-xs text-destructive">{report.error}</p> : null}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{formatDateTime(report.updated_at)}</TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="ghost" disabled={report.status !== "completed"} onClick={() => { window.location.href = reportsApi.getDownloadUrl(report.id); }} aria-label={`Download ${report.title}`}>
                          {report.status === "completed" ? <Download /> : report.status === "failed" ? <AlertTriangle /> : <Loader2 className="animate-spin" />}
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}</TableBody>
                </Table>
              </div>
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </Shell>
  );
}
