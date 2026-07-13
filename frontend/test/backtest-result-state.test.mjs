import assert from "node:assert/strict";
import test from "node:test";

import {
  backtestModeForStrategy,
  backtestExecutionTimingLabel,
  displayBacktestIdentifier,
  deriveBacktestEligibility,
  deriveBacktestJobState,
  syncBacktestFrequencySelection,
} from "../lib/backtest-result-state.ts";

const VALID_QUANT_STRATEGY = {
  id: "quant-a",
  type: "quant",
  status: "active",
  tickers: ["AAPL"],
  beliefs: ["Preserve capital"],
  agent_model: "",
  quant_strategy_name: "momentum",
  quant_params: {
    lookback_bars: 20,
    entry_threshold: 0.05,
    exit_threshold: 0,
    target_position_pct: 80,
  },
  execution_frequency: "daily",
  initial_capital: 100000,
  max_position_pct: 100,
  max_drawdown_pct: 20,
};

test("resets frequency from a newly selected strategy and preserves same-strategy override", () => {
  // Given: the user overrode a daily strategy to monthly.
  const overridden = { strategyId: "quant-a", frequency: "monthly" };

  // When: data refreshes for the same strategy, then selection changes to weekly.
  const preserved = syncBacktestFrequencySelection(overridden, VALID_QUANT_STRATEGY);
  const reset = syncBacktestFrequencySelection(preserved, {
    ...VALID_QUANT_STRATEGY,
    id: "quant-b",
    execution_frequency: "weekly",
  });

  // Then: refresh preserves the override, while selection change resets to its default.
  assert.deepEqual(preserved, overridden);
  assert.deepEqual(reset, { strategyId: "quant-b", frequency: "weekly" });
});

function jobWith(overrides) {
  return {
    id: "0123456789abcdef0123456789abcdef",
    status: "completed",
    request: null,
    config: {
      mode: "deterministic",
    },
    progress: {
      bars_total: 8,
      bars_processed: 5,
      decisions_total: 4,
      decisions_eligible: 4,
      decisions_not_ready: 0,
      decisions_completed: 3,
      current_decision_date: "2024-01-08T00:00:00Z",
    },
    decisions: [],
    result: null,
    error: null,
    created_at: "2024-01-02T00:00:00Z",
    updated_at: "2024-01-08T00:00:00Z",
    ...overrides,
  };
}

test("selects deterministic mode for an eligible quant strategy", () => {
  // Given: an active quant strategy with a supported policy and ticker.
  const strategy = VALID_QUANT_STRATEGY;

  // When: the backtest form derives its mode and local eligibility.
  const mode = backtestModeForStrategy(strategy);
  const eligibility = deriveBacktestEligibility(strategy, "AAPL");

  // Then: it is deterministic and requires no LLM/provider check.
  assert.equal(mode, "deterministic");
  assert.deepEqual(eligibility, {
    kind: "eligible",
    mode: "deterministic",
    providerCheck: "not_required",
  });
});

test("allows an otherwise valid deterministic quant strategy with empty beliefs", () => {
  // Given: the backend-supported default strategy shape with no discretionary beliefs.
  const strategy = { ...VALID_QUANT_STRATEGY, beliefs: [] };

  // When: the frontend derives whether the frozen deterministic policy can run.
  const eligibility = deriveBacktestEligibility(strategy, "AAPL");

  // Then: it matches the backend contract and remains runnable without an LLM.
  assert.deepEqual(eligibility, {
    kind: "eligible",
    mode: "deterministic",
    providerCheck: "not_required",
  });
});

test("keeps complete reproducibility identifiers available for rendering", () => {
  const identifier = "a".repeat(64);

  assert.equal(displayBacktestIdentifier(identifier), identifier);
  assert.equal(displayBacktestIdentifier(""), "unavailable");
});

test("never labels a non-v1 timing value as a same-bar fill", () => {
  assert.equal(
    backtestExecutionTimingLabel("next_open"),
    "Signal at close, fill next open",
  );
  assert.equal(
    backtestExecutionTimingLabel("close_bar"),
    "Unsupported legacy timing; canonical v1 uses next open",
  );
});

