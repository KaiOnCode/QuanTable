"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { QuantPolicyDraft, QuantRule } from "@/lib/strategy-policy";

type Props = {
  readonly draft: QuantPolicyDraft;
  readonly errors: Readonly<Record<string, string>>;
  readonly maximumPositionPct: number;
  readonly disabled?: boolean;
  readonly onChange: (draft: QuantPolicyDraft) => void;
};

type NumberFieldProps = {
  readonly id: string;
  readonly label: string;
  readonly value: string;
  readonly description: string;
  readonly error?: string;
  readonly disabled?: boolean;
  readonly onChange: (value: string) => void;
};

function NumberField({ id, label, value, description, error, disabled, onChange }: NumberFieldProps) {
  const descriptionId = `${id}-description`;
  const errorId = `${id}-error`;
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        value={value}
        disabled={disabled}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${descriptionId} ${errorId}` : descriptionId}
        onChange={(event) => onChange(event.target.value)}
      />
      <p id={descriptionId} className="text-xs text-muted-foreground">{description}</p>
      {error ? <p id={errorId} className="text-xs text-destructive" role="alert">{error}</p> : null}
    </div>
  );
}

export function QuantPolicyFields({ draft, errors, maximumPositionPct, disabled, onChange }: Props) {
  const changeRule = (value: string | null) => {
    if (value === "momentum" || value === "sma_crossover") {
      onChange({ ...draft, rule: value satisfies QuantRule });
    }
  };
  return (
    <fieldset className="space-y-4">
      <legend className="sr-only">Quant policy parameters</legend>
      <div className="space-y-2">
        <Label htmlFor="quant-rule">Quant Rule</Label>
        <Select value={draft.rule} onValueChange={changeRule} disabled={disabled}>
          <SelectTrigger id="quant-rule" className="w-full sm:w-64" aria-describedby="quant-rule-description">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="momentum">Momentum</SelectItem>
            <SelectItem value="sma_crossover">SMA Crossover</SelectItem>
          </SelectContent>
        </Select>
        <p id="quant-rule-description" className="text-xs text-muted-foreground">
          Only supported deterministic rules are available; the name is never compiled into a hidden rule.
        </p>
      </div>
      {draft.rule === "momentum" ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField id="lookback-bars" label="Lookback Bars" value={draft.momentum.lookbackBars} description="Whole trading bars, from 2 to 252." error={errors.lookbackBars} disabled={disabled} onChange={(value) => onChange({ ...draft, momentum: { ...draft.momentum, lookbackBars: value } })} />
          <NumberField id="target-position-pct" label="Target Position (%)" value={draft.momentum.targetPositionPct} description={`Long-only target from 0 to ${maximumPositionPct} percent.`} error={errors.targetPositionPct} disabled={disabled} onChange={(value) => onChange({ ...draft, momentum: { ...draft.momentum, targetPositionPct: value } })} />
          <NumberField id="entry-threshold" label="Entry Threshold" value={draft.momentum.entryThreshold} description="Finite decimal return threshold used to enter." error={errors.entryThreshold} disabled={disabled} onChange={(value) => onChange({ ...draft, momentum: { ...draft.momentum, entryThreshold: value } })} />
          <NumberField id="exit-threshold" label="Exit Threshold" value={draft.momentum.exitThreshold} description="Must not exceed the entry threshold." error={errors.exitThreshold} disabled={disabled} onChange={(value) => onChange({ ...draft, momentum: { ...draft.momentum, exitThreshold: value } })} />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField id="fast-window" label="Fast Window" value={draft.smaCrossover.fastWindow} description="Whole trading bars, from 2 to 100." error={errors.fastWindow} disabled={disabled} onChange={(value) => onChange({ ...draft, smaCrossover: { ...draft.smaCrossover, fastWindow: value } })} />
          <NumberField id="slow-window" label="Slow Window" value={draft.smaCrossover.slowWindow} description="Whole trading bars, from 3 to 252; must exceed fast." error={errors.slowWindow} disabled={disabled} onChange={(value) => onChange({ ...draft, smaCrossover: { ...draft.smaCrossover, slowWindow: value } })} />
          <NumberField id="target-position-pct" label="Target Position (%)" value={draft.smaCrossover.targetPositionPct} description={`Long-only target from 0 to ${maximumPositionPct} percent.`} error={errors.targetPositionPct} disabled={disabled} onChange={(value) => onChange({ ...draft, smaCrossover: { ...draft.smaCrossover, targetPositionPct: value } })} />
        </div>
      )}
    </fieldset>
  );
}
