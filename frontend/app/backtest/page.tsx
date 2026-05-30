"use client";

import { useState } from "react";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/empty-state";
import {
  formatCurrency,
  formatPercent,
  formatDate,
} from "@/lib/utils";
import {
  LineChart,
  Play,
  Download,
  CheckCircle2,
  XCircle,
  TrendingUp,
  BarChart3,
} from "lucide-react";

const MOCK_RESULT = {
  summary: {
    total_predictions: 52,
    accuracy_pct: 62.5,
    cumulative_return_pct: 15.3,
    benchmark_return_pct: 9.1,
    excess_return_pct: 6.2,
    information_ratio: 0.85,
    sharpe_ratio: 1.2,
  },
  results: [
    {
      date: "2023-01-06",
      ticker: "AAPL",
      predicted_direction: "Bullish",
      confidence: 0.8,
      actual_direction: "Bullish",
      actual_return_pct: 3.2,
      benchmark_return_pct: 1.5,
      was_correct: true,
    },
    {
      date: "2023-01-06",
      ticker: "MSFT",
      predicted_direction: "Bullish",
      confidence: 0.65,
      actual_direction: "Bearish",
      actual_return_pct: -1.8,
      benchmark_return_pct: 1.5,
      was_correct: false,
    },
    {
      date: "2023-01-13",
      ticker: "AAPL",
      predicted_direction: "Neutral",
      confidence: 0.55,
      actual_direction: "Bullish",
      actual_return_pct: 1.2,
      benchmark_return_pct: 0.8,
      was_correct: false,
    },
    {
      date: "2023-01-13",
      ticker: "MSFT",
      predicted_direction: "Bullish",
      confidence: 0.72,
      actual_direction: "Bullish",
      actual_return_pct: 2.5,
      benchmark_return_pct: 0.8,
      was_correct: true,
    },
    {
      date: "2023-01-20",
      ticker: "AAPL",
      predicted_direction: "Bearish",
      confidence: 0.78,
      actual_direction: "Bearish",
      actual_return_pct: -2.1,
      benchmark_return_pct: -0.5,
      was_correct: true,
    },
  ],
};