test("selects the experimental mode only for an eligible agent strategy", () => {
  // Given: an active agent strategy with a configured model.
  const strategy = {
    ...VALID_QUANT_STRATEGY,
    id: "agent-a",
    type: "agent",
    agent_model: "gpt-5.6-sol",
    quant_strategy_name: null,
    quant_params: {},
  };

  // When: the form derives agent eligibility without contacting a provider.
  const mode = backtestModeForStrategy(strategy);
  const eligibility = deriveBacktestEligibility(strategy, "AAPL");

  // Then: it is explicitly experimental and provider status remains unknown at submit.
  assert.equal(mode, "agent_experiment");
  assert.deepEqual(eligibility, {
    kind: "eligible",
    mode: "agent_experiment",
    providerCheck: "unknown_at_submit",
  });
});

test("disables historical backtests for HITL strategies", () => {
  // Given: a persisted HITL strategy.
  const strategy = { ...VALID_QUANT_STRATEGY, id: "hitl-a", type: "hitl" };

  // When: the form derives the selectable historical backtest mode.
  const mode = backtestModeForStrategy(strategy);
  const eligibility = deriveBacktestEligibility(strategy, "AAPL");

  // Then: no stale mode is retained and Run remains disabled with a typed cause.
  assert.equal(mode, null);
  assert.deepEqual(eligibility, {
    kind: "ineligible",
    code: "strategy_type_unsupported",
  });
});

test("reports durable running progress from the backend job", () => {
  // Given: a running persisted job with worker progress.
  const job = jobWith({ status: "running" });

  // When: the result surface derives its display state.
  const state = deriveBacktestJobState(job);

  // Then: decision counts and the backend date remain visible without recomputation.
  assert.deepEqual(state, {
    kind: "running",
    status: "running",
    barsProcessed: 5,
    barsTotal: 8,
    decisionsCompleted: 3,
    decisionsTotal: 4,
    currentDecisionDate: "2024-01-08T00:00:00Z",
  });
});

test("preserves observed no-trade causes as untrusted performance", () => {
  // Given: a completed job whose result reports observed no-signal and hold causes.
  const job = jobWith({
    result: {
      outcome: "completed_no_trades",
      warnings: ["completed_with_no_trades_not_trusted_performance"],
      no_trade_reasons: [
        { code: "no_signals", count: 1 },
        { code: "all_hold", count: 3 },
      ],
    },
  });

  // When: the result surface derives its terminal presentation state.
  const state = deriveBacktestJobState(job);

  // Then: it keeps only server-observed causes and marks performance untrusted.
  assert.deepEqual(state, {
    kind: "completed_no_trades",
    warnings: ["completed_with_no_trades_not_trusted_performance"],
    noTradeReasons: [
      { code: "no_signals", count: 1 },
      { code: "all_hold", count: 3 },
    ],
    observedCauseState: "reported",
    performanceTrust: "not_trusted",
    isExperimental: false,
  });
});

test("does not infer no-trade causes absent from the public result", () => {
  // Given: a completed-no-trades result with no observed cause exposed by the API.
  const job = jobWith({
    result: {
      outcome: "completed_no_trades",
      warnings: ["completed_with_no_trades_not_trusted_performance"],
      no_trade_reasons: [],
    },
  });

  // When: the result surface derives its terminal presentation state.
  const state = deriveBacktestJobState(job);

  // Then: it reports the absence instead of inventing HOLD or rejection reasons.
  assert.deepEqual(state, {
    kind: "completed_no_trades",
    warnings: ["completed_with_no_trades_not_trusted_performance"],
    noTradeReasons: [],
    observedCauseState: "not_exposed",
    performanceTrust: "not_trusted",
    isExperimental: false,
  });
});

test("exposes only typed safe failure metadata", () => {
  // Given: a failed durable job with a safe worker error.
  const job = jobWith({
    status: "failed",
    error: {
      code: "execution_failed",
      stage: "execution",
      decision_date: "2024-01-08T00:00:00Z",
      attempt: 2,
      message: "Execution failed safely",
    },
  });

  // When: the result surface derives its failure state.
  const state = deriveBacktestJobState(job);

  // Then: the UI receives only the contractual diagnostic fields.
  assert.deepEqual(state, {
    kind: "failed",
    error: {
      code: "execution_failed",
      stage: "execution",
      decisionDate: "2024-01-08T00:00:00Z",
      attempt: 2,
      message: "Execution failed safely",
    },
  });
});
