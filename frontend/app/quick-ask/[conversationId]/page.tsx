"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";
import { ActionBadge, DirectionBadge } from "@/components/shared/badges";
import { analyzeApi } from "@/lib/api/analyze";
import { formatDateTime } from "@/lib/utils";
import type { AnalysisSessionSnapshot } from "@/lib/types/models";
import { ArrowLeft, Loader2, Clock, Zap } from "lucide-react";
import { Markdown } from "@/components/markdown";

function parseReport(report: string) {
  const lines = report.split("\n");
  const result: Record<string, string> = {};
  let bodyStart = 0;
  for (let i = 0; i < Math.min(lines.length, 8); i++) {
    const line = lines[i].trim();
    const m = line.match(
      /^(方向|时间范围|置信度|一句话结论)[：:]\s*(.+)/,
    );
    if (m) {
      const keyMap: Record<string, string> = {
        "方向": "direction",
        "时间范围": "timeframe",
        "置信度": "confidence",
        "一句话结论": "oneliner",
      };
      result[keyMap[m[1]] || m[1]] = m[2];
      bodyStart = i + 1;
    } else if (line === "" && bodyStart > 0) {
      bodyStart = i + 1;
      break;
    }
  }
  result.body = lines.slice(bodyStart).join("\n").trim();
  return result;
}

export default function HistoryDetailPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const router = useRouter();
  const [session, setSession] = useState<AnalysisSessionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!conversationId) return;
    setLoading(true);
    analyzeApi
      .getHistory(conversationId)
      .then(setSession)
      .catch((err) => setError(String(err)))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    if (!conversationId || session?.status !== "running") return;

    const interval = window.setInterval(() => {
      analyzeApi
        .getHistory(conversationId)
        .then(setSession)
        .catch(() => {});
    }, 2000);

    return () => window.clearInterval(interval);
  }, [conversationId, session?.status]);

  if (loading) {
    return (
      <Shell>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      </Shell>
    );
  }

  if (error || !session) {
    return (
      <Shell>
        <div className="p-6 max-w-6xl mx-auto">
          <Button variant="ghost" onClick={() => router.back()} className="mb-4">
            <ArrowLeft className="mr-2 h-4 w-4" /> Back
          </Button>
          <Card className="border-destructive">
            <CardHeader>
              <CardTitle className="text-destructive">
                Session Not Found
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {error || "This analysis session could not be loaded."}
              </p>
            </CardContent>
          </Card>
        </div>
      </Shell>
    );
  }

  const result = session.result;
  const parsed = result?.report ? parseReport(result.report) : null;
  const oneliner = parsed?.oneliner || "";
  const bodyText = parsed?.body || result?.report || "";
  const confidence = result?.confidence ?? 0.5;
  const confidencePct = Math.round(confidence * 100);
  const strategyId = session.request.strategy_id ?? result?.strategy_id ?? "default";
  const strategyLabel = strategyId === "default" ? "Default" : strategyId;
  const barColor =
    confidencePct >= 70
      ? "bg-green-500"
      : confidencePct >= 40
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <Shell>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        {/* Back + Header */}
        <div className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:gap-4">
          <Button variant="ghost" size="sm" onClick={() => router.back()}>
            <ArrowLeft className="mr-1 h-4 w-4" /> Back
          </Button>
          <div className="min-w-0">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Zap className="h-5 w-5" />
              {session.ticker} Analysis
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="text-xs">
                {session.mode}
              </Badge>
              <Badge
                variant="outline"
                className="max-w-full text-xs"
                title={`Strategy: ${strategyLabel}`}
              >
                Strategy: <span className="ml-1 truncate font-mono">{strategyLabel}</span>
              </Badge>
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatDateTime(session.created_at)}
              </span>
              {result?.elapsed_s != null && (
                <span className="text-xs text-muted-foreground">
                  · {result.elapsed_s}s
                </span>
              )}
              <Badge variant="secondary" className="text-xs">
                {session.status}
              </Badge>
            </div>
          </div>
        </div>

        {session.status === "running" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" />
                Analysis Running
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {session.progress_events.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Waiting for analysis progress.
                </p>
              ) : (
                session.progress_events.map((event) => (
                  <div
                    key={`${event.agent}-${event.status}-${event.timestamp ?? event.report ?? ""}`}
                    className="rounded-lg bg-muted/40 p-3 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">
                        {event.agent.replace(/_/g, " ")}
                      </span>
                      <Badge variant="outline" className="text-[10px]">
                        {event.status}
                      </Badge>
                    </div>
                    {event.report && (
                      <div className="mt-2 line-clamp-3 text-xs text-muted-foreground">
                        {event.report}
                      </div>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        )}

        {session.status === "failed" && (
          <Card className="border-destructive">
            <CardHeader>
              <CardTitle className="text-base text-destructive">
                Analysis Failed
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm">{session.error || "Analysis failed."}</p>
            </CardContent>
          </Card>
        )}

        {/* Result Card */}
        {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Analysis Result</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Badge Row */}
            <div className="flex items-center gap-3 flex-wrap">
              <ActionBadge action={result.action} />
              <DirectionBadge direction={result.direction} />
              {result.timeframe && (
                <Badge variant="outline">{result.timeframe}</Badge>
              )}
            </div>

            {/* Confidence Bar */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Confidence</span>
                <span className="font-mono font-bold">{confidencePct}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${confidencePct}%` }}
                />
              </div>
            </div>

            {/* One-liner */}
            {oneliner && (
              <div className="p-3 rounded-lg bg-primary/5 border border-primary/10">
                <p className="text-sm font-medium">{oneliner}</p>
              </div>
            )}

            {/* Full report */}
            {bodyText && (
              <ScrollArea className="max-h-96">
                <div className="p-4 rounded-lg bg-muted/30 text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
                  <Markdown>{bodyText}</Markdown>
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
        )}

        {/* Agent Reports */}
        {result?.agent_reports &&
          Object.keys(result.agent_reports).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Agent Reports</CardTitle>
              </CardHeader>
              <CardContent>
                <Accordion>
                  {Object.entries(result.agent_reports).map(
                    ([agent, report]) => (
                      <AccordionItem key={agent} value={agent}>
                        <AccordionTrigger>
                          <span className="text-xs font-mono text-muted-foreground mr-2">
                            {agent.replace(/_/g, " ")}
                          </span>
                        </AccordionTrigger>
                        <AccordionContent>
                          <div className="p-3 rounded-lg bg-muted/20 text-xs leading-relaxed max-h-80 overflow-y-auto prose prose-sm dark:prose-invert max-w-none">
                            <Markdown>{report}</Markdown>
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    ),
                  )}
                </Accordion>
              </CardContent>
            </Card>
          )}

        {/* News Sources */}
        {result?.news_articles && result.news_articles.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">
                News Sources ({result.news_articles.length})
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {result.news_articles.map((a, i) => (
                  <div
                    key={`${a.url}-${a.published_at}`}
                    className="flex items-start gap-2 text-sm"
                  >
                    <span className="text-muted-foreground shrink-0 mt-0.5">
                      {i + 1}.
                    </span>
                    <div className="min-w-0">
                      <a
                        href={a.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary hover:underline truncate block"
                      >
                        {a.title}
                      </a>
                      <div className="text-xs text-muted-foreground">
                        {a.source}
                        {a.published_at
                          ? ` · ${a.published_at.slice(0, 10)}`
                          : ""}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </Shell>
  );
}
