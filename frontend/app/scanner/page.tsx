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
import { Button, buttonVariants } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { EmptyState } from "@/components/shared/empty-state";
import { formatPercent } from "@/lib/utils";
import { Search, Plus, Trash2, BarChart3, Brain, Bot } from "lucide-react";

const MOCK_RESULTS = [
  {
    ticker: "AAPL",
    price: 192.45,
    change_pct: 1.25,
    rsi14: 52.3,
    pe_ratio: 30.5,
    market_cap: "2.8T",
    matched_conditions: ["RSI(14) < 70", "PE > 15"],
    explanation: "Moderate technicals, reasonable valuation for tech",
  },
  {
    ticker: "MSFT",
    price: 445.30,
    change_pct: 0.85,
    rsi14: 48.7,
    pe_ratio: 37.2,
    market_cap: "3.3T",
    matched_conditions: ["RSI(14) < 70", "PE > 15"],
    explanation: "Strong fundamentals, neutral technical setup",
  },
  {
    ticker: "INTC",
    price: 22.15,
    change_pct: -3.20,
    rsi14: 28.5,
    pe_ratio: 12.8,
    market_cap: "95B",
    matched_conditions: ["RSI(14) < 30", "PE < 15"],
    explanation: "Oversold with low PE — potential value play",
  },
];

export default function ScannerPage() {
  const [mode, setMode] = useState<"rule" | "agent" | "belief">("rule");
  const [hasScanned, setHasScanned] = useState(true);

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Search className="h-5 w-5" />
            Market Scanner
          </h2>
          <p className="text-sm text-muted-foreground">
            Screen the market with rule-based filters, natural language, or belief-driven queries.
          </p>
        </div>

        {/* Mode Selector */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 mb-4">
              <Button
                variant={mode === "rule" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("rule")}
              >
                <BarChart3 className="mr-2 h-4 w-4" />
                Rule-Based
              </Button>
              <Button
                variant={mode === "agent" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("agent")}
              >
                <Bot className="mr-2 h-4 w-4" />
                Agent-Driven
              </Button>
              <Button
                variant={mode === "belief" ? "default" : "outline"}
                size="sm"
                onClick={() => setMode("belief")}
              >
                <Brain className="mr-2 h-4 w-4" />
                Belief-Driven
              </Button>
            </div>

            {mode === "rule" && (
              <div className="space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Field</Label>
                    <Select defaultValue="rsi14">
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="rsi14">RSI(14)</SelectItem>
                        <SelectItem value="pe_ratio">PE Ratio</SelectItem>
                        <SelectItem value="market_cap">Market Cap</SelectItem>
                        <SelectItem value="volume">Volume</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Operator</Label>
                    <Select defaultValue="<">
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="<">{"<"}</SelectItem>
                        <SelectItem value=">">{">"}</SelectItem>
                        <SelectItem value="<=">{"<="}</SelectItem>
                        <SelectItem value=">=">{">="}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Value</Label>
                    <Input defaultValue="30" />
                  </div>
                  <div className="flex items-end">
                    <Button variant="outline" size="sm" className="w-full">
                      <Plus className="mr-1 h-3 w-3" />
                      Add Condition
                    </Button>
                  </div>
                </div>
                <div className="flex gap-3">
                  <Select defaultValue="sp500">
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sp500">S&P 500</SelectItem>
                      <SelectItem value="nasdaq100">Nasdaq 100</SelectItem>
                      <SelectItem value="csi300">CSI 300</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button>Scan</Button>
                </div>
              </div>
            )}

            {mode === "agent" && (
              <div className="space-y-3">
                <Input
                  placeholder='Describe what you want to find, e.g. "Find tech stocks with negative news but strong fundamentals"'
                  className="h-12"
                />
                <div className="flex gap-3">
                  <Select defaultValue="nasdaq100">
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sp500">S&P 500</SelectItem>
                      <SelectItem value="nasdaq100">Nasdaq 100</SelectItem>
                      <SelectItem value="csi300">CSI 300</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button>Scan with AI</Button>
                </div>
              </div>
            )}

            {mode === "belief" && (
              <div className="space-y-3">
                <Select defaultValue="belief-1">
                  <SelectTrigger className="max-w-md">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="belief-1">聚焦科技股动量</SelectItem>
                    <SelectItem value="belief-2">偏好低估值蓝筹</SelectItem>
                    <SelectItem value="belief-3">关注短期事件驱动</SelectItem>
                  </SelectContent>
                </Select>
                <div className="flex gap-3">
                  <Select defaultValue="sp500">
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sp500">S&P 500</SelectItem>
                      <SelectItem value="nasdaq100">Nasdaq 100</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button>Scan with Belief</Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Results */}
        {hasScanned && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                Results ({MOCK_RESULTS.length} matches)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Ticker</TableHead>
                    <TableHead className="text-right">Price</TableHead>
                    <TableHead className="text-right">Change</TableHead>
                    <TableHead className="text-right">RSI(14)</TableHead>
                    <TableHead className="text-right">PE</TableHead>
                    <TableHead>Market Cap</TableHead>
                    <TableHead>Matched</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {MOCK_RESULTS.map((r) => (
                    <TableRow key={r.ticker}>
                      <TableCell className="font-mono font-bold">
                        ${r.ticker}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {r.price.toFixed(2)}
                      </TableCell>
                      <TableCell
                        className={`text-right font-mono ${
                          r.change_pct >= 0 ? "text-green-500" : "text-red-500"
                        }`}
                      >
                        {formatPercent(r.change_pct)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {r.rsi14}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {r.pe_ratio}
                      </TableCell>
                      <TableCell className="font-mono">{r.market_cap}</TableCell>
                      <TableCell>
                        <div className="flex gap-1 flex-wrap">
                          {r.matched_conditions.map((c, i) => (
                            <Badge key={i} variant="secondary" className="text-xs">
                              {c}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        )}
      </div>
    </Shell>
  );
}
