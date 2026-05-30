"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
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
import { Skeleton } from "@/components/ui/skeleton";
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
import { useQuery } from "@tanstack/react-query";
import { strategiesApi } from "@/lib/api/strategies";
import type { StrategyConfig, PerformanceMetrics, Position } from "@/lib/types/models";
import {
  TrendingUp,
  BarChart3,
  Shield,
  MessageSquare,
  Brain,
  CheckSquare,
  History,
  Settings,
  ArrowUpRight,
  Plus,
  Play,
  Pause,
  Edit,
  Copy,
} from "lucide-react";
import Link from "next/link";

// Mock data
export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();

  const { data: strategy, isLoading: strategyLoading } = useQuery({
    queryKey: ["strategy", id],
    queryFn: () => strategiesApi.get(id),
    enabled: !!id,
  });

  const { data: performance } = useQuery({
    queryKey: ["performance", id],
    queryFn: () => strategiesApi.getPerformance(id),
    enabled: !!id,
  });

  const { data: decisionsData } = useQuery({
    queryKey: ["decisions", id],
    queryFn: () => strategiesApi.getDecisions(id),
    enabled: !!id,
  });

  const { data: positionsData } = useQuery({
    queryKey: ["positions", id],
    queryFn: () => strategiesApi.getPositions(id),
    enabled: !!id,
  });

  const decisions = (decisionsData as any)?.decisions || [];
  const holdings: Position[] = positionsData?.positions || [];
  const account = performance as PerformanceMetrics | undefined;

  if (strategyLoading) {
    return (
      <Shell>
        <div className="p-6 space-y-6">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-64 w-full" />
        </div>
      </Shell>
    );
  }

  const s = strategy || ({} as StrategyConfig);

  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h1 className="text-xl font-bold">{s.name || "Loading..."}</h1>
                {s.type && <Badge variant="outline" className="uppercase text-xs">{s.type}</Badge>}
                {s.status && <StatusBadge status={s.status} />}
              </div>
              <p className="text-sm text-muted-foreground">{s.description || ""}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm">
              <Play className="mr-2 h-4 w-4" />
              {((s.status as string) || "draft") === "active" ? "Restart" : "Start"}
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
            {/* Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Equity</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {formatCurrency((account || {} as any).equity)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Return</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent((account || {} as any).total_pnl_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>vs Benchmark</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent((account || {} as any).excess_return_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Sharpe</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {(account || {} as any).sharpe_ratio?.toFixed(2) || "—"}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Max Drawdown</CardDescription>
                  <CardTitle className="text-2xl font-mono text-red-500">
                    {formatPercent((account || {} as any).max_drawdown_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Win Rate</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {(account || {} as any).win_rate_pct}%
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Trades</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {(account || {} as any).total_trades}
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>

            {/* Equity Chart Placeholder */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Equity Curve</CardTitle>
                <CardDescription>
                  Strategy vs Benchmark (SPY)
                </CardDescription>
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
                {/* Mini table of equity data points */}
                <div className="mt-4">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead className="text-right">Equity</TableHead>
                        <TableHead className="text-right">Benchmark</TableHead>
                        <TableHead className="text-right">Excess</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {((account as any)?.equity_curve || []).map((p: Record<string, any>) => (
                        <TableRow key={p.date}>
                          <TableCell className="text-sm">{p.date}</TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {formatCurrency(p.equity)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm text-muted-foreground">
                            {formatCurrency(p.benchmark)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            <span className={p.equity >= p.benchmark ? "text-green-500" : "text-red-500"}>
                              {formatPercent(((p.equity - p.benchmark) / p.benchmark) * 100)}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* Strategy Info Card */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Configuration</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    <Badge variant="outline" className="uppercase">{s.type}</Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Frequency:</span>{" "}
                    <span className="font-medium capitalize">{s.execution_frequency}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution Time:</span>{" "}
                    <span className="font-medium">{s.execution_time}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>{" "}
                    <span className="font-medium">{(s.active_agents || []).length} agents</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{s.debate_rounds}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Initial Capital:</span>{" "}
                    <span className="font-medium">{formatCurrency(s.initial_capital)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Tickers:</span>{" "}
                    <span className="font-mono">{s.tickers.join(", ")}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>{" "}
                    <span className="font-medium">{s.beliefs.length} configured</span>
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
              decisions.map((d: Record<string, any>) => (
                <Card key={d.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-lg">${d.ticker}</span>
                        <DirectionBadge direction={d.direction} />
                        <ActionBadge action={d.action} />
                        <Badge variant="outline" className="text-xs">
                          Confidence: {(d.confidence * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(d.timestamp)}
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
              <CardHeader>
                <CardTitle className="text-base">Current Holdings</CardTitle>
              </CardHeader>
              <CardContent>
                {holdings.length === 0 ? (
                  <EmptyState
                    title="No holdings"
                    description="No current positions in this s."
                  />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Ticker</TableHead>
                        <TableHead className="text-right">Quantity</TableHead>
                        <TableHead className="text-right">Entry Price</TableHead>
                        <TableHead className="text-right">Current Price</TableHead>
                        <TableHead className="text-right">Market Value</TableHead>
                        <TableHead className="text-right">PnL</TableHead>
                        <TableHead className="text-right">Weight</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {holdings.map((h) => {
                        const pnl =
                          (h.current_price - h.avg_entry_price) * h.quantity;
                        const pnlPct =
                          ((h.current_price - h.avg_entry_price) /
                            h.avg_entry_price) *
                          100;
                        return (
                          <TableRow key={h.ticker}>
                            <TableCell className="font-mono font-bold">
                              ${h.ticker}
                            </TableCell>
                            <TableCell className="text-right">
                              {h.quantity}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {formatCurrency(h.avg_entry_price)}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {formatCurrency(h.current_price)}
                            </TableCell>
                            <TableCell className="text-right font-mono">
                              {formatCurrency(h.current_price * h.quantity)}
                            </TableCell>
                            <TableCell
                              className={`text-right font-mono ${
                                pnl >= 0 ? "text-green-500" : "text-red-500"
                              }`}
                            >
                              {formatPercent(pnlPct)}
                            </TableCell>
                            <TableCell className="text-right">
                              {h.weight_pct}%
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
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
                  description="System event timeline with expandable nodes will appear here."
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
                    <span className="font-medium">{s.name}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    <span className="font-medium uppercase">{s.type}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution:</span>{" "}
                    <span className="font-medium">
                      {s.execution_frequency} @ {s.execution_time}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{s.debate_rounds}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>
                    <ul className="list-disc list-inside mt-1">
                      {s.beliefs.map((b, i) => (
                        <li key={i} className="text-xs text-muted-foreground">
                          {b}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {(s.active_agents || []).map((a) => (
                        <Badge key={a} variant="secondary" className="text-xs">
                          {a}
                        </Badge>
                      ))}
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
