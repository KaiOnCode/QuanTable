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
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { EmptyState } from "@/components/shared/empty-state";
import { DirectionBadge, ActionBadge } from "@/components/shared/badges";
import { formatCurrency, formatPercent, formatDateTime } from "@/lib/utils";
import {
  CheckSquare,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Shield,
  Eye,
  ThumbsUp,
  ThumbsDown,
  Edit3,
} from "lucide-react";

const MOCK_PENDING = [
  {
    id: "a1",
    strategy_name: "Tech Momentum",
    ticker: "NVDA",
    decision: {
      action: "BUY",
      direction: "Bullish",
      confidence: 0.82,
      target_position_pct: 25.0,
      report: "NVDA showing strong momentum post-GTC. AI demand accelerating. Adding to existing position.",
    },
    triggered_rules: ["Position size change > 20%", "Single ticker concentration > 25%"],
    cross_review_consensus: true,
    cross_review_result: "Agree. Strong fundamentals support the bullish thesis. However, note elevated valuation risk.",
    created_at: "2026-05-28T09:35:00Z",
    timeout_at: "2026-05-28T12:35:00Z",
    urgency: "high" as const,
  },
  {
    id: "a2",
    strategy_name: "Value Hunter",
    ticker: "XOM",
    decision: {
      action: "SELL",
      direction: "Bearish",
      confidence: 0.68,
      target_position_pct: 0,
      report: "Oil demand forecasts weakening. Technical breakdown below 200-day MA. Reduce to zero.",
    },
    triggered_rules: ["Signal conflict detected", "Confidence below 0.7"],
    cross_review_consensus: false,
    cross_review_result: "Disagree. The bearish signal is driven by short-term news. Long-term energy demand fundamentals remain intact.",
    created_at: "2026-05-28T09:32:00Z",
    timeout_at: "2026-05-28T12:32:00Z",
    urgency: "medium" as const,
  },
];

const MOCK_HISTORY = [
  {
    id: "h1",
    strategy_name: "Tech Momentum",
    ticker: "AAPL",
    action: "BUY",
    status: "approved",
    reviewer: "admin",
    reviewer_notes: "Solid technical setup. Approved.",
    created_at: "2026-05-27T09:35:00Z",
    resolved_at: "2026-05-27T10:15:00Z",
  },
  {
    id: "h2",
    strategy_name: "Value Hunter",
    ticker: "JPM",
    action: "BUY",
    status: "modified",
    reviewer: "admin",
    reviewer_notes: "Reduced position size from 20% to 15% due to sector concentration.",
    created_at: "2026-05-26T09:35:00Z",
    resolved_at: "2026-05-26T10:45:00Z",
  },
  {
    id: "h3",
    strategy_name: "HITL Safe Harbor",
    ticker: "BND",
    action: "SELL",
    status: "rejected",
    reviewer: "admin",
    reviewer_notes: "Bond allocation should remain as hedge. Override.",
    created_at: "2026-05-25T09:35:00Z",
    resolved_at: "2026-05-25T11:00:00Z",
  },
];