export default function BacktestPage() {
  const [hasRun, setHasRun] = useState(true);
  const result = MOCK_RESULT;

  const correctCount = result.results.filter((r) => r.was_correct).length;
  const total = result.results.length;
  const accuracy = ((correctCount / total) * 100).toFixed(1);

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <LineChart className="h-5 w-5" />
            Backtest
          </h2>
          <p className="text-sm text-muted-foreground">
            Validate strategies against historical data with benchmark comparison.
          </p>
        </div>

        {/* Configuration */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Configuration</CardTitle>
            <CardDescription>
              Select strategy, tickers, and date range for backtesting.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="space-y-2">
                <Label>Strategy</Label>
                <Select defaultValue="tech-momentum">
                  <SelectTrigger>
                    <SelectValue placeholder="Select strategy" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="tech-momentum">Tech Momentum</SelectItem>
                    <SelectItem value="value-hunter">Value Hunter</SelectItem>
                    <SelectItem value="hitl-safe">HITL Safe Harbor</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Tickers</Label>
                <Input placeholder="AAPL, MSFT, NVDA" defaultValue="AAPL, MSFT" />
              </div>
              <div className="space-y-2">
                <Label>Date From</Label>
                <Input type="date" defaultValue="2023-01-01" />
              </div>
              <div className="space-y-2">
                <Label>Date To</Label>
                <Input type="date" defaultValue="2023-12-31" />
              </div>
              <div className="space-y-2">
                <Label>Forward Validation (days)</Label>
                <Select defaultValue="30">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7">7 days</SelectItem>
                    <SelectItem value="14">14 days</SelectItem>
                    <SelectItem value="30">30 days</SelectItem>
                    <SelectItem value="60">60 days</SelectItem>
                    <SelectItem value="90">90 days</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Frequency</Label>
                <Select defaultValue="weekly">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Benchmark</Label>
                <Select defaultValue="SPY">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="SPY">SPY (S&P 500)</SelectItem>
                    <SelectItem value="QQQ">QQQ (Nasdaq 100)</SelectItem>
                    <SelectItem value="000300.SH">CSI 300</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button className="w-full">
                  <Play className="mr-2 h-4 w-4" />
                  Run Backtest
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {hasRun && (
          <div className="space-y-6">
            {/* Summary Metrics */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Predictions</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {result.summary.total_predictions}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Accuracy</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {result.summary.accuracy_pct}%
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Cumulative Return</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent(result.summary.cumulative_return_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>vs Benchmark</CardDescription>
                  <CardTitle className="text-2xl font-mono text-green-500">
                    {formatPercent(result.summary.excess_return_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Information Ratio</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {result.summary.information_ratio.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Sharpe Ratio</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {result.summary.sharpe_ratio.toFixed(2)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Benchmark Return</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {formatPercent(result.summary.benchmark_return_pct)}
                  </CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Correct / Total</CardDescription>
                  <CardTitle className="text-2xl font-mono">
                    {correctCount}/{total}
                  </CardTitle>
                </CardHeader>
              </Card>
            </div>

            {/* Chart Placeholder */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Prediction Timeline</CardTitle>
                <CardDescription>
                  Green = correct, Red = wrong, dot size = confidence
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center bg-muted/30 rounded-lg">
                  <div className="text-center">
                    <TrendingUp className="h-10 w-10 mx-auto mb-2 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      Prediction timeline chart with TradingView Lightweight Charts
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Tabs: Breakdown + Confusion Matrix */}
            <Tabs defaultValue="breakdown">
              <TabsList>
                <TabsTrigger value="breakdown">
                  <BarChart3 className="mr-2 h-4 w-4" />
                  Per-Period Breakdown
                </TabsTrigger>
                <TabsTrigger value="confusion">
                  <BarChart3 className="mr-2 h-4 w-4" />
                  Confusion Matrix
                </TabsTrigger>
              </TabsList>

              <TabsContent value="breakdown" className="mt-4">
                <Card>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Ticker</TableHead>
                        <TableHead>Predicted</TableHead>
                        <TableHead className="text-right">Confidence</TableHead>
                        <TableHead>Actual</TableHead>
                        <TableHead className="text-right">Return</TableHead>
                        <TableHead className="text-right">Benchmark</TableHead>
                        <TableHead className="text-center">Correct</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {result.results.map((r, i) => (
                        <TableRow key={i}>
                          <TableCell className="text-sm">{r.date}</TableCell>
                          <TableCell className="font-mono font-bold">
                            ${r.ticker}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{r.predicted_direction}</Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm">
                            {(r.confidence * 100).toFixed(0)}%
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{r.actual_direction}</Badge>
                          </TableCell>
                          <TableCell
                            className={`text-right font-mono text-sm ${
                              r.actual_return_pct >= 0
                                ? "text-green-500"
                                : "text-red-500"
                            }`}
                          >
                            {formatPercent(r.actual_return_pct)}
                          </TableCell>
                          <TableCell className="text-right font-mono text-sm text-muted-foreground">
                            {formatPercent(r.benchmark_return_pct)}
                          </TableCell>
                          <TableCell className="text-center">
                            {r.was_correct ? (
                              <CheckCircle2 className="h-4 w-4 text-green-500 mx-auto" />
                            ) : (
                              <XCircle className="h-4 w-4 text-red-500 mx-auto" />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              </TabsContent>

              <TabsContent value="confusion" className="mt-4">
                <Card>
                  <CardContent className="pt-6">
                    <div className="max-w-md mx-auto">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-20" />
                            <TableHead className="text-center">Pred Bullish</TableHead>
                            <TableHead className="text-center">Pred Bearish</TableHead>
                            <TableHead className="text-center">Pred Neutral</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">Actual Bullish</TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-green-500/20 text-green-500 font-mono font-bold">
                                2
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-red-500/20 text-red-500 font-mono">
                                1
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-muted font-mono text-muted-foreground">
                                0
                              </span>
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Actual Bearish</TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-red-500/20 text-red-500 font-mono">
                                1
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-green-500/20 text-green-500 font-mono font-bold">
                                1
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-muted font-mono text-muted-foreground">
                                0
                              </span>
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Actual Neutral</TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-muted font-mono text-muted-foreground">
                                0
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-muted font-mono text-muted-foreground">
                                0
                              </span>
                            </TableCell>
                            <TableCell className="text-center">
                              <span className="inline-flex items-center justify-center h-8 w-12 rounded bg-muted font-mono text-muted-foreground">
                                0
                              </span>
                            </TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                      <p className="text-center text-sm text-muted-foreground mt-4">
                        Accuracy: {accuracy}% ({correctCount}/{total})
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>

            {/* Export */}
            <div className="flex gap-3">
              <Button variant="outline">
                <Download className="mr-2 h-4 w-4" />
                Export CSV
              </Button>
              <Button variant="outline">
                <Download className="mr-2 h-4 w-4" />
                Export PDF Report
              </Button>
            </div>
          </div>
        )}
      </div>
    </Shell>
  );
}
