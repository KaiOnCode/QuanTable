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
import {
  DEFAULT_DEEP_THINK_MODEL,
  DEFAULT_QUICK_THINK_MODEL,
} from "@/lib/llm-defaults";
import type { CreateStrategyRequest } from "@/lib/types/models";
import {
  ArrowLeft, Plus, Loader2, X,
} from "lucide-react";
import Link from "next/link";

const DEFAULT_AGENTS = ["market", "news", "fundamentals", "pm"];

export default function NewStrategyPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("agent");
  const [tickerInput, setTickerInput] = useState("");
  const [tickers, setTickers] = useState<string[]>([]);
  const [error, setError] = useState("");

  const createMutation = useMutation({
    mutationFn: () =>
      strategiesApi.create({
        name: name || "Untitled Strategy",
        description,
        type: type as "agent" | "quant" | "hitl",
        tickers,
        active_agents: DEFAULT_AGENTS,
        debate_rounds: 2,
        beliefs: [],
        belief_weights: {},
        risk_debate_rounds: 2,
        agent_model: DEFAULT_QUICK_THINK_MODEL,
        deep_think_model: DEFAULT_DEEP_THINK_MODEL,
        agent_temperature: 0,
        enable_debate_mode: true,
        enable_cross_review: false,
        quant_strategy_name: null,
        quant_params: {},
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
      } satisfies CreateStrategyRequest),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["strategies"] });
      router.push(`/strategies/${result.id}`);
    },
    onError: (e: Error) => {
      setError(e.message);
    },
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
    setError("");
    createMutation.mutate();
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
                <Select value={type} onValueChange={(v) => v && setType(v)}>
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