export default function ApprovalsPage() {
  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <CheckSquare className="h-5 w-5" />
            Approvals (HITL)
          </h2>
          <p className="text-sm text-muted-foreground">
            Human-in-the-loop intervention — review, approve, or modify agent decisions.
          </p>
        </div>

        <Tabs defaultValue="pending" className="space-y-4">
          <TabsList>
            <TabsTrigger value="pending" className="gap-2">
              <Clock className="h-4 w-4" />
              Pending
              {MOCK_PENDING.length > 0 && (
                <Badge variant="destructive" className="ml-1 h-5 px-1.5 text-xs">
                  {MOCK_PENDING.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <CheckCircle2 className="h-4 w-4" />
              History
            </TabsTrigger>
          </TabsList>

          {/* Pending */}
          <TabsContent value="pending" className="space-y-4">
            {MOCK_PENDING.length === 0 ? (
              <Card>
                <CardContent className="pt-8">
                  <EmptyState
                    icon={<CheckCircle2 className="h-12 w-12" />}
                    title="No pending approvals"
                    description="All agent decisions are within risk parameters. No human review needed."
                  />
                </CardContent>
              </Card>
            ) : (
              MOCK_PENDING.map((a) => (
                <Card
                  key={a.id}
                  className={
                    a.urgency === "high"
                      ? "border-destructive/50"
                      : a.urgency === "medium"
                      ? "border-yellow-500/30"
                      : ""
                  }
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-bold font-mono text-lg">
                            ${a.ticker}
                          </span>
                          <ActionBadge action={a.decision.action} />
                          <DirectionBadge direction={a.decision.direction} />
                          {a.urgency === "high" && (
                            <Badge variant="destructive">
                              <AlertTriangle className="mr-1 h-3 w-3" />
                              High Priority
                            </Badge>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {a.strategy_name} · Confidence: {(a.decision.confidence * 100).toFixed(0)}%
                          · Target: {a.decision.target_position_pct}%
                        </p>
                      </div>
                      <div className="text-right">
                        <div className="flex items-center gap-1 text-xs text-muted-foreground mb-1">
                          <Clock className="h-3 w-3" />
                          Timeout: {formatDateTime(a.timeout_at)}
                        </div>
                        <Badge
                          variant={
                            a.cross_review_consensus ? "default" : "secondary"
                          }
                          className={
                            a.cross_review_consensus
                              ? "text-green-500 border-green-500/20"
                              : "text-yellow-500 border-yellow-500/20"
                          }
                        >
                          <Shield className="mr-1 h-3 w-3" />
                          {a.cross_review_consensus
                            ? "Cross-Review: Consensus"
                            : "Cross-Review: Divergence"}
                        </Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Decision detail */}
                    <div className="p-3 rounded-lg bg-muted/50">
                      <p className="text-xs text-muted-foreground mb-1">
                        Agent Reasoning:
                      </p>
                      <p className="text-sm">{a.decision.report}</p>
                    </div>

                    {/* Triggered rules */}
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">
                        Triggered Rules:
                      </p>
                      <div className="flex gap-1 flex-wrap">
                        {a.triggered_rules.map((r, i) => (
                          <Badge key={i} variant="outline" className="text-xs">
                            {r}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    {/* Cross-review */}
                    <div
                      className={`p-3 rounded-lg ${
                        a.cross_review_consensus
                          ? "bg-green-500/5 border border-green-500/20"
                          : "bg-yellow-500/5 border border-yellow-500/20"
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <Shield className="h-4 w-4 text-muted-foreground" />
                        <span className="text-xs font-medium">
                          Cross-Review (2nd LLM):
                        </span>
                        <Badge
                          variant="outline"
                          className={
                            a.cross_review_consensus
                              ? "text-green-500"
                              : "text-yellow-500"
                          }
                        >
                          {a.cross_review_consensus ? "Consensus" : "Divergence"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {a.cross_review_result}
                      </p>
                    </div>

                    <Separator />

                    {/* Actions */}
                    <div className="flex items-center gap-3">
                      <Button variant="default" size="sm">
                        <ThumbsUp className="mr-2 h-4 w-4" />
                        Approve
                      </Button>
                      <Button variant="destructive" size="sm">
                        <ThumbsDown className="mr-2 h-4 w-4" />
                        Reject
                      </Button>
                      <Button variant="outline" size="sm">
                        <Edit3 className="mr-2 h-4 w-4" />
                        Modify
                      </Button>
                      <Button variant="ghost" size="sm">
                        <Eye className="mr-2 h-4 w-4" />
                        View Full Context
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>

          {/* History */}
          <TabsContent value="history" className="space-y-4">
            {MOCK_HISTORY.length === 0 ? (
              <Card>
                <CardContent className="pt-8">
                  <EmptyState
                    icon={<CheckCircle2 className="h-12 w-12" />}
                    title="No approval history"
                    description="Past approvals will appear here."
                  />
                </CardContent>
              </Card>
            ) : (
              MOCK_HISTORY.map((h) => (
                <Card key={h.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold">${h.ticker}</span>
                        <ActionBadge action={h.action} />
                        <Badge
                          variant={
                            h.status === "approved"
                              ? "default"
                              : h.status === "rejected"
                              ? "destructive"
                              : "secondary"
                          }
                        >
                          {h.status}
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {formatDateTime(h.resolved_at)}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <span className="text-xs text-muted-foreground">
                          Strategy:
                        </span>{" "}
                        {h.strategy_name}
                      </div>
                      <div>
                        <span className="text-xs text-muted-foreground">
                          Reviewer:
                        </span>{" "}
                        <span className="font-medium">{h.reviewer}</span>
                      </div>
                      <div className="col-span-2">
                        <span className="text-xs text-muted-foreground">
                          Notes:
                        </span>{" "}
                        <span className="text-sm">{h.reviewer_notes}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>
        </Tabs>
      </div>
    </Shell>
  );
}
