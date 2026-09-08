import { DEFAULT_DEEP_THINK_MODEL, DEFAULT_QUICK_THINK_MODEL } from "@/lib/llm-defaults";
import type { QuantPolicyValidation } from "@/lib/strategy-policy";
import type { CreateStrategyRequest, StrategyType } from "@/lib/types/models";

type DraftBasics = {
  readonly name: string;
  readonly description: string;
  readonly type: StrategyType;
  readonly tickers: readonly string[];
};

export function buildCreateStrategyRequest(
  basics: DraftBasics,
  policy: QuantPolicyValidation,
): CreateStrategyRequest | null {
  if (basics.type === "quant" && !policy.ok) return null;
  const quant = basics.type === "quant" && policy.ok
    ? policy.payload
    : { quant_strategy_name: null, quant_params: {} };
  return {
    ...basics,
    tickers: [...basics.tickers],
    active_agents: ["market", "news", "fundamentals", "pm"],
    debate_rounds: 2,
    beliefs: [],
    belief_weights: {},
    risk_debate_rounds: 2,
    agent_model: DEFAULT_QUICK_THINK_MODEL,
    deep_think_model: DEFAULT_DEEP_THINK_MODEL,
    agent_temperature: 0,
    enable_debate_mode: true,
    enable_cross_review: false,
    ...quant,
    alpha_zoo_factors: [],
    execution_frequency: "daily",
    execution_time: "09:30",
    initial_capital: 100000,
    max_position_pct: 80,
    max_drawdown_pct: 100,
    hitl_enabled: false,
    hitl_trigger_position_change_pct: 20,
    hitl_trigger_signal_conflict: true,
    hitl_trigger_confidence_below: 0.6,
    hitl_timeout_hours: 2,
    memory_enabled: true,
    memory_recall_limit: 5,
    weekly_reflection: true,
    tags: [],
    creator: "",
    parent_strategy_id: null,
  } satisfies CreateStrategyRequest;
}
