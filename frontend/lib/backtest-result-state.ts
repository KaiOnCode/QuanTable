import type {
  BacktestFrequency,
  BacktestMode as BacktestModeContract,
} from "./types/models";

export type BacktestMode = BacktestModeContract;

export type BacktestFrequencySelection = {
  readonly strategyId: string;
  readonly frequency: BacktestFrequency;
};

export type BacktestEligibility =
  | {
      readonly kind: "eligible";
      readonly mode: BacktestMode;
      readonly providerCheck: "not_required" | "unknown_at_submit";
    }
  | {
      readonly kind: "ineligible";
      readonly code:
        | "agent_model_missing"
        | "strategy_config_invalid"
        | "strategy_inactive"
        | "strategy_not_backtestable"
        | "strategy_type_unsupported"
        | "ticker_not_allowed";
    };

export type BacktestStrategyInput = {
  readonly type: "agent" | "quant" | "hitl";
  readonly status: string;
  readonly tickers: readonly string[];
  readonly beliefs: readonly string[];
  readonly agent_model: string;
  readonly quant_strategy_name: string | null;
  readonly quant_params: Readonly<Record<string, unknown>>;
  readonly execution_frequency: string;
  readonly initial_capital: number;
  readonly max_position_pct: number;
  readonly max_drawdown_pct: number;
};

type BacktestProgressInput = {
  readonly bars_total: number;
  readonly bars_processed: number;
  readonly decisions_total: number;
  readonly decisions_completed: number;
  readonly current_decision_date: string | null;
};

type BacktestNoTradeReasonInput = {
  readonly code: "no_signals" | "not_ready" | "all_hold" | "all_rejected";
  readonly count: number;
};

type BacktestResultInput = {
  readonly outcome: "completed" | "completed_no_trades";
  readonly warnings: readonly string[];
  readonly no_trade_reasons: readonly BacktestNoTradeReasonInput[];
};

type BacktestErrorInput = {
  readonly code: string;
  readonly stage: string | null;
  readonly decision_date: string | null;
  readonly attempt: number | null;
  readonly message: string;
};

export type BacktestJobInput = {
  readonly status: "pending" | "running" | "completed" | "failed";
  readonly config: { readonly mode: BacktestMode } | null;
  readonly progress: BacktestProgressInput;
  readonly result: BacktestResultInput | null;
  readonly error: BacktestErrorInput | null;
};

export type BacktestJobDisplayState =
  | {
      readonly kind: "running";
      readonly status: "pending" | "running";
      readonly barsProcessed: number;
      readonly barsTotal: number;
      readonly decisionsCompleted: number;
      readonly decisionsTotal: number;
      readonly currentDecisionDate: string | null;
    }
  | {
      readonly kind: "failed";
      readonly error: {
        readonly code: string;
        readonly stage: string | null;
        readonly decisionDate: string | null;
        readonly attempt: number | null;
        readonly message: string;
      };
    }
  | {
      readonly kind: "completed";
      readonly warnings: readonly string[];
      readonly isExperimental: boolean;
    }
  | {
      readonly kind: "completed_no_trades";
      readonly warnings: readonly string[];
      readonly noTradeReasons: readonly BacktestNoTradeReasonInput[];
      readonly observedCauseState: "reported" | "not_exposed";
      readonly performanceTrust: "not_trusted";
      readonly isExperimental: boolean;
    }
  | {
      readonly kind: "inconsistent";
      readonly reason: "missing_failure_error" | "missing_terminal_result";
    };

const VALID_FREQUENCIES = ["daily", "weekly", "monthly"] as const;

export function syncBacktestFrequencySelection(
  current: BacktestFrequencySelection,
  strategy: (BacktestStrategyInput & { readonly id: string }) | undefined,
): BacktestFrequencySelection {
  if (strategy === undefined || strategy.id === current.strategyId) {
    return current;
  }
  const frequency = hasValidFrequency(strategy.execution_frequency)
    ? strategy.execution_frequency
    : "daily";
  return { strategyId: strategy.id, frequency };
}

function isFiniteNumber(value: number): boolean {
  return Number.isFinite(value);
}

function hasValidFrequency(value: string): value is BacktestFrequency {
  return VALID_FREQUENCIES.some((frequency) => frequency === value);
}

function hasValidSharedConfiguration(strategy: BacktestStrategyInput): boolean {
  return (
    strategy.tickers.length > 0 &&
    strategy.tickers.every((ticker) => /^[A-Z][A-Z0-9.-]{0,14}$/.test(ticker)) &&
    hasValidFrequency(strategy.execution_frequency) &&
    isFiniteNumber(strategy.initial_capital) &&
    strategy.initial_capital > 0 &&
    isFiniteNumber(strategy.max_position_pct) &&
    strategy.max_position_pct > 0 &&
    strategy.max_position_pct <= 100 &&
    isFiniteNumber(strategy.max_drawdown_pct) &&
    strategy.max_drawdown_pct > 0 &&
    strategy.max_drawdown_pct <= 100
  );
}

function finiteIntegerInRange(
  value: unknown,
  minimum: number,
  maximum: number,
): boolean {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    Number.isFinite(value) &&
    value >= minimum &&
    value <= maximum
  );
}

