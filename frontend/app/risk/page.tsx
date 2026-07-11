"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { riskApi } from "@/lib/api/risk";
import { strategiesApi } from "@/lib/api/strategies";
import type {
  ConcentrationResult,
  RiskOverview,
  RiskStatus,
} from "@/lib/types/models";
import { formatDate, formatDateTime, formatPercent } from "@/lib/utils";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Loader2,
  Play,
  Shield,
  TrendingDown,
} from "lucide-react";

const STATUS_COPY: Readonly<Record<Exclude<RiskStatus, "complete">, { title: string; description: string }>> = {
  unavailable: {
    title: "Decision targets unavailable",
    description: "Run analysis for this strategy so it has a persisted, non-zero target position.",
  },
  partial: {
    title: "Market history is partial",
    description: "Valid decision targets exist, but at least 60 common close dates are required for historical risk metrics.",
  },
  invalid: {
    title: "Decision targets are invalid",
    description: "Correct targets outside 0–100% or reduce total exposure to 100% or less.",
  },
};

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function decimalPercent(value: number | null): string {
  return value === null ? "Unavailable" : formatPercent(value * 100);
}

function drawdownPercent(value: number): string {
  const percentage = value * 100;
  return `${Math.abs(percentage) < 0.05 ? "0.0" : percentage.toFixed(1)}%`;
}

function histogram(values: readonly number[]): readonly { bucket: string; count: number }[] {
  if (values.length === 0) return [];
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const binCount = Math.min(12, Math.max(5, Math.ceil(Math.sqrt(values.length))));
  const width = maximum === minimum ? 1 : (maximum - minimum) / binCount;
  const counts = Array.from({ length: binCount }, () => 0);
  for (const value of values) {
    const index = maximum === minimum
      ? 0
      : Math.min(binCount - 1, Math.floor((value - minimum) / width));
    counts[index] += 1;
  }
  return counts.map((count, index) => ({
    bucket: `${((minimum + index * width) * 100).toFixed(1)}%`,
    count,
  }));
}

function Warnings({ items }: { items: readonly string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm" role="status">
      {items.map((warning) => <p key={warning}>{warning}</p>)}
    </div>
  );
}

