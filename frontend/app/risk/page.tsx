"use client";

import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/shared/empty-state";
import { formatPercent, formatCurrency } from "@/lib/utils";
import {
  Shield,
  TrendingDown,
  BarChart3,
  AlertTriangle,
  Activity,
  PieChart,
} from "lucide-react";

const MOCK_VAR = {
  var_95: -0.023,
  cvar_95: -0.031,
  var_99: -0.045,
  method: "historical",
  lookback_days: 252,
};

const MOCK_STRESS = [
  { scenario: "2008 Financial Crisis", impact_pct: -35.2, description: "S&P 500 dropped 57% peak-to-trough" },
  { scenario: "2020 COVID Crash", impact_pct: -28.7, description: "S&P 500 dropped 34% in 23 trading days" },
  { scenario: "2022 Rate Hikes", impact_pct: -15.3, description: "S&P 500 dropped 25% as Fed hiked 425bps" },
  { scenario: "Custom: -10% Market + VIX 40", impact_pct: -8.5, description: "Market shock: -10%, VIX spike to 40, rates +100bps" },
];

const MOCK_CORRELATION = [
  ["AAPL", 1.00, 0.72, 0.58, 0.45, 0.35],
  ["MSFT", 0.72, 1.00, 0.65, 0.42, 0.38],
  ["NVDA", 0.58, 0.65, 1.00, 0.38, 0.30],
  ["SPY", 0.45, 0.42, 0.38, 1.00, 0.62],
  ["BND", 0.35, 0.38, 0.30, 0.62, 1.00],
];

const MOCK_CONCENTRATION = [
  { sector: "Technology", weight_pct: 52.3, tickers: ["AAPL", "MSFT", "NVDA"] },
  { sector: "Financials", weight_pct: 18.5, tickers: ["JPM", "BAC"] },
  { sector: "Energy", weight_pct: 12.2, tickers: ["XOM"] },
  { sector: "Consumer", weight_pct: 10.8, tickers: ["AMZN", "WMT"] },
  { sector: "Cash", weight_pct: 6.2, tickers: [] },
];

export default function RiskPage() {
  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Risk Analytics
            </h2>
            <p className="text-sm text-muted-foreground">
              VaR, stress testing, correlation, and concentration analysis.
            </p>
          </div>
          <Select defaultValue="tech-momentum">
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tech-momentum">Tech Momentum</SelectItem>
              <SelectItem value="value-hunter">Value Hunter</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* VaR/CVaR */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Activity className="h-4 w-4" />
                VaR / CVaR
                <Badge variant="outline" className="text-xs">
                  {MOCK_VAR.method} · {MOCK_VAR.lookback_days}d lookback
                </Badge>
              </CardTitle>
              <CardDescription>
                Value at Risk — historical simulation method
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-48 flex items-center justify-center bg-muted/30 rounded-lg mb-4">
                <div className="text-center">
                  <BarChart3 className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Return distribution histogram with VaR lines
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">VaR 95%</p>
                  <p className="text-lg font-mono font-bold text-red-500">
                    {formatPercent(MOCK_VAR.var_95 * 100)}
                  </p>
                  <p className="text-xs text-muted-foreground">1-day</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">CVaR 95%</p>
                  <p className="text-lg font-mono font-bold text-red-500">
                    {formatPercent(MOCK_VAR.cvar_95 * 100)}
                  </p>
                  <p className="text-xs text-muted-foreground">Expected shortfall</p>
                </div>
                <div className="text-center p-3 rounded-lg bg-muted/50">
                  <p className="text-xs text-muted-foreground mb-1">VaR 99%</p>
                  <p className="text-lg font-mono font-bold text-red-500">
                    {formatPercent(MOCK_VAR.var_99 * 100)}
                  </p>
                  <p className="text-xs text-muted-foreground">Tail risk</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Stress Test */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Stress Test
              </CardTitle>
              <CardDescription>
                Estimated portfolio impact under historical and custom scenarios.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {MOCK_STRESS.map((s, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                  >
                    <div>
                      <p className="text-sm font-medium">{s.scenario}</p>
                      <p className="text-xs text-muted-foreground">
                        {s.description}
                      </p>
                    </div>
                    <Badge
                      variant={
                        s.impact_pct < -20
                          ? "destructive"
                          : s.impact_pct < -10
                          ? "secondary"
                          : "outline"
                      }
                      className="font-mono text-sm"
                    >
                      {formatPercent(s.impact_pct)}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Correlation + Concentration */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Correlation */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Correlation Matrix
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-16" />
                      {MOCK_CORRELATION.map((row, i) => (
                        <TableHead key={i} className="text-center font-mono text-xs">
                          {row[0]}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {MOCK_CORRELATION.map((row, i) => (
                      <TableRow key={i}>
                        <TableCell className="font-mono font-bold text-xs">
                          {row[0]}
                        </TableCell>
                        {(row.slice(1) as number[]).map((val, j) => {
                          const intensity =
                            val === 1
                              ? "bg-muted/50"
                              : Math.abs(val) > 0.6
                              ? val > 0
                                ? "bg-red-500/20 text-red-500"
                                : "bg-green-500/20 text-green-500"
                              : Math.abs(val) > 0.4
                              ? val > 0
                                ? "bg-yellow-500/10 text-yellow-600"
                                : "bg-green-500/10 text-green-500"
                              : "text-muted-foreground";
                          return (
                            <TableCell
                              key={j}
                              className={`text-center font-mono text-sm ${intensity}`}
                            >
                              {val.toFixed(2)}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Concentration */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <PieChart className="h-4 w-4" />
                Sector Concentration
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-48 flex items-center justify-center bg-muted/30 rounded-lg mb-4">
                <div className="text-center">
                  <PieChart className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">
                    Pie chart will render here
                  </p>
                </div>
              </div>
              <div className="space-y-2">
                {MOCK_CONCENTRATION.map((s, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-sm font-medium w-24">{s.sector}</span>
                    <div className="flex-1 h-3 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${s.weight_pct}%` }}
                      />
                    </div>
                    <span className="text-sm font-mono w-14 text-right">
                      {s.weight_pct}%
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {s.tickers.join(", ")}
                    </span>
                  </div>
                ))}
              </div>
              {/* Warning for overconcentration */}
              {MOCK_CONCENTRATION.some((s) => s.weight_pct > 50) && (
                <div className="mt-4 p-3 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
                  <p className="text-xs text-destructive">
                    Technology sector exceeds 50% concentration — consider rebalancing.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Drawdown */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Drawdown Curve
            </CardTitle>
            <CardDescription>
              Historical drawdown with peak-to-trough annotations.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-64 flex items-center justify-center bg-muted/30 rounded-lg">
              <div className="text-center">
                <TrendingDown className="h-10 w-10 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Drawdown chart will render here with TradingView Lightweight Charts
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