function finiteNumberInRange(
  value: unknown,
  minimum: number,
  maximum: number,
): boolean {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= minimum &&
    value <= maximum
  );
}

function hasExactKeys(
  params: Readonly<Record<string, unknown>>,
  expectedKeys: readonly string[],
): boolean {
  return (
    Object.keys(params).length === expectedKeys.length &&
    expectedKeys.every((key) => Object.hasOwn(params, key))
  );
}

function hasSupportedQuantPolicy(strategy: BacktestStrategyInput): boolean {
  const params = strategy.quant_params;
  const target = params.target_position_pct;
  if (!finiteNumberInRange(target, 0, strategy.max_position_pct)) {
    return false;
  }
  switch (strategy.quant_strategy_name) {
    case "momentum": {
      const entryThreshold = params.entry_threshold;
      const exitThreshold = params.exit_threshold;
      return (
        hasExactKeys(params, [
          "lookback_bars",
          "entry_threshold",
          "exit_threshold",
          "target_position_pct",
        ]) &&
        finiteIntegerInRange(params.lookback_bars, 2, 252) &&
        finiteNumberInRange(entryThreshold, Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY) &&
        finiteNumberInRange(exitThreshold, Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY) &&
        typeof entryThreshold === "number" &&
        typeof exitThreshold === "number" &&
        exitThreshold <= entryThreshold
      );
    }
    case "sma_crossover":
      return (
        hasExactKeys(params, [
          "fast_window",
          "slow_window",
          "target_position_pct",
        ]) &&
        finiteIntegerInRange(params.fast_window, 2, 100) &&
        finiteIntegerInRange(params.slow_window, 3, 252) &&
        typeof params.fast_window === "number" &&
        typeof params.slow_window === "number" &&
        params.slow_window > params.fast_window
      );
    case null:
      return false;
    default:
      return false;
  }
}

export function backtestModeForStrategy(
  strategy: BacktestStrategyInput | undefined,
): BacktestMode | null {
  if (strategy === undefined) {
    return null;
  }
  switch (strategy.type) {
    case "quant":
      return "deterministic";
    case "agent":
      return "agent_experiment";
    case "hitl":
      return null;
  }
}

export function deriveBacktestEligibility(
  strategy: BacktestStrategyInput | undefined,
  ticker: string,
): BacktestEligibility {
  if (strategy === undefined) {
    return { kind: "ineligible", code: "strategy_not_backtestable" };
  }
  if (strategy.status !== "active") {
    return { kind: "ineligible", code: "strategy_inactive" };
  }
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!strategy.tickers.includes(normalizedTicker)) {
    return { kind: "ineligible", code: "ticker_not_allowed" };
  }
  if (!hasValidSharedConfiguration(strategy)) {
    return { kind: "ineligible", code: "strategy_config_invalid" };
  }
  switch (strategy.type) {
    case "quant":
      return hasSupportedQuantPolicy(strategy)
        ? {
            kind: "eligible",
            mode: "deterministic",
            providerCheck: "not_required",
          }
        : { kind: "ineligible", code: "strategy_config_invalid" };
    case "agent":
      return strategy.agent_model.trim().length > 0
        ? {
            kind: "eligible",
            mode: "agent_experiment",
            providerCheck: "unknown_at_submit",
          }
        : { kind: "ineligible", code: "agent_model_missing" };
    case "hitl":
      return { kind: "ineligible", code: "strategy_type_unsupported" };
  }
}

export function displayBacktestIdentifier(value: string): string {
  return value || "unavailable";
}

export function backtestExecutionTimingLabel(value: string): string {
  return value === "next_open"
    ? "Signal at close, fill next open"
    : "Unsupported legacy timing; canonical v1 uses next open";
}

function runningState(
  status: "pending" | "running",
  progress: BacktestProgressInput,
): BacktestJobDisplayState {
  return {
    kind: "running",
    status,
    barsProcessed: progress.bars_processed,
    barsTotal: progress.bars_total,
    decisionsCompleted: progress.decisions_completed,
    decisionsTotal: progress.decisions_total,
    currentDecisionDate: progress.current_decision_date,
  };
}

export function deriveBacktestJobState(
  job: BacktestJobInput,
): BacktestJobDisplayState {
  switch (job.status) {
    case "pending":
    case "running":
      return runningState(job.status, job.progress);
    case "failed":
      return job.error === null
        ? { kind: "inconsistent", reason: "missing_failure_error" }
        : {
            kind: "failed",
            error: {
              code: job.error.code,
              stage: job.error.stage,
              decisionDate: job.error.decision_date,
              attempt: job.error.attempt,
              message: job.error.message,
            },
          };
    case "completed":
      if (job.result === null) {
        return { kind: "inconsistent", reason: "missing_terminal_result" };
      }
      switch (job.result.outcome) {
        case "completed":
          return {
            kind: "completed",
            warnings: job.result.warnings,
            isExperimental: job.config?.mode === "agent_experiment",
          };
        case "completed_no_trades":
          return {
            kind: "completed_no_trades",
            warnings: job.result.warnings,
            noTradeReasons: job.result.no_trade_reasons,
            observedCauseState:
              job.result.no_trade_reasons.length > 0
                ? "reported"
                : "not_exposed",
            performanceTrust: "not_trusted",
            isExperimental: job.config?.mode === "agent_experiment",
          };
      }
  }
}