function Exposure({ overview }: { overview: RiskOverview }) {
  const rows = Object.entries(overview.exposure.weights);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Decision Target Exposure</CardTitle>
        <CardDescription>Targets are analysis decisions, not executed holdings.</CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader><TableRow><TableHead>Ticker</TableHead><TableHead className="text-right">Target</TableHead><TableHead>Latest decision</TableHead></TableRow></TableHeader>
          <TableBody>
            {rows.map(([ticker, weight]) => {
              const decision = overview.exposure.decisions.find((item) => item.ticker === ticker);
              return <TableRow key={ticker}><TableCell className="font-mono font-medium">{ticker}</TableCell><TableCell className="text-right font-mono">{decimalPercent(weight)}</TableCell><TableCell>{decision ? formatDateTime(decision.created_at) : "Unavailable"}</TableCell></TableRow>;
            })}
            {overview.exposure.cash_weight !== null ? <TableRow><TableCell className="font-medium">Cash</TableCell><TableCell className="text-right font-mono">{decimalPercent(overview.exposure.cash_weight)}</TableCell><TableCell>Residual target</TableCell></TableRow> : null}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function Concentration({ title, result }: { title: string; result: ConcentrationResult }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle><CardDescription>HHI {result.herfindahl_index.toFixed(3)}</CardDescription></CardHeader>
      <CardContent className="space-y-3">
        {Object.entries(result.weights).map(([label, weight]) => <div key={label} className="space-y-1"><div className="flex justify-between gap-3 text-sm"><span className="truncate">{label}</span><span className="font-mono">{decimalPercent(weight)}</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, weight * 100)}%` }} /></div></div>)}
      </CardContent>
    </Card>
  );
}

function CompleteAnalytics({ overview }: { overview: RiskOverview }) {
  const distribution = useMemo(() => histogram(overview.portfolio_returns), [overview.portfolio_returns]);
  const worstIndex = overview.portfolio_returns.reduce((current, value, index, values) => value < values[current] ? index : current, 0);
  const worstReturn = overview.portfolio_returns[worstIndex] ?? null;
  const worstDate = overview.common_dates[worstIndex + 1] ?? null;
  const returnMinimum = Math.min(...overview.portfolio_returns);
  const returnMaximum = Math.max(...overview.portfolio_returns);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[['VaR 95%', overview.var_95], ['CVaR 95%', overview.cvar_95], ['VaR 99%', overview.var_99], ['Max drawdown', overview.max_drawdown]].map(([label, value]) => <Card key={String(label)}><CardHeader className="pb-2"><CardDescription>{label}</CardDescription><CardTitle className="font-mono text-xl text-destructive">{decimalPercent(value as number | null)}</CardTitle></CardHeader></Card>)}
      </div>
      <div className="grid gap-6 xl:grid-cols-2">
        <Card><CardHeader><CardTitle id="return-distribution-title" className="flex items-center gap-2 text-base"><BarChart3 className="h-4 w-4" />Return Distribution</CardTitle><CardDescription>{overview.observation_count} weighted daily return observations</CardDescription></CardHeader><CardContent><p id="return-distribution-summary" className="sr-only">Daily returns range from {decimalPercent(returnMinimum)} to {decimalPercent(returnMaximum)} across {overview.observation_count} observations.</p><div className="h-64 min-w-0" role="img" aria-labelledby="return-distribution-title" aria-describedby="return-distribution-summary"><ResponsiveContainer width="100%" height="100%"><BarChart data={distribution} accessibilityLayer margin={{ right: 8 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="bucket" minTickGap={18} padding={{ left: 8, right: 16 }} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} /><YAxis allowDecimals={false} width={32} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} /><Tooltip /><Bar dataKey="count" name="Days" fill="var(--primary)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></CardContent></Card>
        <Card><CardHeader><CardTitle id="drawdown-title" className="flex items-center gap-2 text-base"><TrendingDown className="h-4 w-4" />Drawdown</CardTitle><CardDescription>Peak-to-trough history through {overview.as_of ? formatDate(overview.as_of) : "unavailable"}</CardDescription></CardHeader><CardContent><p id="drawdown-summary" className="sr-only">Maximum historical drawdown is {decimalPercent(overview.max_drawdown)} through {overview.as_of ? formatDate(overview.as_of) : "an unavailable date"}.</p><div className="h-64 min-w-0" role="img" aria-labelledby="drawdown-title" aria-describedby="drawdown-summary"><ResponsiveContainer width="100%" height="100%"><AreaChart data={overview.drawdown_curve} accessibilityLayer><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" minTickGap={32} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} /><YAxis tickFormatter={drawdownPercent} width={52} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} /><Tooltip formatter={(value) => [decimalPercent(Number(value)), "Drawdown"]} /><Area type="monotone" dataKey="value" stroke="var(--destructive)" fill="var(--destructive)" fillOpacity={0.18} /></AreaChart></ResponsiveContainer></div></CardContent></Card>
      </div>
      <Card><CardHeader><CardTitle className="text-base">Historical Worst Day</CardTitle><CardDescription>Observed in the weighted decision-target return series, not a modeled scenario.</CardDescription></CardHeader><CardContent><p className="text-2xl font-mono font-semibold text-destructive">{decimalPercent(worstReturn)}</p><p className="text-sm text-muted-foreground">{worstDate ? formatDate(worstDate) : "Date unavailable"}</p></CardContent></Card>
      <div className="grid gap-6 xl:grid-cols-2"><Concentration title="Ticker Concentration" result={overview.ticker_concentration} /><Concentration title="Sector Concentration" result={overview.sector_concentration} /></div>
      <Card><CardHeader><CardTitle className="text-base">Correlation Matrix</CardTitle><CardDescription>Unknown means the return pair has no usable variance.</CardDescription></CardHeader><CardContent className="overflow-x-auto p-0"><Table><TableHeader><TableRow><TableHead /><>{overview.correlation.labels.map((label) => <TableHead key={label} className="text-center font-mono">{label}</TableHead>)}</></TableRow></TableHeader><TableBody>{overview.correlation.labels.map((label, row) => <TableRow key={label}><TableCell className="font-mono font-medium">{label}</TableCell>{overview.correlation.matrix[row]?.map((value, column) => <TableCell key={`${label}-${overview.correlation.labels[column]}`} className="text-center font-mono">{value === null ? "Unknown" : value.toFixed(2)}</TableCell>)}</TableRow>)}</TableBody></Table></CardContent></Card>
      <Exposure overview={overview} />
    </div>
  );
}

export default function RiskPage() {
  const [requestedStrategy, setRequestedStrategy] = useState("");
  const [shockPercent, setShockPercent] = useState("-10");
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: () => strategiesApi.list(), retry: false });
  const strategies = strategiesQuery.data?.items ?? [];
  const selectedStrategy = strategies.find((strategy) => strategy.id === requestedStrategy)?.id ?? strategies[0]?.id ?? "";
  const selectedName = strategies.find((strategy) => strategy.id === selectedStrategy)?.name ?? "";
  const overviewQuery = useQuery({ queryKey: ["risk", "overview", selectedStrategy], queryFn: () => riskApi.overview(selectedStrategy), enabled: selectedStrategy.length > 0, retry: false });
  const stressMutation = useMutation({ mutationFn: (shock: number) => riskApi.stress(selectedStrategy, { uniform_market_shock: shock }) });
  const overview = overviewQuery.data?.strategy_id === selectedStrategy ? overviewQuery.data : undefined;
  const shock = Number(shockPercent);
  const validShock = Number.isFinite(shock) && shock >= -100 && shock <= 100;
  const selectStrategy = (value: string | null) => {
    if (value === null) return;
    setRequestedStrategy(value);
    stressMutation.reset();
  };

  return (
    <Shell>
      <div className="space-y-6 p-4 sm:p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div><h2 className="flex items-center gap-2 text-lg font-semibold"><Shield className="h-5 w-5" />Risk Analytics</h2><p className="text-sm text-muted-foreground">Historical risk from persisted decision targets and cached closes.</p></div>
          <div className="w-full space-y-2 md:w-72"><Label htmlFor="risk-strategy">Strategy</Label><Select value={selectedStrategy} onValueChange={selectStrategy} disabled={strategiesQuery.isLoading || strategiesQuery.isError || strategies.length === 0}><SelectTrigger id="risk-strategy" aria-label="Strategy"><span className="flex flex-1 truncate text-left">{selectedName || (strategiesQuery.isLoading ? "Loading strategies" : "Select strategy")}</span></SelectTrigger><SelectContent>{strategies.map((strategy) => <SelectItem key={strategy.id} value={strategy.id}>{strategy.name}</SelectItem>)}</SelectContent></Select></div>
        </div>

        {strategiesQuery.isError ? <Card className="border-destructive"><CardContent className="pt-6 text-sm text-destructive" role="alert">Failed to load strategies: {messageFor(strategiesQuery.error)}</CardContent></Card> : null}
        {!strategiesQuery.isLoading && !strategiesQuery.isError && strategies.length === 0 ? <Card><EmptyState icon={<Shield className="h-12 w-12" />} title="No strategies available" description="Create a strategy and persist analysis decisions before opening Risk Analytics." /></Card> : null}
        {selectedStrategy && overviewQuery.isLoading ? <Card><CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading {selectedName} risk data</CardContent></Card> : null}
        {overviewQuery.isError ? <Card className="border-destructive"><CardContent className="pt-6" role="alert"><p className="font-medium text-destructive">Risk service unavailable</p><p className="mt-1 text-sm text-muted-foreground">{messageFor(overviewQuery.error)}</p><Button className="mt-4" variant="outline" onClick={() => void overviewQuery.refetch()}>Retry</Button></CardContent></Card> : null}

        {overview ? <><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">Decision target exposure</Badge><Badge variant="secondary">{overview.status}</Badge><span className="text-sm text-muted-foreground">Decision as of {overview.exposure.as_of ? formatDateTime(overview.exposure.as_of) : "unavailable"}</span></div><Warnings items={overview.warnings} />{overview.status === "complete" ? <CompleteAnalytics overview={overview} /> : <div className="space-y-6"><Card><EmptyState icon={overview.status === "invalid" ? <AlertTriangle className="h-12 w-12" /> : <Activity className="h-12 w-12" />} title={STATUS_COPY[overview.status].title} description={STATUS_COPY[overview.status].description} /></Card>{overview.exposure.weights && Object.keys(overview.exposure.weights).length > 0 ? <Exposure overview={overview} /> : null}</div>}</> : null}

        {overview?.status === "complete" ? <Card><CardHeader><CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="h-4 w-4" />Uniform Market Shock</CardTitle><CardDescription>Applies one decimal market return to gross decision-target exposure. This is a model assumption.</CardDescription></CardHeader><CardContent className="space-y-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-end"><div className="w-full space-y-2 sm:max-w-48"><Label htmlFor="market-shock">Market shock (%)</Label><Input id="market-shock" type="number" min={-100} max={100} step={1} value={shockPercent} onChange={(event) => { setShockPercent(event.target.value); stressMutation.reset(); }} aria-invalid={!validShock} /></div><Button disabled={!validShock || stressMutation.isPending} onClick={() => stressMutation.mutate(shock / 100)}>{stressMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}Run stress</Button></div>{!validShock ? <p className="text-sm text-destructive" role="alert">Enter a shock from -100% to 100%.</p> : null}{stressMutation.isError ? <p className="text-sm text-destructive" role="alert">Stress request failed: {messageFor(stressMutation.error)}</p> : null}{stressMutation.data?.strategy_id === selectedStrategy ? <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">Input shock</p><p className="font-mono text-lg">{decimalPercent(stressMutation.data.uniform_market_shock.shock)}</p></div><div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">Gross exposure</p><p className="font-mono text-lg">{decimalPercent(stressMutation.data.uniform_market_shock.gross_exposure)}</p></div><div className="rounded-lg bg-muted/50 p-3"><p className="text-xs text-muted-foreground">Modeled impact</p><p className="font-mono text-lg text-destructive">{decimalPercent(stressMutation.data.uniform_market_shock.impact)}</p></div></div> : null}</CardContent></Card> : null}
      </div>
    </Shell>
  );
}
