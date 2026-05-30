"use client";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { ConfidenceBar, DirectionBadge } from "@/components/shared/badges";
import {
  formatCurrency,
  formatPercent,
  formatDate,
} from "@/lib/utils";
import {
  Brain,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  AlertTriangle,
  Plus,
  Search,
  Clock,
  CheckCircle2,
  XCircle,
  HelpCircle,
  BarChart3,
  History,
  BookOpen,
  FlaskConical,
} from "lucide-react";

const MOCK_MEMORIES = [
  {
    id: "m1",
    ticker: "AAPL",
    action: "BUY",
    direction: "Bullish",
    outcome_quality: 0.85,
    owm_score: 0.78,
    episodic: "Bought AAPL at $185 on RSI(14)=32 signal with positive news sentiment. Sold at $192 (+3.8%).",
    created_at: "2026-05-15T10:30:00Z",
  },
  {
    id: "m2",
    ticker: "NVDA",
    action: "BUY",
    direction: "Bullish",
    outcome_quality: 0.92,
    owm_score: 0.85,
    episodic: "Bought NVDA at $880 after earnings beat. Strong AI demand narrative. Sold at $950 (+7.9%).",
    created_at: "2026-05-10T10:30:00Z",
  },
  {
    id: "m3",
    ticker: "TSLA",
    action: "SELL",
    direction: "Bearish",
    outcome_quality: -0.45,
    owm_score: -0.35,
    episodic: "Shorted TSLA at $250 on overbought signal, but rallied to $265. Stopped out (-6%).",
    created_at: "2026-04-28T10:30:00Z",
  },
];

const MOCK_REFLECTIONS = [
  {
    id: "r1",
    period_start: "2026-05-19",
    period_end: "2026-05-25",
    total_trades: 6,
    win_rate_pct: 66.7,
    avg_return_pct: 2.1,
    max_drawdown_pct: -4.2,
    strategy_decay_detected: false,
    recommendations: ["Keep current position sizing", "Monitor tech sector correlation"],
    generated_at: "2026-05-25T18:00:00Z",
  },
  {
    id: "r2",
    period_start: "2026-05-12",
    period_end: "2026-05-18",
    total_trades: 5,
    win_rate_pct: 40.0,
    avg_return_pct: -0.8,
    max_drawdown_pct: -8.5,
    strategy_decay_detected: true,
    decay_indicators: ["declining win rate", "increasing drawdown"],
    recommendations: ["Reduce position size by 25%", "Add volatility filter to entry conditions"],
    generated_at: "2026-05-18T18:00:00Z",
  },
];

const MOCK_KNOWLEDGE = [
  { id: "k1", type: "rule" as const, title: "RSI(14) < 30 + positive news → BUY signal >60% win rate", confidence: 0.9 },
  { id: "k2", type: "finding" as const, title: "AAPL typically rallies 2-3% in the week after earnings beats", confidence: 0.75 },
  { id: "k3", type: "failure" as const, title: "Shorting on RSI > 70 alone without news confirmation is unreliable", confidence: 0.85 },
];

const MOCK_HYPOTHESES = [
  {
    id: "h1",
    claim: "RSI(14) < 30 combined with positive news sentiment produces >60% win rate",
    status: "active" as const,
    budget_rounds: 20,
    completed_rounds: 12,
    acceptance_criteria: "Win rate > 60% over at least 20 trades",
  },
  {
    id: "h2",
    claim: "MACD crossover signals are more reliable in trending markets than ranging markets",
    status: "validating" as const,
    budget_rounds: 15,
    completed_rounds: 3,
    acceptance_criteria: "Signal accuracy > 55% in trending vs < 45% in ranging",
  },
  {
    id: "h3",
    claim: "Adding volume confirmation to entry signals reduces false positives by 30%",
    status: "rejected" as const,
    budget_rounds: 10,
    completed_rounds: 10,
    acceptance_criteria: "False positive rate reduced by >= 30%",
  },
];

