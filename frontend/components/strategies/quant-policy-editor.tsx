"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuantPolicyFields } from "@/components/strategies/quant-policy-fields";
import { strategiesApi } from "@/lib/api/strategies";
import {
  quantPolicyDraftFromStored,
  validateQuantPolicyDraft,
  type QuantPolicyDraft,
} from "@/lib/strategy-policy";
import type { StrategyConfig } from "@/lib/types/models";

export function QuantPolicyEditor({ strategy }: { readonly strategy: StrategyConfig }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<QuantPolicyDraft>(() =>
    quantPolicyDraftFromStored(strategy.quant_strategy_name, strategy.quant_params),
  );
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});
  const [message, setMessage] = useState("");
  const mutation = useMutation({
    mutationFn: (request: Parameters<typeof strategiesApi.update>[1]) =>
      strategiesApi.update(strategy.id, request),
    onSuccess: async () => {
      setMessage("Quant policy saved.");
      await queryClient.invalidateQueries({ queryKey: ["strategy", strategy.id] });
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const save = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validateQuantPolicyDraft(draft, strategy.max_position_pct);
    if (!validation.ok) {
      setErrors(validation.errors);
      setMessage("Correct the highlighted quant policy fields.");
      const firstError = Object.keys(validation.errors)[0];
      const fieldIds: Readonly<Record<string, string>> = {
        lookbackBars: "lookback-bars", entryThreshold: "entry-threshold",
        exitThreshold: "exit-threshold", targetPositionPct: "target-position-pct",
        fastWindow: "fast-window", slowWindow: "slow-window",
      };
      if (firstError) document.getElementById(fieldIds[firstError] ?? "quant-rule")?.focus();
      return;
    }
    setErrors({});
    setMessage("");
    mutation.mutate(validation.payload);
  };

  const cancel = () => {
    setDraft(quantPolicyDraftFromStored(strategy.quant_strategy_name, strategy.quant_params));
    setErrors({});
    setMessage("");
  };

  return (
    <form className="space-y-4" onSubmit={save}>
      <QuantPolicyFields
        draft={draft}
        errors={errors}
        maximumPositionPct={strategy.max_position_pct}
        disabled={mutation.isPending}
        onChange={(nextDraft) => { setDraft(nextDraft); setErrors({}); setMessage(""); }}
      />
      {message ? (
        <p className={mutation.isError ? "text-sm text-destructive" : "text-sm text-muted-foreground"} role="status">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Save Quant Policy
        </Button>
        <Button type="button" variant="outline" onClick={cancel} disabled={mutation.isPending}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
