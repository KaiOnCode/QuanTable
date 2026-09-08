import { AlertCircle, BarChart3, Loader2, RefreshCw } from "lucide-react";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { deriveBacktestJobState } from "@/lib/backtest-result-state";
import type { BacktestJobResponse } from "@/lib/types/models";
import { formatDate } from "@/lib/utils";

type BacktestJobStateProps = {
  readonly backtestId: string | null;
  readonly job: BacktestJobResponse | undefined;
  readonly isRestored: boolean;
  readonly isLoading: boolean;
  readonly loadError: string | null;
  readonly actionError: string | null;
  readonly isReplaying: boolean;
  readonly isRunningCurrent: boolean;
  readonly onReplay: (backtestId: string) => void;
  readonly onRunCurrent: () => void;
};

function progressValue(
  completed: number,
  total: number,
  barsProcessed: number,
  barsTotal: number,
): number {
  const numerator = total > 0 ? completed : barsProcessed;
  const denominator = total > 0 ? total : barsTotal;
  if (denominator <= 0) return 0;
  return Math.min(100, Math.round((numerator / denominator) * 100));
}

export function BacktestJobState({
  backtestId,
  job,
  isRestored,
  isLoading,
  loadError,
  actionError,
  isReplaying,
  isRunningCurrent,
  onReplay,
  onRunCurrent,
}: BacktestJobStateProps) {
  if (backtestId && isLoading) {
    return (
      <Card><CardContent className="flex items-center gap-2 pt-6 text-sm text-muted-foreground"><Loader2 className="animate-spin" /> Loading backtest {backtestId}</CardContent></Card>
    );
  }
  if (loadError) {
    return <Card className="border-destructive"><CardContent className="pt-6 text-sm" role="alert">Unable to load this backtest: {loadError}</CardContent></Card>;
  }
  if (job === undefined) {
    return isRestored ? <Card><CardContent className="pt-2"><EmptyState icon={<BarChart3 className="h-12 w-12" />} title="No backtest selected" description="Choose a strategy and historical window, then run a persisted backtest." /></CardContent></Card> : null;
  }

  const state = deriveBacktestJobState(job);
  switch (state.kind) {
    case "running": {
      const value = progressValue(
        state.decisionsCompleted,
        state.decisionsTotal,
        state.barsProcessed,
        state.barsTotal,
      );
      return (
        <Card aria-live="polite">
          <CardContent className="space-y-3 pt-6">
            <div className="flex items-start gap-3"><Loader2 className="mt-0.5 animate-spin" /><div><p className="font-medium">Backtest {state.status}</p><p className="text-sm text-muted-foreground">{state.decisionsCompleted}/{state.decisionsTotal} decisions completed{state.currentDecisionDate ? ` through ${formatDate(state.currentDecisionDate)}` : ""}.</p></div></div>
            <Progress value={value}><ProgressLabel>Durable worker progress</ProgressLabel><ProgressValue /></Progress>
          </CardContent>
        </Card>
      );
    }
    case "failed":
      return (
        <Card className="border-destructive" role="alert">
          <CardContent className="space-y-4 pt-6">
            <div><p className="flex items-center gap-2 font-medium text-destructive"><AlertCircle /> Backtest failed</p><p className="mt-1 text-sm text-muted-foreground">{state.error.message}</p><dl className="mt-3 grid grid-cols-1 gap-2 text-xs text-muted-foreground sm:grid-cols-3"><div><dt>Stage</dt><dd className="font-mono text-foreground">{state.error.stage ?? "unavailable"}</dd></div><div><dt>Decision date</dt><dd className="font-mono text-foreground">{state.error.decisionDate ? formatDate(state.error.decisionDate) : "unavailable"}</dd></div><div><dt>Attempt</dt><dd className="font-mono text-foreground">{state.error.attempt ?? "unavailable"}</dd></div></dl></div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button variant="outline" onClick={() => onReplay(job.id)} disabled={isReplaying || isRunningCurrent}>{isReplaying ? <Loader2 className="animate-spin" /> : <RefreshCw />} Replay same snapshot</Button>
              <Button variant="outline" onClick={onRunCurrent} disabled={isReplaying || isRunningCurrent}>{isRunningCurrent ? <Loader2 className="animate-spin" /> : <RefreshCw />} Run with current strategy/data</Button>
            </div>
            {actionError ? <p className="text-sm text-destructive">{actionError}</p> : null}
          </CardContent>
        </Card>
      );
    case "inconsistent":
      return <Card className="border-destructive"><CardContent className="pt-6 text-sm" role="alert">The persisted job returned an incomplete terminal contract: {state.reason}.</CardContent></Card>;
    case "completed":
    case "completed_no_trades":
      return null;
  }
}
