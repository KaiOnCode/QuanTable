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
import { EmptyState } from "@/components/shared/empty-state";
import { formatDate } from "@/lib/utils";
import { Newspaper, TrendingUp, TrendingDown, Mail, MessageCircle, CheckCircle2, XCircle } from "lucide-react";

const MOCK_INSIGHTS = [
  {
    id: "i1",
    type: "morning_brief" as const,
    title: "May 28 Morning Brief",
    summary: "Tech earnings drive pre-market optimism. NVDA reports tonight.",
    content: "Asian markets mixed overnight. European futures pointing higher. Key catalysts: NVDA earnings (after close), US consumer confidence (10am ET), Fed minutes (2pm ET). Sector focus: semis running hot, financials cooling off. Watch AAPL $190 support, MSFT $440 resistance.",
    tickers_covered: ["NVDA", "AAPL", "MSFT"],
    key_events: ["NVDA Earnings After Close", "US Consumer Confidence 10am", "Fed Minutes 2pm"],
    generated_at: "2026-05-28T08:00:00Z",
    direction_correct: null,
  },
  {
    id: "i2",
    type: "midday_update" as const,
    title: "May 27 Midday Update",
    summary: "Markets flat at midday. Rotation from tech into financials.",
    content: "S&P 500 +0.1%, Nasdaq -0.3%, DJIA +0.4%. Volume below average. Financials leading on yield curve steepening. Tech taking a breather after yesterday's rally.",
    tickers_covered: ["SPY", "QQQ", "XLF"],
    key_events: ["Sector rotation observed"],
    generated_at: "2026-05-27T12:30:00Z",
    direction_correct: true,
  },
  {
    id: "i3",
    type: "morning_brief" as const,
    title: "May 27 Morning Brief",
    summary: "Futures higher after strong European PMI data. AAPL earnings beat.",
    content: "S&P 500 futures +0.5%. AAPL beat on EPS ($1.52 vs $1.50 est) and raised guidance. Tech sector expected to lead. Oil prices steady. 10Y at 4.25%.",
    tickers_covered: ["AAPL", "SPY", "QQQ"],
    key_events: ["AAPL Earnings Beat", "European PMI Strong"],
    generated_at: "2026-05-27T08:00:00Z",
    direction_correct: true,
  },
];

export default function InsightsPage() {
  const insights = MOCK_INSIGHTS;
  const checked = insights.filter((i) => i.direction_correct !== null);
  const accuracy =
    checked.length > 0
      ? ((checked.filter((i) => i.direction_correct).length / checked.length) * 100).toFixed(0)
      : "—";

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Newspaper className="h-5 w-5" />
            Daily Insights
          </h2>
          <p className="text-sm text-muted-foreground">
            Morning briefs, midday updates, and event-driven alerts sent via multiple channels.
          </p>
        </div>

        {/* Accuracy + Channel Status */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Directional Accuracy</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className="text-5xl font-bold font-mono">{accuracy}%</div>
                <div className="text-sm text-muted-foreground">
                  <p>{checked.length} checked insights</p>
                  <p className="text-green-500">
                    {checked.filter((i) => i.direction_correct).length} correct
                  </p>
                  <p className="text-red-500">
                    {checked.filter((i) => !i.direction_correct).length} incorrect
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Channel Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {[
                  { label: "Email", icon: Mail, active: true },
                  { label: "Telegram", icon: MessageCircle, active: true },
                  { label: "WeChat", icon: MessageCircle, active: false },
                  { label: "Feishu", icon: MessageCircle, active: false },
                ].map((ch) => (
                  <div key={ch.label} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <ch.icon className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{ch.label}</span>
                    </div>
                    <Badge
                      variant={ch.active ? "default" : "secondary"}
                      className={ch.active ? "text-green-500" : ""}
                    >
                      {ch.active ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Calendar placeholder */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Insight Calendar</CardTitle>
            <CardDescription>Click a day to view that day&apos;s briefs.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-40 flex items-center justify-center bg-muted/30 rounded-lg">
              <div className="text-center">
                <Newspaper className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Monthly calendar with insight dots will render here
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Insight Cards */}
        <div className="space-y-4">
          {insights.map((insight) => (
            <Card key={insight.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge
                      variant={insight.type === "morning_brief" ? "default" : "secondary"}
                    >
                      {insight.type === "morning_brief" ? "Morning" : "Midday"}
                    </Badge>
                    <CardTitle className="text-base">{insight.title}</CardTitle>
                  </div>
                  <div className="flex items-center gap-2">
                    {insight.direction_correct === true && (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    )}
                    {insight.direction_correct === false && (
                      <XCircle className="h-4 w-4 text-red-500" />
                    )}
                    <span className="text-xs text-muted-foreground">
                      {formatDate(insight.generated_at)}
                    </span>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm font-medium mb-1">{insight.summary}</p>
                <p className="text-sm text-muted-foreground mb-3">{insight.content}</p>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-muted-foreground">Covered:</span>
                  {insight.tickers_covered.map((t) => (
                    <Badge key={t} variant="outline" className="text-xs font-mono">
                      ${t}
                    </Badge>
                  ))}
                  <span className="text-xs text-muted-foreground ml-4">Events:</span>
                  {insight.key_events.map((e, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      {e}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </Shell>
  );
}
