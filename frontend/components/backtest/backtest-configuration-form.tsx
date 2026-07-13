import type { BacktestMode, BacktestRequest, StrategyConfig } from "@/lib/types/models";
import type { BacktestEligibility } from "@/lib/backtest-result-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { formatCurrency } from "@/lib/utils";
import { Loader2, Play } from "lucide-react";

type BacktestConfigurationFormProps = {
  readonly strategies: readonly StrategyConfig[];
  readonly selectedStrategyId: string;
  readonly selectedStrategy: StrategyConfig | undefined;
  readonly ticker: string;
  readonly dateFrom: string;
  readonly dateTo: string;
  readonly frequency: BacktestRequest["frequency"];
  readonly benchmark: string;
  readonly mode: BacktestMode | null;
  readonly eligibility: BacktestEligibility;
  readonly isLoadingStrategies: boolean;
  readonly isSubmitting: boolean;
  readonly strategyError: string | null;
  readonly onStrategyChange: (strategyId: string) => void;
  readonly onTickerChange: (ticker: string) => void;
  readonly onDateFromChange: (date: string) => void;
  readonly onDateToChange: (date: string) => void;
  readonly onFrequencyChange: (frequency: BacktestRequest["frequency"]) => void;
  readonly onBenchmarkChange: (benchmark: string) => void;
  readonly onSubmit: () => void;
};

function modeLabel(mode: BacktestMode): string {
  switch (mode) {
    case "deterministic":
      return "Deterministic quant";
    case "agent_experiment":
      return "Agent experiment";
  }
}

export function backtestEligibilityMessage(eligibility: BacktestEligibility): string {
  switch (eligibility.kind) {
    case "eligible":
      return eligibility.providerCheck === "not_required"
        ? "Deterministic execution does not require an LLM credential."
        : "Experimental and provider-dependent. Capability is checked when you run, and this is not canonical performance.";
    case "ineligible":
      switch (eligibility.code) {
        case "agent_model_missing":
          return "Agent experiment requires a configured agent model.";
        case "strategy_config_invalid":
          return "This strategy has an incomplete or unsupported backtest configuration.";
        case "strategy_inactive":
          return "Activate this strategy before starting a historical backtest.";
        case "strategy_not_backtestable":
          return "Select a persisted backtestable strategy before running.";
        case "strategy_type_unsupported":
          return "Historical backtests are unsupported for HITL strategies.";
        case "ticker_not_allowed":
          return "The selected ticker is not allowed by this strategy.";
      }
  }
}

function parseFrequency(value: string): BacktestRequest["frequency"] | null {
  switch (value) {
    case "daily":
    case "weekly":
    case "monthly":
      return value;
    default:
      return null;
  }
}

