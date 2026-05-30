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
const MOCK_STRATEGY = {
  id: "1",
  name: "Tech Momentum",
  description: "Momentum-based strategy focused on tech stocks with RSI/MA cross signals",
  type: "agent" as const,
  status: "active" as const,
  tickers: ["AAPL", "MSFT", "NVDA"],
  beliefs: ["聚焦科技股动量：关注RSI超卖反弹和均线金叉信号"],
  active_agents: ["market", "news", "fundamentals", "bull_researcher", "bear_researcher", "pm"],
  debate_rounds: 2,
  execution_frequency: "daily",
  execution_time: "09:30",
  initial_capital: 100000,
  created_at: "2026-05-01T09:00:00Z",
  updated_at: "2026-05-28T06:00:00Z",
  tags: ["tech", "momentum"],
  creator: "team",
  parent_strategy_id: null,
};

const MOCK_ACCOUNT = {
  equity: 105230.45,
  cash: 32100.20,
  total_pnl_pct: 5.23,
  benchmark_return_pct: 2.15,
  excess_return_pct: 3.08,
  sharpe_ratio: 1.35,
  max_drawdown_pct: -8.45,
  win_rate_pct: 62.5,
  total_trades: 24,
};

const MOCK_DECISIONS = [
  {
    id: "d1",
    ticker: "AAPL",
    direction: "Bullish",
    action: "BUY",
    confidence: 0.78,
    target_position_pct: 15,
    winning_belief: "科技股动量",
    timestamp: "2026-05-28T09:35:00Z",
    report: "RSI(14)=32 超卖区域，均线金叉信号确认，MACD底部背离。",
  },
  {
    id: "d2",
    ticker: "MSFT",
    direction: "Bullish",
    action: "BUY",
    confidence: 0.65,
    target_position_pct: 10,
    winning_belief: "科技股动量",
    timestamp: "2026-05-27T09:35:00Z",
    report: "财报超预期后回调至20日均线，机构增持明显。",
  },
  {
    id: "d3",
    ticker: "NVDA",
    direction: "Neutral",
    action: "HOLD",
    confidence: 0.55,
    target_position_pct: 10,
    winning_belief: null,
    timestamp: "2026-05-26T09:35:00Z",
    report: "估值偏高但AI需求强劲，暂持观望。",
  },
];

const MOCK_HOLDINGS = [
  { ticker: "AAPL", quantity: 50, avg_entry_price: 185.20, current_price: 192.45, weight_pct: 28.3 },
  { ticker: "MSFT", quantity: 20, avg_entry_price: 420.50, current_price: 445.30, weight_pct: 26.5 },
  { ticker: "NVDA", quantity: 30, avg_entry_price: 880.00, current_price: 950.20, weight_pct: 18.2 },
];

const MOCK_EQUITY_CURVE = [
  { date: "2026-04-01", equity: 100000, benchmark: 100000 },
  { date: "2026-04-15", equity: 102500, benchmark: 101200 },
  { date: "2026-05-01", equity: 104000, benchmark: 101800 },
  { date: "2026-05-15", equity: 105800, benchmark: 102500 },
  { date: "2026-05-28", equity: 105230, benchmark: 102150 },
];

export default function StrategyDetailPage() {
  const { id } = useParams<{ id: string }>();
  const strategy = MOCK_STRATEGY;
  const account = MOCK_ACCOUNT;
  const decisions = MOCK_DECISIONS;
  const holdings = MOCK_HOLDINGS;
  const equityCurve = MOCK_EQUITY_CURVE;

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
                <StatusBadge status={strategy.status} />
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
            {/* Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Equity</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {formatCurrency(account.equity)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Return</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent(account.total_pnl_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>vs Benchmark</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent(account.excess_return_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Sharpe</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {account.sharpe_ratio?.toFixed(2) || "—"}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Max Drawdown</CardDescription>
                  <CardTitle className="text-2xl font-mono text-red-500">
                    {formatPercent(account.max_drawdown_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Win Rate</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {account.win_rate_pct}%
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Trades</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {account.total_trades}
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
                      {equityCurve.map((p) => (
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
                    <Badge variant="outline" className="uppercase">{strategy.type}</Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Frequency:</span>{" "}
                    <span className="font-medium capitalize">{strategy.execution_frequency}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution Time:</span>{" "}
                    <span className="font-medium">{strategy.execution_time}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>{" "}
                    <span className="font-medium">{strategy.active_agents.length} agents</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{strategy.debate_rounds}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Initial Capital:</span>{" "}
                    <span className="font-medium">{formatCurrency(strategy.initial_capital)}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Tickers:</span>{" "}
                    <span className="font-mono">{strategy.tickers.join(", ")}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>{" "}
                    <span className="font-medium">{strategy.beliefs.length} configured</span>
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
              decisions.map((d) => (
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
                    description="No current positions in this strategy."
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
                    <span className="font-medium">{strategy.name}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Type:</span>{" "}
                    <span className="font-medium uppercase">{strategy.type}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Execution:</span>{" "}
                    <span className="font-medium">
                      {strategy.execution_frequency} @ {strategy.execution_time}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Debate Rounds:</span>{" "}
                    <span className="font-medium">{strategy.debate_rounds}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Beliefs:</span>
                    <ul className="list-disc list-inside mt-1">
                      {strategy.beliefs.map((b, i) => (
                        <li key={i} className="text-xs text-muted-foreground">
                          {b}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Active Agents:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {strategy.active_agents.map((a) => (
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
