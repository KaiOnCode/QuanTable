import { AlertTriangle, Download, FlaskConical } from "lucide-react";
import { BacktestDecisionEvidence } from "@/components/backtest/backtest-decision-evidence";
import { BacktestEquityChart } from "@/components/backtest/backtest-equity-chart";
import { BacktestMetrics } from "@/components/backtest/backtest-metrics";
import { BacktestTradeEvidence } from "@/components/backtest/backtest-trade-evidence";
import { EmptyState } from "@/components/shared/empty-state";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  backtestExecutionTimingLabel,
  deriveBacktestJobState,
  displayBacktestIdentifier,
} from "@/lib/backtest-result-state";
import { backtestApi } from "@/lib/api/backtest";
import type { BacktestJobResponse } from "@/lib/types/models";
import { formatCurrency, formatDate } from "@/lib/utils";

type BacktestResultSurfaceProps = {
  readonly job: BacktestJobResponse;
};

function observedReasonLabel(code: "no_signals" | "not_ready" | "all_hold" | "all_rejected"): string {
  switch (code) {
    case "no_signals":
      return "No eligible signal was produced";
    case "not_ready":
      return "Decision context was not ready";
    case "all_hold":
      return "Every ready decision held";
    case "all_rejected":
      return "Every executable order was rejected";
  }
}

export function BacktestResultSurface({ job }: BacktestResultSurfaceProps) {
  const state = deriveBacktestJobState(job);
  if (state.kind !== "completed" && state.kind !== "completed_no_trades") return null;
  if (job.result === null || job.config === null) return null;

  const { config, result } = job;
  const noTrades = state.kind === "completed_no_trades";
  const frozenStrategyId = job.request?.strategy_id || config.strategy_id || "unavailable";
  const noTradePanel = state.kind === "completed_no_trades" ? (
    <Card>
      <CardContent className="pt-2">
        <EmptyState
          icon={<AlertTriangle className="h-12 w-12" />}
          title="No closed trades; performance is not trusted"
          description={state.observedCauseState === "reported"
            ? "The server observed the causes below. They are diagnostic evidence, not performance proof."
            : "The server did not expose an observed cause. This may include an open ending position; the UI will not infer HOLD, rejection, or no-signal behavior."}
          className="py-8"
        />
        {state.noTradeReasons.length > 0 ? (
          <ul className="space-y-2 pb-6 text-sm">
            {state.noTradeReasons.map((reason) => (
              <li key={reason.code} className="rounded-lg border border-input p-3">
                <span className="font-medium">{observedReasonLabel(reason.code)}</span>
                <span className="ml-2 font-mono text-muted-foreground">{reason.count}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  ) : null;

  return (
    <section className="space-y-6" aria-labelledby="backtest-result-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="backtest-result-title" className="text-base font-semibold">Completed {config.ticker} backtest</h3>
          <p className="text-sm text-muted-foreground">{config.start_date} to {config.end_date} · {config.run_frequency} rebalance cadence · benchmark {config.benchmark_symbol}</p>
          <p className="text-xs text-muted-foreground">Frozen strategy <span className="break-all font-mono text-foreground">{displayBacktestIdentifier(frozenStrategyId)}</span> · job <span className="break-all font-mono text-foreground">{displayBacktestIdentifier(job.id)}</span></p>
        </div>
        <Badge variant={noTrades ? "secondary" : "default"}>{noTrades ? "No closed trades" : "Completed"}</Badge>
      </div>

      {state.isExperimental ? <Card><CardContent className="flex items-start gap-3 pt-6"><FlaskConical className="mt-0.5" /><div><p className="font-medium">Agent experiment</p><p className="text-sm text-muted-foreground">This provider-dependent result is experimental and is not canonical performance evidence.</p></div></CardContent></Card> : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base"><AlertTriangle /> Backtest fidelity / Sample sufficiency</CardTitle>
          <CardDescription>Out-of-sample robustness: not evaluated</CardDescription>
        </CardHeader>
        <CardContent>
          {result.warnings.length > 0 ? (
            <ul className="space-y-2 text-sm text-muted-foreground">
              {result.warnings.map((warning) => <li key={warning} className="break-all font-mono">{warning}</li>)}
            </ul>
          ) : <p className="text-sm text-muted-foreground">No server sample warnings were returned for this job.</p>}
        </CardContent>
      </Card>

      {noTradePanel}

      <BacktestMetrics summary={result.metrics} />

      <Card>
        <CardHeader><CardTitle className="text-base">Run diagnostics</CardTitle><CardDescription>Frozen policy, data, costs, and end-position facts returned by the job.</CardDescription></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 xl:grid-cols-4">
            <div><dt className="text-xs text-muted-foreground">Execution timing</dt><dd className="mt-1">{backtestExecutionTimingLabel(config.execution_timing)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Costs</dt><dd className="mt-1 font-mono">{config.commission_bps} bps commission · {config.slippage_bps} bps slippage</dd></div>
            <div><dt className="text-xs text-muted-foreground">Sample</dt><dd className="mt-1">{config.evaluation_bar_count} evaluation bars{config.sample_first_date ? ` · ${formatDate(config.sample_first_date)} to ${formatDate(config.sample_last_date)}` : ""}</dd></div>
            <div><dt className="text-xs text-muted-foreground">End position</dt><dd className="mt-1 font-mono">{result.end_position.shares.toFixed(2)} {result.end_position.ticker} · {formatCurrency(result.end_position.market_value)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Fees / slippage</dt><dd className="mt-1 font-mono">{formatCurrency(result.metrics.total_fees_usd)} / {formatCurrency(result.metrics.total_slippage_usd)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Orders / fills / closed</dt><dd className="mt-1 font-mono">{result.orders.length} / {result.fills.length} / {result.closed_trades.length}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Policy hash</dt><dd className="mt-1 break-all font-mono text-xs">{displayBacktestIdentifier(result.provenance.policy_hash)}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Data hash</dt><dd className="mt-1 break-all font-mono text-xs">{displayBacktestIdentifier(result.provenance.data_snapshot_hash)}</dd></div>
            <div className="sm:col-span-2 xl:col-span-4"><dt className="text-xs text-muted-foreground">Canonical result hash</dt><dd className="mt-1 break-all font-mono text-xs">{displayBacktestIdentifier(result.provenance.canonical_result_hash)}</dd></div>
          </dl>
        </CardContent>
      </Card>

      <BacktestEquityChart equity={result.equity} />
      <BacktestDecisionEvidence decisions={job.decisions} orders={result.orders} />
      <BacktestTradeEvidence fills={result.fills} closedTrades={result.closed_trades} />

      <div className="flex flex-col gap-2 sm:flex-row">
        <a className={buttonVariants({ variant: "outline" })} href={backtestApi.tradesCsvUrl(job.id)} download><Download /> Export executions CSV</a>
        <a className={buttonVariants({ variant: "outline" })} href={backtestApi.closedTradesCsvUrl(job.id)} download><Download /> Export closed trades CSV</a>
        <a className={buttonVariants({ variant: "outline" })} href={backtestApi.decisionsCsvUrl(job.id)} download><Download /> Export decisions CSV</a>
        <a className={buttonVariants({ variant: "outline" })} href={backtestApi.decisionsJsonUrl(job.id)} download><Download /> Export decisions JSON</a>
      </div>
    </section>
  );
}
