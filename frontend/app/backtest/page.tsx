"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart as RechartsLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Shell } from "@/components/layout/shell";
import { BacktestMetrics } from "@/components/backtest/backtest-metrics";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
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
import { backtestApi } from "@/lib/api/backtest";
import { strategiesApi } from "@/lib/api/strategies";
import type { BacktestRequest } from "@/lib/types/models";
import { usePersistedBacktestId } from "@/lib/use-persisted-backtest-id";
import { formatCurrency, formatDate, formatPercent } from "@/lib/utils";
import { AlertCircle, BarChart3, Download, LineChart, Loader2, Play, RefreshCw } from "lucide-react";

const DEFAULT_DATE_FROM = "2024-01-02";
const DEFAULT_DATE_TO = "2024-03-29";

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof Error && error.message.startsWith("HTTP 404:");
}

function BacktestContent() {
  const searchParams = useSearchParams();
  const [strategyId, setStrategyId] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [dateFrom, setDateFrom] = useState(DEFAULT_DATE_FROM);
  const [dateTo, setDateTo] = useState(DEFAULT_DATE_TO);
  const [frequency, setFrequency] = useState<BacktestRequest["frequency"]>("weekly");
  const [benchmark, setBenchmark] = useState("SPY");
  const [validationError, setValidationError] = useState<string | null>(null);
  const { backtestId, isRestored, persistBacktestId, syncBacktestStatus } =
    usePersistedBacktestId(searchParams.get("backtest_id"));

  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list(),
  });
  const strategies = strategiesQuery.data?.items ?? [];
  const selectedStrategyId =
    strategies.find((strategy) => strategy.id === strategyId)?.id ??
    strategies[0]?.id ??
    "";
  const selectedStrategyName =
    strategies.find((strategy) => strategy.id === selectedStrategyId)?.name ?? "";
  const jobQuery = useQuery({
    queryKey: ["backtest", backtestId],
    queryFn: () => backtestApi.get(backtestId ?? ""),
    enabled: backtestId !== null,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 1000 : false;
    },
  });
  const job = jobQuery.data;

  useEffect(() => {
    if (job) {
      syncBacktestStatus(job.backtest_id, job.status);
    } else if (backtestId && isNotFoundError(jobQuery.error)) {
      syncBacktestStatus(backtestId, "not_found");
    }
  }, [backtestId, job, jobQuery.error, syncBacktestStatus]);

  const runMutation = useMutation({
    mutationFn: (request: BacktestRequest) => backtestApi.create(request),
    onSuccess: (created) => {
      setValidationError(null);
      persistBacktestId(created.backtest_id, created.status);
    },
  });

  const canSubmit = selectedStrategyId.length > 0 && ticker.trim().length > 0 && !runMutation.isPending;
  const isRunning = job?.status === "pending" || job?.status === "running";
  const completed = job?.status === "completed" ? job.result : null;
  const jobError = job?.status === "failed" ? job.error?.message ?? "Backtest failed." : null;
  const requestError = runMutation.isError ? messageFor(runMutation.error) : null;
  const resultConfig = completed?.config;

  const chartData = useMemo(
    () => completed?.series.map((point) => ({
      ...point,
      dateLabel: formatDate(point.date),
    })) ?? [],
    [completed]
  );

  const submit = () => {
    const normalizedTicker = ticker.trim().toUpperCase();
    const normalizedBenchmark = benchmark.trim().toUpperCase();
    if (!selectedStrategyId) {
      setValidationError("Select a persisted strategy before running a backtest.");
      return;
    }
    if (!normalizedTicker) {
      setValidationError("Enter one ticker symbol.");
      return;
    }
    if (!normalizedBenchmark) {
      setValidationError("Enter a benchmark symbol.");
      return;
    }
    if (dateFrom > dateTo) {
      setValidationError("Date from must not be after date to.");
      return;
    }
    setValidationError(null);
    runMutation.mutate({
      strategy_id: selectedStrategyId,
      ticker: normalizedTicker,
      date_from: dateFrom,
      date_to: dateTo,
      frequency,
      benchmark: normalizedBenchmark,
    });
  };

  return (
    <Shell>
      <div className="space-y-6 p-4 sm:p-6">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <LineChart className="h-5 w-5" /> Backtest
          </h2>
          <p className="text-sm text-muted-foreground">
            Run one persisted strategy against a single historical ticker and independent benchmark.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Configuration</CardTitle>
            <CardDescription>All values are sent to the persisted ACTIVE backtest job.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="space-y-2">
                <Label htmlFor="backtest-strategy">Strategy</Label>
                <Select value={selectedStrategyId} onValueChange={(value) => value && setStrategyId(value)} disabled={strategiesQuery.isLoading || strategiesQuery.isError || strategies.length === 0}>
                  <SelectTrigger id="backtest-strategy" aria-label="Strategy">
                    <span className="flex flex-1 truncate text-left">
                      {selectedStrategyName || (strategiesQuery.isLoading ? "Loading strategies" : "Select strategy")}
                    </span>
                  </SelectTrigger>
                  <SelectContent>
                    {strategies.map((strategy) => <SelectItem key={strategy.id} value={strategy.id}>{strategy.name}</SelectItem>)}
                  </SelectContent>
                </Select>
                {strategiesQuery.isError ? <p className="text-xs text-destructive" role="alert">Failed to load strategies: {messageFor(strategiesQuery.error)}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-ticker">Ticker</Label>
                <Input id="backtest-ticker" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} placeholder="AAPL" autoCapitalize="characters" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-date-from">Date From</Label>
                <Input id="backtest-date-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-date-to">Date To</Label>
                <Input id="backtest-date-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-frequency">Frequency</Label>
                <Select value={frequency} onValueChange={(value) => value && setFrequency(value as BacktestRequest["frequency"])}>
                  <SelectTrigger id="backtest-frequency"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-benchmark">Benchmark</Label>
                <Input id="backtest-benchmark" value={benchmark} onChange={(event) => setBenchmark(event.target.value.toUpperCase())} placeholder="SPY" autoCapitalize="characters" />
              </div>
              <div className="flex items-end">
                <Button className="w-full" onClick={submit} disabled={!canSubmit}>
                  {runMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                  Run Backtest
                </Button>
              </div>
            </div>
            {strategies.length === 0 && !strategiesQuery.isLoading && !strategiesQuery.isError ? <p className="mt-4 text-sm text-muted-foreground">Create a strategy before starting a backtest.</p> : null}
            {validationError || requestError ? <p className="mt-4 text-sm text-destructive" role="alert">{validationError ?? requestError}</p> : null}
          </CardContent>
        </Card>

        {backtestId && jobQuery.isLoading ? <Card><CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Loading backtest {backtestId}</CardContent></Card> : null}
        {jobQuery.isError ? <Card className="border-destructive"><CardContent className="pt-6" role="alert">Unable to load this backtest: {messageFor(jobQuery.error)}</CardContent></Card> : null}
        {isRunning ? <Card><CardContent className="flex items-center gap-3 pt-6"><Loader2 className="h-5 w-5 animate-spin" /><div><p className="font-medium">Backtest {job?.status}</p><p className="text-sm text-muted-foreground">The page will refresh this persisted job until it reaches a terminal state.</p></div></CardContent></Card> : null}
        {jobError ? <Card className="border-destructive"><CardContent className="flex items-start justify-between gap-4 pt-6" role="alert"><div><p className="flex items-center gap-2 font-medium text-destructive"><AlertCircle className="h-4 w-4" /> Backtest failed</p><p className="mt-1 text-sm text-muted-foreground">{jobError}</p></div><Button variant="outline" onClick={submit} disabled={runMutation.isPending}><RefreshCw className="mr-2 h-4 w-4" /> Retry</Button></CardContent></Card> : null}

        {isRestored && !backtestId && !runMutation.isPending ? <Card><CardContent className="pt-2"><EmptyState icon={<BarChart3 className="h-12 w-12" />} title="No backtest selected" description="Choose a strategy and historical window, then run a persisted backtest." /></CardContent></Card> : null}

        {completed && resultConfig && backtestId ? <div className="space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><h3 className="text-base font-semibold">Completed {resultConfig.ticker} backtest</h3><p className="text-sm text-muted-foreground">{resultConfig.start_date} to {resultConfig.end_date} · {resultConfig.frequency} decisions · benchmark {resultConfig.benchmark_symbol}</p></div>
            <Badge>Completed</Badge>
          </div>
          <BacktestMetrics summary={completed.summary} />
          <Card>
            <CardHeader><CardTitle className="text-base">Equity and Drawdown</CardTitle><CardDescription>{chartData.length} daily equity points returned by the completed job.</CardDescription></CardHeader>
            <CardContent><div className="h-80 min-w-0"><ResponsiveContainer width="100%" height="100%"><RechartsLineChart data={chartData} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="dateLabel" minTickGap={32} /><YAxis yAxisId="equity" tickFormatter={(value: number) => `$${Math.round(value)}`} width={70} /><YAxis yAxisId="drawdown" orientation="right" tickFormatter={(value: number) => `${value}%`} width={55} /><Tooltip formatter={(value, name) => { const numberValue = typeof value === "number" ? value : Number(value); const label = String(name ?? ""); return [label.includes("drawdown") ? formatPercent(numberValue) : formatCurrency(numberValue), label]; }} /><Legend /><Line yAxisId="equity" type="monotone" dataKey="strategy_equity" name="Strategy equity" stroke="var(--primary)" strokeWidth={2} dot={false} /><Line yAxisId="equity" type="monotone" dataKey="benchmark_equity" name="Benchmark equity" stroke="var(--muted-foreground)" strokeWidth={2} dot={false} /><Line yAxisId="drawdown" type="monotone" dataKey="strategy_drawdown_pct" name="Strategy drawdown" stroke="var(--destructive)" strokeWidth={1.5} dot={false} /></RechartsLineChart></ResponsiveContainer></div></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Trades</CardTitle><CardDescription>Executed trades from the completed backtest.</CardDescription></CardHeader>
            <CardContent className="overflow-x-auto p-0"><Table><TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Ticker</TableHead><TableHead>Side</TableHead><TableHead className="text-right">Quantity</TableHead><TableHead className="text-right">Price</TableHead><TableHead className="text-right">Realized P/L</TableHead><TableHead className="text-right">Equity After</TableHead></TableRow></TableHeader><TableBody>{completed.trades.length === 0 ? <TableRow><TableCell colSpan={7} className="py-8 text-center text-muted-foreground">This completed backtest produced no trades.</TableCell></TableRow> : completed.trades.map((trade) => <TableRow key={trade.order_id}><TableCell>{formatDate(trade.timestamp)}</TableCell><TableCell className="font-mono">{trade.ticker}</TableCell><TableCell><Badge variant="outline">{trade.side}</Badge></TableCell><TableCell className="text-right font-mono">{trade.quantity.toFixed(2)}</TableCell><TableCell className="text-right font-mono">{formatCurrency(trade.price)}</TableCell><TableCell className="text-right font-mono">{formatCurrency(trade.realized_pnl)}</TableCell><TableCell className="text-right font-mono">{formatCurrency(trade.equity_after)}</TableCell></TableRow>)}</TableBody></Table></CardContent>
          </Card>
          <div><a className={buttonVariants({ variant: "outline" })} href={backtestApi.csvUrl(backtestId)} download><Download className="mr-2 inline h-4 w-4" /> Export trades CSV</a></div>
        </div> : null}
      </div>
    </Shell>
  );
}

export default function BacktestPage() {
  return (
    <Suspense fallback={<Shell><div className="p-6 text-sm text-muted-foreground">Loading backtest…</div></Shell>}>
      <BacktestContent />
    </Suspense>
  );
}