export function BacktestConfigurationForm({
  strategies,
  selectedStrategyId,
  selectedStrategy,
  ticker,
  dateFrom,
  dateTo,
  frequency,
  benchmark,
  mode,
  eligibility,
  isLoadingStrategies,
  isSubmitting,
  strategyError,
  onStrategyChange,
  onTickerChange,
  onDateFromChange,
  onDateToChange,
  onFrequencyChange,
  onBenchmarkChange,
  onSubmit,
}: BacktestConfigurationFormProps) {
  const canSubmit = eligibility.kind === "eligible" && !isSubmitting;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Configuration</CardTitle>
        <CardDescription>
          The server freezes strategy policy, historical data, execution timing, and costs before accepting a job.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="min-w-0 space-y-2">
              <Label htmlFor="backtest-strategy">Strategy</Label>
              <Select
                value={selectedStrategyId}
                onValueChange={(value) => {
                  if (value) onStrategyChange(value);
                }}
                disabled={isLoadingStrategies || strategyError !== null || strategies.length === 0}
              >
                <SelectTrigger id="backtest-strategy" aria-label="Strategy" className="max-w-full">
                  <span className="grid min-w-0 text-left">
                    {strategies.map((strategy) => (
                      <span
                        key={strategy.id}
                        aria-hidden
                        className="invisible col-start-1 row-start-1 whitespace-nowrap"
                      >
                        {strategy.name}
                      </span>
                    ))}
                    <span className="col-start-1 row-start-1 truncate">
                      {selectedStrategy?.name ?? (isLoadingStrategies ? "Loading strategies" : "Select strategy")}
                    </span>
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {strategies.map((strategy) => (
                    <SelectItem key={strategy.id} value={strategy.id}>
                      {strategy.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {selectedStrategy ? (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">{selectedStrategy.type}</Badge>
                  <Badge variant="secondary">{selectedStrategy.status}</Badge>
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label htmlFor="backtest-ticker">Ticker</Label>
              <Input
                id="backtest-ticker"
                value={ticker}
                onChange={(event) => onTickerChange(event.target.value.toUpperCase())}
                placeholder="AAPL"
                autoCapitalize="characters"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="backtest-date-from">Date From</Label>
              <Input id="backtest-date-from" type="date" value={dateFrom} onChange={(event) => onDateFromChange(event.target.value)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="backtest-date-to">Date To</Label>
              <Input id="backtest-date-to" type="date" value={dateTo} onChange={(event) => onDateToChange(event.target.value)} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="backtest-frequency">Rebalance Cadence</Label>
              <Select
                value={frequency}
                onValueChange={(value) => {
                  const nextFrequency = parseFrequency(value ?? "");
                  if (nextFrequency) onFrequencyChange(nextFrequency);
                }}
              >
                <SelectTrigger id="backtest-frequency">{frequency}</SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="backtest-benchmark">Benchmark</Label>
              <Input
                id="backtest-benchmark"
                value={benchmark}
                onChange={(event) => onBenchmarkChange(event.target.value.toUpperCase())}
                placeholder="SPY"
                autoCapitalize="characters"
              />
            </div>

            <div className="space-y-2 md:col-span-2">
              <Label>Mode</Label>
              {mode === null ? (
                <p className="rounded-lg border border-input px-3 py-2 text-sm text-muted-foreground">
                  Historical backtest mode is unavailable for this strategy type.
                </p>
              ) : (
                <RadioGroup
                  value={mode}
                  disabled
                  aria-label="Backtest mode"
                  className="grid-cols-1"
                >
                  <Label htmlFor={`backtest-mode-${mode}`} className="flex items-start gap-3 rounded-lg border border-input p-3">
                    <RadioGroupItem id={`backtest-mode-${mode}`} value={mode} />
                    <span className="space-y-1">
                      <span className="block text-sm font-medium">{modeLabel(mode)}</span>
                      <span className="block text-xs font-normal text-muted-foreground">{backtestEligibilityMessage(eligibility)}</span>
                    </span>
                  </Label>
                </RadioGroup>
              )}
            </div>
          </div>

          {selectedStrategy ? (
            <dl className="grid grid-cols-1 gap-3 rounded-lg border border-input p-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <div><dt className="text-xs text-muted-foreground">Signal and fill timing</dt><dd className="mt-1">Signal at close, fill next open</dd></div>
              <div><dt className="text-xs text-muted-foreground">Market-data treatment</dt><dd className="mt-1">Provider-adjusted prices</dd></div>
              <div><dt className="text-xs text-muted-foreground">Execution costs</dt><dd className="mt-1">10 bps commission + 5 bps slippage</dd></div>
              <div><dt className="text-xs text-muted-foreground">Initial capital</dt><dd className="mt-1 font-mono">{formatCurrency(selectedStrategy.initial_capital)}</dd></div>
            </dl>
          ) : null}

          {strategies.length === 0 && !isLoadingStrategies && strategyError === null ? <p className="text-sm text-muted-foreground">Create a strategy before starting a backtest.</p> : null}

          <Button className="w-full sm:w-auto" type="submit" disabled={!canSubmit}>
            {isSubmitting ? <Loader2 className="animate-spin" /> : <Play />}
            Run with current strategy/data
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
