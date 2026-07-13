"use client";

import { Suspense, useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { BacktestConfigurationForm } from "@/components/backtest/backtest-configuration-form";
import { BacktestJobState } from "@/components/backtest/backtest-job-state";
import { BacktestResultSurface } from "@/components/backtest/backtest-result-surface";
import { Shell } from "@/components/layout/shell";
import { backtestApi } from "@/lib/api/backtest";
import { strategiesApi } from "@/lib/api/strategies";
import { displayBacktestError, isBacktestNotFoundError } from "@/lib/backtest-api-error";
import { backtestModeForStrategy, deriveBacktestEligibility, syncBacktestFrequencySelection } from "@/lib/backtest-result-state";
import type { BacktestRequest } from "@/lib/types/models";
import { usePersistedBacktestId } from "@/lib/use-persisted-backtest-id";
import { LineChart } from "lucide-react";

const DEFAULT_DATE_FROM = "2024-01-02";
const DEFAULT_DATE_TO = "2024-03-29";

function messageFor(error: unknown): string {
  return displayBacktestError(error);
}

function BacktestContent() {
  const searchParams = useSearchParams();
  const [strategyId, setStrategyId] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [dateFrom, setDateFrom] = useState(DEFAULT_DATE_FROM);
  const [dateTo, setDateTo] = useState(DEFAULT_DATE_TO);
  const [frequencySelection, setFrequencySelection] = useState({
    strategyId: "",
    frequency: "daily" as BacktestRequest["frequency"],
  });
  const [benchmark, setBenchmark] = useState("SPY");
  const [validationError, setValidationError] = useState<string | null>(null);
  const { backtestId, isRestored, persistBacktestId, syncBacktestStatus } = usePersistedBacktestId(searchParams.get("backtest_id"));

  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list(),
  });
  const strategies = strategiesQuery.data?.items ?? [];
  const selectedStrategy = strategies.find((strategy) => strategy.id === strategyId) ?? strategies[0];
  const selectedStrategyId = selectedStrategy?.id ?? "";
  const mode = backtestModeForStrategy(selectedStrategy);
  const eligibility = deriveBacktestEligibility(selectedStrategy, ticker);
  const frequency = frequencySelection.frequency;

  useEffect(() => {
    setFrequencySelection((current) =>
      syncBacktestFrequencySelection(current, selectedStrategy),
    );
  }, [selectedStrategy]);

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
      syncBacktestStatus(job.id, job.status);
    } else if (backtestId && isBacktestNotFoundError(jobQuery.error)) {
      syncBacktestStatus(backtestId, "not_found");
    }
  }, [backtestId, job, jobQuery.error, syncBacktestStatus]);

  const runMutation = useMutation({
    mutationFn: (request: BacktestRequest) => backtestApi.create(request),
    onSuccess: (accepted) => {
      setValidationError(null);
      persistBacktestId(accepted.id, accepted.status);
    },
  });
  const replayMutation = useMutation({
    mutationFn: (sourceId: string) => backtestApi.replay(sourceId),
    onSuccess: (accepted) => {
      setValidationError(null);
      persistBacktestId(accepted.id, accepted.status);
    },
  });

  const selectStrategy = (nextStrategyId: string) => {
    setValidationError(null);
    runMutation.reset();
    replayMutation.reset();
    setStrategyId(nextStrategyId);
  };

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
    if (eligibility.kind !== "eligible") {
      setValidationError("Resolve the strategy eligibility requirements before running this backtest.");
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
      mode: eligibility.mode,
    });
  };

  const completedJob = job?.status === "completed" && job.result !== null && job.config !== null ? job : null;
  const strategyError = strategiesQuery.isError ? `Failed to load strategies: ${messageFor(strategiesQuery.error)}` : null;
  const requestError = runMutation.isError ? messageFor(runMutation.error) : null;
  const actionError = replayMutation.isError ? messageFor(replayMutation.error) : requestError;

  return (
    <Shell>
      <main className="space-y-6 p-4 sm:p-6">
        <header>
          <h2 className="flex items-center gap-2 text-lg font-semibold"><LineChart className="h-5 w-5" /> Backtest</h2>
          <p className="text-sm text-muted-foreground">Run one persisted strategy against a single historical ticker and independent benchmark.</p>
        </header>

        <BacktestConfigurationForm
          strategies={strategies}
          selectedStrategyId={selectedStrategyId}
          selectedStrategy={selectedStrategy}
          ticker={ticker}
          dateFrom={dateFrom}
          dateTo={dateTo}
          frequency={frequency}
          benchmark={benchmark}
          mode={mode}
          eligibility={eligibility}
          isLoadingStrategies={strategiesQuery.isLoading}
          isSubmitting={runMutation.isPending}
          validationError={validationError}
          strategyError={strategyError}
          requestError={requestError}
          onStrategyChange={selectStrategy}
          onTickerChange={setTicker}
          onDateFromChange={setDateFrom}
          onDateToChange={setDateTo}
          onFrequencyChange={(nextFrequency) =>
            setFrequencySelection((current) => ({
              ...current,
              frequency: nextFrequency,
            }))
          }
          onBenchmarkChange={setBenchmark}
          onSubmit={submit}
        />

        <BacktestJobState
          backtestId={backtestId}
          job={job}
          isRestored={isRestored}
          isLoading={jobQuery.isLoading}
          loadError={jobQuery.isError ? messageFor(jobQuery.error) : null}
          actionError={actionError}
          isReplaying={replayMutation.isPending}
          isRunningCurrent={runMutation.isPending}
          onReplay={(sourceId) => replayMutation.mutate(sourceId)}
          onRunCurrent={submit}
        />

        {completedJob ? <BacktestResultSurface job={completedJob} /> : null}
      </main>
    </Shell>
  );
}

export default function BacktestPage() {
  return <Suspense fallback={<Shell><div className="p-6 text-sm text-muted-foreground">Loading backtest…</div></Shell>}><BacktestContent /></Suspense>;
}