export default function MemoryLabPage() {
  return (
    <Shell>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Brain className="h-5 w-5" />
              Memory Lab
            </h2>
            <p className="text-sm text-muted-foreground">
              Strategy learning hub — OWM memories, reflections, knowledge base, and hypotheses.
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

        <Tabs defaultValue="memories" className="space-y-4">
          <TabsList>
            <TabsTrigger value="memories">
              <History className="mr-2 h-4 w-4" />
              Memories
            </TabsTrigger>
            <TabsTrigger value="reflections">
              <BarChart3 className="mr-2 h-4 w-4" />
              Reflections
            </TabsTrigger>
            <TabsTrigger value="knowledge">
              <BookOpen className="mr-2 h-4 w-4" />
              Knowledge Base
            </TabsTrigger>
            <TabsTrigger value="hypotheses">
              <FlaskConical className="mr-2 h-4 w-4" />
              Hypotheses
            </TabsTrigger>
          </TabsList>

          {/* Memories Tab */}
          <TabsContent value="memories" className="space-y-4">
            {/* OWM Score Distribution Placeholder */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">OWM Score Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-40 flex items-center justify-center bg-muted/30 rounded-lg">
                  <p className="text-sm text-muted-foreground">
                    Histogram chart will render here
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Memories Table */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Recent Memories</CardTitle>
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                      <Input placeholder="Filter by ticker..." className="pl-8 h-8 w-40 text-xs" />
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ticker</TableHead>
                      <TableHead>Direction</TableHead>
                      <TableHead>OWM Score</TableHead>
                      <TableHead>Outcome Quality</TableHead>
                      <TableHead>Episode</TableHead>
                      <TableHead>Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {MOCK_MEMORIES.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell className="font-mono font-bold">
                          ${m.ticker}
                        </TableCell>
                        <TableCell>
                          <DirectionBadge direction={m.direction} />
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span
                              className={`font-mono text-sm ${
                                m.owm_score >= 0
                                  ? "text-green-500"
                                  : "text-red-500"
                              }`}
                            >
                              {m.owm_score.toFixed(2)}
                            </span>
                            <ConfidenceBar value={Math.abs(m.owm_score)} />
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          <span
                            className={
                              m.outcome_quality >= 0
                                ? "text-green-500"
                                : "text-red-500"
                            }
                          >
                            {formatPercent(m.outcome_quality * 100)}
                          </span>
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground max-w-[300px] truncate">
                          {m.episodic}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {formatDate(m.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Reflections Tab */}
          <TabsContent value="reflections" className="space-y-4">
            {/* Strategy Health */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Strategy Health Monitor</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-40 flex items-center justify-center bg-muted/30 rounded-lg">
                  <div className="text-center">
                    <TrendingUp className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      Win rate trend chart will render here
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Reflection Cards */}
            {MOCK_REFLECTIONS.map((ref) => (
              <Card
                key={ref.id}
                className={ref.strategy_decay_detected ? "border-destructive/50" : ""}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">
                        {ref.period_start} → {ref.period_end}
                      </CardTitle>
                      {ref.strategy_decay_detected && (
                        <Badge variant="destructive">
                          <AlertTriangle className="mr-1 h-3 w-3" />
                          Decay Detected
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      Generated {formatDate(ref.generated_at)}
                    </span>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
                    <div>
                      <span className="text-xs text-muted-foreground">Trades</span>
                      <p className="font-mono font-bold">{ref.total_trades}</p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">Win Rate</span>
                      <p className="font-mono font-bold">{ref.win_rate_pct}%</p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">Avg Return</span>
                      <p
                        className={`font-mono font-bold ${
                          ref.avg_return_pct >= 0 ? "text-green-500" : "text-red-500"
                        }`}
                      >
                        {formatPercent(ref.avg_return_pct)}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">Max Drawdown</span>
                      <p className="font-mono font-bold text-red-500">
                        {formatPercent(ref.max_drawdown_pct)}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-muted-foreground">Status</span>
                      <Badge
                        variant={ref.strategy_decay_detected ? "destructive" : "default"}
                      >
                        {ref.strategy_decay_detected ? "Unhealthy" : "Healthy"}
                      </Badge>
                    </div>
                  </div>
                  {ref.decay_indicators && ref.decay_indicators.length > 0 && (
                    <div className="mb-3">
                      <span className="text-xs text-muted-foreground">
                        Decay Indicators:
                      </span>
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {ref.decay_indicators.map((d, i) => (
                          <Badge key={i} variant="outline" className="text-xs">
                            {d}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    <span className="text-xs text-muted-foreground">
                      Recommendations:
                    </span>
                    <ul className="list-disc list-inside mt-1">
                      {ref.recommendations.map((r, i) => (
                        <li key={i} className="text-xs">{r}</li>
                      ))}
                    </ul>
                  </div>
                </CardContent>
              </Card>
            ))}
          </TabsContent>

          {/* Knowledge Base Tab */}
          <TabsContent value="knowledge" className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="flex gap-2">
                <Button variant="outline" size="sm">All</Button>
                <Button variant="outline" size="sm" className="text-green-500">Rules</Button>
                <Button variant="outline" size="sm" className="text-blue-500">Findings</Button>
                <Button variant="outline" size="sm" className="text-red-500">Failures</Button>
              </div>
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" />
                Add Entry
              </Button>
            </div>

            <div className="space-y-3">
              {MOCK_KNOWLEDGE.map((k) => (
                <Card key={k.id}>
                  <CardContent className="pt-4">
                    <div className="flex items-start gap-3">
                      <span>
                        {k.type === "rule" ? (
                          <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
                        ) : k.type === "finding" ? (
                          <Lightbulb className="h-4 w-4 text-blue-500 mt-0.5" />
                        ) : (
                          <XCircle className="h-4 w-4 text-red-500 mt-0.5" />
                        )}
                      </span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge
                            variant="outline"
                            className={
                              k.type === "rule"
                                ? "text-green-500 border-green-500/20"
                                : k.type === "finding"
                                ? "text-blue-500 border-blue-500/20"
                                : "text-red-500 border-red-500/20"
                            }
                          >
                            {k.type}
                          </Badge>
                          <span className="text-sm font-medium">{k.title}</span>
                        </div>
                        <div className="flex items-center gap-2 mt-2">
                          <span className="text-xs text-muted-foreground">
                            Confidence:
                          </span>
                          <ConfidenceBar value={k.confidence} />
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Hypotheses Tab */}
          <TabsContent value="hypotheses" className="space-y-4">
            <div className="flex justify-between items-center">
              <p className="text-sm text-muted-foreground">
                Testable trading hypotheses with evidence tracking.
              </p>
              <Button size="sm">
                <Plus className="mr-2 h-4 w-4" />
                New Hypothesis
              </Button>
            </div>

            {MOCK_HYPOTHESES.map((h) => (
              <Card key={h.id}>
                <CardContent className="pt-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <FlaskConical className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium">{h.claim}</span>
                      </div>
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <Badge
                          variant={
                            h.status === "active"
                              ? "default"
                              : h.status === "rejected"
                              ? "destructive"
                              : "secondary"
                          }
                          className="text-xs"
                        >
                          {h.status}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          Progress: {h.completed_rounds}/{h.budget_rounds} rounds
                        </span>
                        <span className="text-xs text-muted-foreground">
                          | Criteria: {h.acceptance_criteria}
                        </span>
                      </div>
                      <div className="mt-2">
                        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary transition-all"
                            style={{
                              width: `${(h.completed_rounds / h.budget_rounds) * 100}%`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </TabsContent>
        </Tabs>
      </div>
    </Shell>
  );
}
