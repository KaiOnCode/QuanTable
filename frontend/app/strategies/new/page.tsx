"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { strategiesApi } from "@/lib/api/strategies";
import { QuantPolicyFields } from "@/components/strategies/quant-policy-fields";
import type { CreateStrategyRequest, StrategyType } from "@/lib/types/models";
import { buildCreateStrategyRequest } from "@/lib/strategy-create-request";
import {
  DEFAULT_QUANT_POLICY_DRAFT,
  validateQuantPolicyDraft,
  type QuantPolicyDraft,
} from "@/lib/strategy-policy";
import {
  ArrowLeft, Plus, Loader2, X,
} from "lucide-react";
import Link from "next/link";

export default function NewStrategyPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState<StrategyType>("agent");
  const [quantPolicy, setQuantPolicy] = useState<QuantPolicyDraft>(DEFAULT_QUANT_POLICY_DRAFT);
  const [quantErrors, setQuantErrors] = useState<Readonly<Record<string, string>>>({});
  const [tickerInput, setTickerInput] = useState("");
  const [tickers, setTickers] = useState<string[]>([]);
  const [error, setError] = useState("");

  const createMutation = useMutation({
    mutationFn: (request: CreateStrategyRequest) => strategiesApi.create(request),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["strategies"] });
      router.push(`/strategies/${result.id}`);
    },
    onError: (mutationError: Error) => setError(mutationError.message),
  });

  const addTicker = () => {
    const t = tickerInput.trim().toUpperCase();
    if (t && !tickers.includes(t)) {
      setTickers([...tickers, t]);
    }
    setTickerInput("");
  };

  const removeTicker = (t: string) => {
    setTickers(tickers.filter((x) => x !== t));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Strategy name is required");
      return;
    }
    const policy = validateQuantPolicyDraft(quantPolicy, 80);
    if (type === "quant" && !policy.ok) {
      setQuantErrors(policy.errors);
      setError("Correct the highlighted quant policy fields.");
      const firstError = Object.keys(policy.errors)[0];
      const fieldIds: Readonly<Record<string, string>> = {
        lookbackBars: "lookback-bars", entryThreshold: "entry-threshold",
        exitThreshold: "exit-threshold", targetPositionPct: "target-position-pct",
        fastWindow: "fast-window", slowWindow: "slow-window",
      };
      if (firstError) document.getElementById(fieldIds[firstError] ?? "quant-rule")?.focus();
      return;
    }
    const request = buildCreateStrategyRequest({ name, description, type, tickers }, policy);
    if (!request) return;
    setQuantErrors({});
    setError("");
    createMutation.mutate(request);
  };

  return (
    <Shell>
      <div className="p-4 sm:p-6 max-w-2xl mx-auto space-y-6">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/strategies" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Link>
          <h2 className="text-lg font-semibold">New Strategy</h2>
        </div>

        <form onSubmit={handleSubmit}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Basic Info</CardTitle>
              <CardDescription>Name, type, and tickers for your strategy.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Name */}
              <div className="space-y-2">
                <Label htmlFor="name">Name *</Label>
                <Input
                  id="name"
                  placeholder="e.g. Tech Momentum"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>

              {/* Description */}
              <div className="space-y-2">
                <Label htmlFor="desc">Description</Label>
                <Textarea
                  id="desc"
                  placeholder="Describe what this strategy does..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={2}
                />
              </div>

              {/* Type */}
              <div className="space-y-2">
                <Label>Strategy Type</Label>
                <Select value={type} onValueChange={(value) => {
                  if (value === "agent" || value === "quant" || value === "hitl") setType(value);
                }}>
                  <SelectTrigger className="w-full sm:w-48">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="agent">Agent (LLM-driven)</SelectItem>
                    <SelectItem value="quant">Quant (rule-based)</SelectItem>
                    <SelectItem value="hitl">HITL (human approval)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {type === "agent" && "AI agents analyze market data and make decisions autonomously."}
                  {type === "quant" && "Rule-based strategies with configurable parameters."}
                  {type === "hitl" && "AI agents propose decisions; a human approves before execution."}
                </p>
              </div>

              {type === "quant" ? (
                <>
                  <Separator />
                  <QuantPolicyFields
                    draft={quantPolicy}
                    errors={quantErrors}
                    maximumPositionPct={80}
                    disabled={createMutation.isPending}
                    onChange={(draft) => { setQuantPolicy(draft); setQuantErrors({}); }}
                  />
                </>
              ) : null}

              <Separator />

              {/* Tickers */}
              <div className="space-y-2">
                <Label>Tickers</Label>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    placeholder="AAPL"
                    value={tickerInput}
                    onChange={(e) => setTickerInput(e.target.value.toUpperCase())}
                    className="max-w-[150px]"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        addTicker();
                      }
                    }}
                  />
                  <Button type="button" variant="outline" size="sm" onClick={addTicker}>
                    <Plus className="mr-1 h-3 w-3" /> Add
                  </Button>
                </div>
                {tickers.length > 0 && (
                  <div className="flex gap-1 flex-wrap mt-2">
                    {tickers.map((t) => (
                      <Badge key={t} variant="secondary" className="font-mono gap-1">
                        ${t}
                        <button
                          type="button"
                          onClick={() => removeTicker(t)}
                          className="ml-1 hover:text-destructive"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  {tickers.length === 0
                    ? "Add at least one ticker to get started."
                    : `${tickers.length} ticker(s) added.`}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <p className="text-sm text-destructive mt-4 bg-destructive/10 p-3 rounded-md">{error}</p>
          )}

          {/* Submit */}
          <div className="flex flex-col-reverse gap-3 mt-6 sm:flex-row sm:justify-end">
            <Link href="/strategies" className={buttonVariants({ variant: "outline" })}>
              Cancel
            </Link>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : null}
              Create Strategy
            </Button>
          </div>
        </form>
      </div>
    </Shell>
  );
}
