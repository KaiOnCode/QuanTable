import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  DEFAULT_QUANT_POLICY_DRAFT,
  quantPolicyDraftFromStored,
  validateQuantPolicyDraft,
} from "../lib/strategy-policy.ts";

const QUANT_POLICY_FIELDS = new URL("../components/strategies/quant-policy-fields.tsx", import.meta.url);
const QUANT_POLICY_EDITOR = new URL("../components/strategies/quant-policy-editor.tsx", import.meta.url);

test("quant strategy creation exposes supported typed policy fields", async () => {
  // Given: the public New Strategy surface
  const source = await readFile(QUANT_POLICY_FIELDS, "utf8");

  // When: its quant policy contract is inspected
  const requiredContractLabels = [
    "Quant Rule",
    "Lookback Bars",
    "Entry Threshold",
    "Exit Threshold",
    "Fast Window",
    "Slow Window",
    "Target Position (%)",
  ];

  // Then: both supported rule families and every typed parameter are present
  assert.match(source, /value="momentum"/);
  assert.match(source, /value="sma_crossover"/);
  for (const label of requiredContractLabels) {
    assert.match(source, new RegExp(label.replace(/[()]/g, "\\$&")));
  }
});

test("quant policy edit has native submit, first-error focus, and local cancel semantics", async () => {
  const source = await readFile(QUANT_POLICY_EDITOR, "utf8");

  assert.match(source, /<form[^>]*onSubmit=/);
  assert.match(source, /type="submit"/);
  assert.match(source, /document\.getElementById/);
  assert.match(source, /type="button"[^>]*onClick=\{cancel\}/);
});

test("momentum policy produces stable API JSON and rejects inverted thresholds", () => {
  const valid = validateQuantPolicyDraft(DEFAULT_QUANT_POLICY_DRAFT, 80);
  assert.deepEqual(valid, {
    ok: true,
    payload: {
      quant_strategy_name: "momentum",
      quant_params: {
        lookback_bars: 20,
        entry_threshold: 0.05,
        exit_threshold: 0,
        target_position_pct: 80,
      },
    },
  });
  const invalid = validateQuantPolicyDraft({
    ...DEFAULT_QUANT_POLICY_DRAFT,
    momentum: { ...DEFAULT_QUANT_POLICY_DRAFT.momentum, entryThreshold: "0.01", exitThreshold: "0.02" },
  });
  assert.equal(invalid.ok, false);
  if (!invalid.ok) assert.match(invalid.errors.exitThreshold, /must not exceed/);
});

test("rule switching preserves typed SMA state and enforces window ordering", () => {
  const draft = quantPolicyDraftFromStored("sma_crossover", {
    fast_window: 12,
    slow_window: 48,
    target_position_pct: 60,
  });
  assert.equal(draft.rule, "sma_crossover");
  assert.deepEqual(validateQuantPolicyDraft(draft, 80), {
    ok: true,
    payload: {
      quant_strategy_name: "sma_crossover",
      quant_params: { fast_window: 12, slow_window: 48, target_position_pct: 60 },
    },
  });
  const invalid = validateQuantPolicyDraft({
    ...draft,
    smaCrossover: { ...draft.smaCrossover, fastWindow: "50", slowWindow: "20" },
  });
  assert.equal(invalid.ok, false);
  if (!invalid.ok) assert.match(invalid.errors.slowWindow, /must exceed/);
});
