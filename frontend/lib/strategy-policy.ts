export const QUANT_RULES = ["momentum", "sma_crossover"] as const;

export type QuantRule = (typeof QUANT_RULES)[number];

export type QuantPolicyDraft = {
  readonly rule: QuantRule;
  readonly momentum: {
    readonly lookbackBars: string;
    readonly entryThreshold: string;
    readonly exitThreshold: string;
    readonly targetPositionPct: string;
  };
  readonly smaCrossover: {
    readonly fastWindow: string;
    readonly slowWindow: string;
    readonly targetPositionPct: string;
  };
};

export type QuantPolicyPayload =
  | {
      readonly quant_strategy_name: "momentum";
      readonly quant_params: {
        readonly lookback_bars: number;
        readonly entry_threshold: number;
        readonly exit_threshold: number;
        readonly target_position_pct: number;
      };
    }
  | {
      readonly quant_strategy_name: "sma_crossover";
      readonly quant_params: {
        readonly fast_window: number;
        readonly slow_window: number;
        readonly target_position_pct: number;
      };
    };

export type QuantPolicyValidation =
  | { readonly ok: true; readonly payload: QuantPolicyPayload }
  | { readonly ok: false; readonly errors: Readonly<Record<string, string>> };

export const DEFAULT_QUANT_POLICY_DRAFT: QuantPolicyDraft = {
  rule: "momentum",
  momentum: {
    lookbackBars: "20",
    entryThreshold: "0.05",
    exitThreshold: "0",
    targetPositionPct: "80",
  },
  smaCrossover: {
    fastWindow: "20",
    slowWindow: "50",
    targetPositionPct: "80",
  },
};

function finiteNumber(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function boundedNumber(
  errors: Record<string, string>,
  key: string,
  value: string,
  minimum: number,
  maximum: number,
  integer: boolean,
): number | null {
  const parsed = finiteNumber(value);
  if (parsed === null || parsed < minimum || parsed > maximum || (integer && !Number.isInteger(parsed))) {
    errors[key] = integer
      ? `Enter a whole number from ${minimum} to ${maximum}.`
      : `Enter a number from ${minimum} to ${maximum}.`;
    return null;
  }
  return parsed;
}

export function validateQuantPolicyDraft(
  draft: QuantPolicyDraft,
  maximumPositionPct = 100,
): QuantPolicyValidation {
  const errors: Record<string, string> = {};
  switch (draft.rule) {
    case "momentum": {
      const lookback = boundedNumber(errors, "lookbackBars", draft.momentum.lookbackBars, 2, 252, true);
      const entry = finiteNumber(draft.momentum.entryThreshold);
      const exit = finiteNumber(draft.momentum.exitThreshold);
      const target = boundedNumber(errors, "targetPositionPct", draft.momentum.targetPositionPct, 0, maximumPositionPct, false);
      if (entry === null) errors.entryThreshold = "Enter a finite entry threshold.";
      if (exit === null) errors.exitThreshold = "Enter a finite exit threshold.";
      if (entry !== null && exit !== null && exit > entry) {
        errors.exitThreshold = "Exit threshold must not exceed entry threshold.";
      }
      if (lookback === null || entry === null || exit === null || target === null || Object.keys(errors).length > 0) {
        return { ok: false, errors };
      }
      return {
        ok: true,
        payload: {
          quant_strategy_name: "momentum",
          quant_params: { lookback_bars: lookback, entry_threshold: entry, exit_threshold: exit, target_position_pct: target },
        },
      };
    }
    case "sma_crossover": {
      const fast = boundedNumber(errors, "fastWindow", draft.smaCrossover.fastWindow, 2, 100, true);
      const slow = boundedNumber(errors, "slowWindow", draft.smaCrossover.slowWindow, 3, 252, true);
      const target = boundedNumber(errors, "targetPositionPct", draft.smaCrossover.targetPositionPct, 0, maximumPositionPct, false);
      if (fast !== null && slow !== null && slow <= fast) {
        errors.slowWindow = "Slow window must exceed fast window.";
      }
      if (fast === null || slow === null || target === null || Object.keys(errors).length > 0) {
        return { ok: false, errors };
      }
      return {
        ok: true,
        payload: {
          quant_strategy_name: "sma_crossover",
          quant_params: { fast_window: fast, slow_window: slow, target_position_pct: target },
        },
      };
    }
  }
}

export function quantPolicyDraftFromStored(
  rule: string | null,
  params: Readonly<Record<string, unknown>>,
): QuantPolicyDraft {
  const base = DEFAULT_QUANT_POLICY_DRAFT;
  if (rule === "sma_crossover") {
    return {
      ...base,
      rule,
      smaCrossover: {
        fastWindow: typeof params.fast_window === "number" ? String(params.fast_window) : base.smaCrossover.fastWindow,
        slowWindow: typeof params.slow_window === "number" ? String(params.slow_window) : base.smaCrossover.slowWindow,
        targetPositionPct: typeof params.target_position_pct === "number" ? String(params.target_position_pct) : base.smaCrossover.targetPositionPct,
      },
    };
  }
  return {
    ...base,
    momentum: {
      lookbackBars: typeof params.lookback_bars === "number" ? String(params.lookback_bars) : base.momentum.lookbackBars,
      entryThreshold: typeof params.entry_threshold === "number" ? String(params.entry_threshold) : base.momentum.entryThreshold,
      exitThreshold: typeof params.exit_threshold === "number" ? String(params.exit_threshold) : base.momentum.exitThreshold,
      targetPositionPct: typeof params.target_position_pct === "number" ? String(params.target_position_pct) : base.momentum.targetPositionPct,
    },
  };
}
