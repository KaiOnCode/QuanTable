"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { StatusBadge, DirectionBadge, ActionBadge } from "@/components/shared/badges";
import { EmptyState } from "@/components/shared/empty-state";
import { formatPercent, formatDate } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import { QuantPolicyEditor } from "@/components/strategies/quant-policy-editor";
import { Loader2, ArrowLeft, TrendingUp, BarChart3, Settings } from "lucide-react";
import Link from "next/link";

type TabKey = "overview" | "decisions" | "settings";

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<TabKey>("overview");

  const { data: strategy, isLoading } = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => strategiesApi.get(id),
    enabled: !!id,
  });

  const { data: perf } = useQuery({
    queryKey: ["strategy", id, "performance"],
    queryFn: () => strategiesApi.getPerformance(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <Shell>
        <div className="p-6 flex justify-center h-64 items-center">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </Shell>
    );
  }

  if (!strategy) {
    return (
      <Shell>
        <div className="p-6">
          <Card className="border-destructive">
            <CardContent className="pt-8">
              <EmptyState title="Strategy not found"
                description="It may have been deleted."
                action={<Link href="/strategies" className={buttonVariants()}><ArrowLeft className="mr-2 h-4 w-4" /> Back to Strategies</Link>}
              />
            </CardContent>
          </Card>
        </div>
      </Shell>
    );
  }

  const tickers = strategy.tickers ?? [];
  const agents = strategy.active_agents ?? [];

  const tabs: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: "overview", label: "Overview", icon: <TrendingUp className="h-4 w-4" /> },
    { key: "decisions", label: "Decisions", icon: <BarChart3 className="h-4 w-4" /> },
    { key: "settings", label: "Settings", icon: <Settings className="h-4 w-4" /> },
  ];

  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div>
          <Link href="/strategies" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Link>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <h1 className="text-xl font-bold">{strategy.name}</h1>
            <Badge variant="outline" className="uppercase text-xs">{strategy.type}</Badge>
            <StatusBadge status={strategy.status ?? "draft"} />
          </div>
          <p className="text-sm text-muted-foreground mt-1">{strategy.description}</p>
        </div>

        {/* Custom tab bar (avoids @base-ui/react/tabs SSR issue) */}
        <div className="flex items-center gap-1 border-b pb-2">
          {tabs.map((t) => (
            <Button
              key={t.key}
              variant={tab === t.key ? "default" : "ghost"}
              size="sm"
              onClick={() => setTab(t.key)}
            >
              {t.icon}
              <span className="ml-2">{t.label}</span>
            </Button>
          ))}
        </div>

        {/* Tab: Overview */}
        {tab === "overview" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <MetricCard label="Total Return" value={formatPercent(perf?.total_return_pct ?? 0)} highlight />
              <MetricCard label="vs Benchmark" value={formatPercent(perf?.excess_return_pct ?? 0)} />
              <MetricCard label="Win Rate" value={`${perf?.win_rate_pct ?? 0}%`} />
              <MetricCard label="Total Trades" value={`${perf?.total_trades ?? 0}`} />
            </div>

            <Card>
              <CardHeader><CardTitle className="text-base">Configuration</CardTitle></CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                  <InfoRow label="Type" value={strategy.type} />
                  <InfoRow label="Frequency" value={strategy.execution_frequency ?? "daily"} />
                  <InfoRow label="Time" value={strategy.execution_time ?? "09:30"} />
                  <InfoRow label="Debate Rounds" value={`${strategy.debate_rounds ?? 2}`} />
                  <InfoRow label="Agents" value={`${agents.length} active`} />
                  <InfoRow label="Created" value={formatDate(strategy.created_at ?? "")} />
                </div>
                {tickers.length > 0 && (
                  <div className="mt-3 flex gap-1 flex-wrap">
                    <span className="text-xs text-muted-foreground">Tickers:</span>
                    {tickers.map((t: string) => (
                      <Badge key={t} variant="secondary" className="font-mono text-xs">${t}</Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}

        {/* Tab: Decisions */}
        {tab === "decisions" && (
          <StrategyDecisions strategyId={strategy.id} />
        )}

        {/* Tab: Settings */}
        {tab === "settings" && (
          <Card>
            <CardHeader><CardTitle className="text-base">Strategy Settings</CardTitle></CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <InfoRow label="Name" value={strategy.name} />
                <InfoRow label="Type" value={strategy.type} />
                <InfoRow label="Execution" value={`${strategy.execution_frequency ?? "daily"} @ ${strategy.execution_time ?? "09:30"}`} />
                <InfoRow label="Debate Rounds" value={`${strategy.debate_rounds ?? 2}`} />
                {strategy.type === "quant" ? (
                  <div className="col-span-2 mt-3 border-t pt-4">
                    <h2 className="mb-1 text-sm font-semibold">Deterministic Quant Policy</h2>
                    <p className="mb-4 text-xs text-muted-foreground">
                      Configure the supported executable rule persisted with this strategy.
                    </p>
                    <QuantPolicyEditor strategy={strategy} />
                  </div>
                ) : null}
                <div className="col-span-2">
                  <span className="text-muted-foreground">Beliefs:</span>
                  {(strategy.beliefs ?? []).length > 0 ? (
                    <ul className="list-disc list-inside">{strategy.beliefs?.map((belief: string) => <li key={`${strategy.id}:${belief}`} className="text-xs text-muted-foreground">{belief}</li>)}</ul>
                  ) : <span className="text-xs text-muted-foreground"> None configured</span>}
                </div>
                <div className="col-span-2">
                  <span className="text-muted-foreground">Active Agents:</span>
                  <span className="ml-2 text-xs">{agents.join(", ") || "None"}</span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Shell>
  );
}

function MetricCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className={`text-lg font-mono ${highlight ? "text-green-500" : ""}`}>{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-xs text-muted-foreground">{label}</span>
      <p className="font-medium capitalize">{value || "—"}</p>
    </div>
  );
}

function StrategyDecisions({ strategyId }: { strategyId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["strategy", strategyId, "decisions"],
    queryFn: () => strategiesApi.getDecisions(strategyId),
    enabled: !!strategyId,
  });

  if (isLoading) return <p className="text-sm text-muted-foreground p-4">Loading decisions...</p>;

  const decisions = data?.decisions ?? [];
  if (decisions.length === 0) {
    return (
      <Card>
        <CardContent className="pt-8">
          <EmptyState title="No decisions yet"
            description="Run this strategy to generate trading decisions. Decisions will appear here."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {decisions.slice(0, 20).map((d) => (
        <Card key={d.id}>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold text-lg">${d.ticker}</span>
                <DirectionBadge direction={d.direction ?? "Neutral"} />
                <ActionBadge action={d.action ?? "HOLD"} />
                <Badge variant="outline" className="text-xs">
                  Confidence: {((d.confidence ?? 0) * 100).toFixed(0)}%
                </Badge>
              </div>
              <span className="text-xs text-muted-foreground">{d.created_at?.slice(0, 10) ?? ""}</span>
            </div>
          </CardHeader>
          {d.report && (
            <CardContent>
              <p className="text-sm text-muted-foreground line-clamp-3">{d.report}</p>
              {d.winning_belief && (
                <p className="text-xs text-muted-foreground mt-1">Belief: {d.winning_belief}</p>
              )}
            </CardContent>
          )}
        </Card>
      ))}
    </div>
  );
}
