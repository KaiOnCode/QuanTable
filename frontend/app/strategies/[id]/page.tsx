"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge, DirectionBadge, ActionBadge } from "@/components/shared/badges";
import { formatCurrency, formatPercent, formatDate, formatDateTime } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import type { StrategyConfig, PerformanceMetrics } from "@/lib/types/models";
import {
  TrendingUp,
  BarChart3,
  Shield,
  MessageSquare,
  Brain,
  CheckSquare,
  History,
  Settings,
  Loader2,
  Play,
  Pause,
  Edit,
  Copy,
} from "lucide-react";
import Link from "next/link";

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();

  const {
    data: strategy,
    isLoading: strategyLoading,
    isError: strategyError,
  } = useQuery<StrategyConfig>({
    queryKey: ["strategy", id],
    queryFn: () => strategiesApi.get(id),
    enabled: !!id,
  });

  const { data: performance } = useQuery<PerformanceMetrics>({
    queryKey: ["strategy", id, "performance"],
    queryFn: () => strategiesApi.getPerformance(id),
    enabled: !!id,
  });

  const { data: decisionsData } = useQuery({
    queryKey: ["strategy", id, "decisions"],
    queryFn: () => strategiesApi.getDecisions(id),
    enabled: !!id,
  });
  const decisions: any[] = decisionsData?.decisions ?? [];

  if (strategyLoading) {
    return (
      <Shell>
        <div className="p-6 flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </Shell>
    );
  }

  if (strategyError || !strategy) {
    return (
      <Shell>
        <div className="p-6">
          <Card className="border-destructive">
            <CardContent className="pt-8">
              <EmptyState
                title="Strategy not found"
                description="The requested strategy could not be loaded. It may have been deleted."
                action={
                  <Link href="/strategies" className={buttonVariants()}>
                    Back to Strategies
                  </Link>
                }
              />
            </CardContent>
          </Card>
        </div>
      </Shell>
    );
  }

  const tickers = strategy.tickers ?? [];
  const beliefs = strategy.beliefs ?? [];
  const agents = strategy.active_agents ?? [];

  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="text-xl font-bold">{strategy.name}</h1>
                <Badge variant="outline" className="uppercase text-xs">
                  {strategy.type}
                </Badge>
                <StatusBadge status={strategy.status ?? "draft"} />
              </div>
              <p className="text-sm text-muted-foreground">
                {strategy.description}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm">
              <Play className="mr-2 h-4 w-4" />
              {strategy.status === "active" ? "Restart" : "Start"}
            </Button>
            <Button variant="outline" size="sm">
              <Pause className="mr-2 h-4 w-4" />
              Pause
            </Button>
            <Button variant="outline" size="sm">
              <Edit className="mr-2 h-4 w-4" />
              Edit
            </Button>
            <Button variant="outline" size="sm">
              <Copy className="mr-2 h-4 w-4" />
              Clone
            </Button>
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview" className="space-y-4">
          <TabsList>
            <TabsTrigger value="overview">
              <TrendingUp className="mr-2 h-4 w-4" />
              Overview
            </TabsTrigger>
            <TabsTrigger value="decisions">
              <BarChart3 className="mr-2 h-4 w-4" />
              Decisions
            </TabsTrigger>
            <TabsTrigger value="holdings">
              <Shield className="mr-2 h-4 w-4" />
              Holdings
            </TabsTrigger>
            <TabsTrigger value="debate">
              <MessageSquare className="mr-2 h-4 w-4" />
              Debate
            </TabsTrigger>
            <TabsTrigger value="memory">
              <Brain className="mr-2 h-4 w-4" />
              Memory
            </TabsTrigger>
            <TabsTrigger value="approvals">
              <CheckSquare className="mr-2 h-4 w-4" />
              Approvals
            </TabsTrigger>
            <TabsTrigger value="audit">
              <History className="mr-2 h-4 w-4" />
              Audit
            </TabsTrigger>
            <TabsTrigger value="settings">
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Return</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent(performance?.total_return_pct ?? 0)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>vs Benchmark</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {formatPercent(performance?.excess_return_pct ?? 0)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Win Rate</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {performance?.win_rate_pct ?? 0}%
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Max Drawdown</CardDescription>
                  <CardTitle className="text-2xl font-mono text-red-500">
                    {formatPercent(performance?.max_drawdown_pct ?? 0)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Trades</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {performance?.total_trades ?? 0}
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>

            {/* Equity Chart Placeholder */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Equity Curve</CardTitle>
                <CardDescription>Strategy vs Benchmark (SPY)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center bg-muted/30 rounded-lg">
                  <div className="text-center">
                    <TrendingUp className="h-10 w-10 mx-auto mb-2 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      Equity chart will render here with TradingView Lightweight Charts
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Strategy Info */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Configuration</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    <Badge variant="outline" className="uppercase">{strategy.type}</Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Frequency:</span>{" "}
                    <span className="font-medium capitalize">{strategy.execution_frequency ?? "daily"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution Time:</span>{" "}
                    <span className="font-medium">{strategy.execution_time ?? "09:30"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>{" "}
                    <span className="font-medium">{agents.length} agents</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{strategy.debate_rounds ?? 2}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Tickers:</span>{" "}
                    <span className="font-mono">{tickers.join(", ") || "None"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>{" "}
                    <span className="font-medium">{beliefs.length} configured</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Decisions Tab */}
          <TabsContent value="decisions" className="space-y-4">
            {decisions.length === 0 ? (
              <EmptyState
                title="No decisions yet"
                description="Decisions will appear after the strategy executes its first analysis."
              />
            ) : (
              decisions.map((d: any) => (
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
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(d.created_at ?? d.timestamp ?? "")}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm">{d.report}</p>
                    {d.winning_belief && (
                      <p className="text-xs text-muted-foreground mt-2">
                        Winning belief: {d.winning_belief}
                      </p>
                    )}
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          {/* Holdings Tab */}
          <TabsContent value="holdings">
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  title="No holdings"
                  description="Broker integration not yet connected. Holdings will appear when the broker engine is online."
                />
              </CardContent>
            </Card>
          </TabsContent>

          {/* Stub tabs */}
          <TabsContent value="debate">
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  icon={<MessageSquare className="h-12 w-12" />}
                  title="Debate Viewer"
                  description="Bull vs Bear and Risk 3-way debate records will appear here after strategy executions."
                />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="memory">
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  icon={<Brain className="h-12 w-12" />}
                  title="Memory Lab"
                  description="OWM memory records, reflections, and knowledge base entries will appear here."
                />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="approvals">
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  icon={<CheckSquare className="h-12 w-12" />}
                  title="Approvals"
                  description="HITL approval requests and history will appear here."
                />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="audit">
            <Card>
              <CardContent className="pt-8">
                <EmptyState
                  icon={<History className="h-12 w-12" />}
                  title="Audit Trail"
                  description="System event timeline will appear here."
                />
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="settings">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Strategy Configuration</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <span className="text-muted-foreground">Name:</span>{" "}
                    <span className="font-medium">{strategy.name}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    <span className="font-medium uppercase">{strategy.type}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution:</span>{" "}
                    <span className="font-medium">
                      {strategy.execution_frequency ?? "daily"} @ {strategy.execution_time ?? "09:30"}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{strategy.debate_rounds ?? 2}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>
                    <ul className="list-disc list-inside mt-1">
                      {beliefs.length > 0 ? (
                        beliefs.map((b, i) => (
                          <li key={i} className="text-xs text-muted-foreground">{b}</li>
                        ))
                      ) : (
                        <li className="text-xs text-muted-foreground">None configured</li>
                      )}
                    </ul>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {agents.length > 0 ? (
                        agents.map((a) => (
                          <Badge key={a} variant="secondary" className="text-xs">{a}</Badge>
                        ))
                      ) : (
                        <span className="text-xs text-muted-foreground">None</span>
                      )}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </Shell>
  );
}
