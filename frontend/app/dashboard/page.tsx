"use client";

import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/badges";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import { api } from "@/lib/api/client";
import type { StrategyConfig, PerformanceMetrics } from "@/lib/types/models";
import {
  TrendingUp,
  BarChart3,
  Zap,
  LineChart,
  Plus,
  ArrowUpRight,
  Loader2,
} from "lucide-react";
import Link from "next/link";

function StrategyCard({ strategy }: { strategy: StrategyConfig }) {
  const { data: perf } = useQuery<PerformanceMetrics>({
    queryKey: ["strategy", strategy.id, "performance"],
    queryFn: () => strategiesApi.getPerformance(strategy.id),
    staleTime: 60_000,
  });

  const pct = perf?.total_return_pct ?? 0;
  const isPositive = pct >= 0;

  return (
    <Link href={`/strategies/${strategy.id}`}>
      <Card className="hover:border-primary/50 transition-colors cursor-pointer h-full">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium truncate">
              {strategy.name}
            </CardTitle>
            <StatusBadge status={strategy.status ?? "draft"} />
          </div>
          <CardDescription className="text-xs truncate">
            {strategy.description || "No description"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="uppercase text-xs">
                {strategy.type}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {(strategy.tickers ?? []).length} tickers
              </span>
            </div>
            <span
              className={`font-mono text-lg font-bold ${
                isPositive ? "text-green-500" : "text-red-500"
              }`}
            >
              {formatPercent(pct)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["strategies", undefined, undefined],
    queryFn: () => strategiesApi.list({ limit: 6 }),
  });

  const strategies = data?.items ?? [];
  const hasStrategies = strategies.length > 0;

  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Quick Actions */}
        <div className="flex items-center gap-3 flex-wrap">
          <Link href="/quick-ask" className={buttonVariants()}>
            <Zap className="mr-2 h-4 w-4" />
            Quick Ask
          </Link>
          <Link href="/strategies/new" className={buttonVariants({ variant: "outline" })}>
            <Plus className="mr-2 h-4 w-4" />
            New Strategy
          </Link>
          <Link href="/backtest" className={buttonVariants({ variant: "outline" })}>
            <LineChart className="mr-2 h-4 w-4" />
            Run Backtest
          </Link>
          <Link href="/memory-lab" className={buttonVariants({ variant: "outline" })}>
            <BarChart3 className="mr-2 h-4 w-4" />
            Memory Lab
          </Link>
        </div>

        {/* Strategy Leaderboard */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Strategy Leaderboard</h2>
            <Link
              href="/strategies"
              className={buttonVariants({ variant: "ghost", size: "sm" })}
            >
              View All <ArrowUpRight className="h-3 w-3" />
            </Link>
          </div>

          {isLoading ? (
            <Card>
              <CardContent className="pt-8 flex items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </CardContent>
            </Card>
          ) : !hasStrategies ? (
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  title="No strategies yet"
                  description="Create your first trading strategy to see performance metrics and leaderboard rankings."
                  action={
                    <Link href="/strategies/new" className={buttonVariants()}>
                      <Plus className="mr-2 h-4 w-4" />
                      Create Strategy
                    </Link>
                  }
                />
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {strategies.map((s) => (
                <StrategyCard key={s.id} strategy={s} />
              ))}
            </div>
          )}
        </div>

        {/* Equity Chart + Alerts */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Portfolio Performance</CardTitle>
              <CardDescription>Equity curve overlay vs benchmark</CardDescription>
            </CardHeader>
            <CardContent className="h-80 flex items-center justify-center">
              <EmptyState
                icon={<TrendingUp className="h-12 w-12" />}
                title="Performance chart"
                description="Equity curves will appear once strategies have trade data from the broker engine."
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Alerts &amp; Pending</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Pending Approvals</span>
                  <Badge variant="outline">0</Badge>
                </div>
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Triggered Alerts</span>
                  <Badge variant="outline">0</Badge>
                </div>
                <div className="flex items-center justify-between text-sm p-3 rounded-lg bg-muted/50">
                  <span>Reflections Ready</span>
                  <Badge variant="outline">0</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Market Brief */}
        <MarketBriefCard />
      </div>
    </Shell>
  );
}

function MarketBriefCard() {
  const { data } = useQuery({
    queryKey: ["insights", "latest"],
    queryFn: () => api.get<{ insight: import("@/lib/types/models").DailyBrief | null }>("insights/latest"),
    staleTime: 300_000,
  });
  const brief = data?.insight;
  if (!brief) return null;
  return (
    <Card
      className="cursor-pointer hover:bg-muted/30 transition-colors"
      onClick={() => window.location.href = "/insights"}
    >
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{brief.title}</CardTitle>
        <p className="text-xs text-muted-foreground">
          {brief.summary?.slice(0, 150)}
        </p>
      </CardHeader>
    </Card>
  );
}
