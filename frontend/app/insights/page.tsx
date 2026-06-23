"use client";

import { useState, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
} from "@/components/ui/accordion";
import { EmptyState } from "@/components/shared/empty-state";
import { api } from "@/lib/api/client";
import { formatDateTime } from "@/lib/utils";
import type { DailyBrief } from "@/lib/types/models";
import ReactMarkdown from "react-markdown";
import {
  Loader2, RefreshCw, CheckCircle2, Globe, ExternalLink,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// Convert [N] citations to markdown links
function renderCitations(content: string, sources: any[]): string {
  if (!sources || sources.length === 0) return content;
  return content.replace(/\[(\d+)\]/g, (match, num) => {
    const idx = parseInt(num, 10);
    const src = sources.find((s: any) => s.idx === idx);
    if (src?.url) return `[${match}](${src.url})`;
    return match;
  });
}

type ProgressStep = {
  stage: string;
  status: string;
  detail: string;
};

export default function InsightsPage() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<DailyBrief | null>(null);
  const [hours24, setHours24] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressStep[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["insights"],
    queryFn: () => api.get<{ insights: DailyBrief[] }>("insights?limit=20"),
  });
  const briefs = data?.insights ?? [];

  const startGenerate = useCallback(() => {
    setGenerating(true);
    setProgress([]);
    const controller = new AbortController();
    abortRef.current = controller;

    const url = `${API_BASE}/insights/generate?hours=${hours24 ? 24 : 0}`;

    fetch(url, {
      method: "POST",
      headers: { Accept: "text/event-stream" },
      signal: controller.signal,
    })
      .then(async (resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const reader = resp.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let eventName = "message";
        let dataLines: string[] = [];

        const flush = () => {
          const dataStr = dataLines.join("\n");
          dataLines = [];
          eventName = "message";
          if (!dataStr.trim()) return;
          try {
            const payload = JSON.parse(dataStr);
            if (eventName === "progress") {
              setProgress((prev) => [...prev, payload]);
            } else if (eventName === "done") {
              setGenerating(false);
              setSelected(payload as any);
              queryClient.invalidateQueries({ queryKey: ["insights"] });
            } else if (eventName === "error") {
              setGenerating(false);
              setProgress((prev) => [...prev, { stage: "error", status: "error", detail: payload.message }]);
            }
          } catch { /* skip parse errors */ }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split(/\r?\n/);
          buffer = lines.pop() ?? "";
          for (const line of lines) {
            if (line === "") { flush(); }
            else if (line.startsWith("event:")) { eventName = line.slice(6).trim(); }
            else if (line.startsWith("data:")) { dataLines.push(line.slice(5).trimStart()); }
          }
        }
        if (dataLines.length > 0) flush();
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        setProgress((prev) => [...prev, { stage: "error", status: "error", detail: String(err) }]);
        setGenerating(false);
      });
  }, [hours24, queryClient]);

  const stageLabels: Record<string, string> = {
    start: "Initializing",
    market: "Market Data",
    news: "News Collection",
    llm: "AI Generation",
    store: "Saving",
    done: "Complete",
    error: "Error",
  };

  if (selected) {
    const sources = (selected as any).sources || (selected as any).news_sources || [];
    const allArticles = (selected as any).all_articles || [];
    // Group all articles by category
    const byCategory: Record<string, any[]> = {};
    for (const a of allArticles) {
      const cat = a.category || "other";
      if (!byCategory[cat]) byCategory[cat] = [];
      if (byCategory[cat].length < 20) byCategory[cat].push(a);
    }

    return (
      <Shell>
        <div className="p-6 max-w-6xl mx-auto space-y-4">
          <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>← Back</Button>

          {/* Brief Content */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Badge>Morning Brief</Badge>
                <CardTitle className="text-lg">{selected.title}</CardTitle>
              </div>
              <div className="text-xs text-muted-foreground">
                {formatDateTime(selected.generated_at)}
                {selected.news_count != null && <> · {selected.news_count} articles</>}
                {selected.elapsed_s != null && <> · {selected.elapsed_s}s</>}
              </div>
            </CardHeader>
            <CardContent>
              <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
                <ReactMarkdown
                  components={{
                    a: ({ href, children, ...props }: any) => {
                      if (href?.startsWith("http")) {
                        return <a href={href} target="_blank" rel="noopener noreferrer" {...props}>{children}</a>;
                      }
                      return <a href={href} {...props}>{children}</a>;
                    },
                  }}
                >
                  {renderCitations(selected.content, sources)}
                </ReactMarkdown>
              </div>

              {/* Cited Sources */}
              {sources.length > 0 && (
                <Accordion className="mt-4">
                  <AccordionItem value="cited">
                    <AccordionTrigger className="text-sm font-medium">
                      Cited Sources ({sources.length})
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="max-h-64 overflow-y-auto space-y-1 text-xs">
                        {sources.map((s: any) => (
                          <div key={s.idx} className="flex items-start gap-2 py-1 border-b border-muted/20 last:border-0">
                            <span className="text-muted-foreground font-mono w-7 shrink-0 text-right">[{s.idx}]</span>
                            <div className="min-w-0">
                              {s.url ? (
                                <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline leading-snug">{s.title}</a>
                              ) : <span className="leading-snug">{s.title}</span>}
                              <div className="text-muted-foreground mt-0.5">{s.source} · {s.category}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              )}
            </CardContent>
          </Card>

          {/* All Articles by Category */}
          {Object.keys(byCategory).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  <Globe className="inline h-4 w-4 mr-1" />
                  All Collected Articles ({allArticles.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <Accordion className="space-y-1">
                  {Object.entries(byCategory).sort().map(([cat, arts]) => (
                    <AccordionItem key={cat} value={cat}>
                      <AccordionTrigger className="text-sm py-2">
                        <span className="font-mono text-xs text-muted-foreground mr-2">{cat}</span>
                        <span className="text-xs">({arts.length} articles)</span>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="max-h-48 overflow-y-auto space-y-1 text-xs pl-4">
                          {arts.map((a: any, i: number) => (
                            <div key={i} className="flex items-start gap-2 py-1 border-b border-muted/10 last:border-0">
                              <span className="shrink-0">{(a as any).url ? (
                                <a href={(a as any).url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
                                  <ExternalLink className="h-3 w-3" />
                                </a>
                              ) : null}</span>
                              <div className="min-w-0">
                                <p className="leading-snug">{a.title}</p>
                                <span className="text-muted-foreground">{a.source}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </CardContent>
            </Card>
          )}
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Daily Insights</h2>
            <p className="text-sm text-muted-foreground">52 news categories · 50+ sources · AI-generated brief</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant={hours24 ? "default" : "outline"} size="sm" onClick={() => setHours24(!hours24)}>
              24h
            </Button>
            <Button onClick={startGenerate} disabled={generating}>
              {generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              {generating ? "Generating..." : "Generate Now"}
            </Button>
          </div>
        </div>

        {/* Real-time Progress */}
        {generating && (
          <Card>
            <CardHeader><CardTitle className="text-base">Progress</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                {progress.map((p, i) => (
                  <div key={i} className="flex items-center gap-3">
                    {p.status === "done" ? (
                      <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />
                    ) : p.status === "error" ? (
                      <CheckCircle2 className="h-4 w-4 text-red-500 shrink-0" />
                    ) : (
                      <Loader2 className="h-4 w-4 animate-spin text-blue-500 shrink-0" />
                    )}
                    <span className="text-muted-foreground w-24 shrink-0">{stageLabels[p.stage] || p.stage}</span>
                    <span className="text-xs text-muted-foreground truncate">{p.detail}</span>
                  </div>
                ))}
                {progress.length === 0 && (
                  <div className="flex items-center gap-3 text-sm">
                    <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
                    <span className="text-muted-foreground">Starting...</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Brief List */}
        {isLoading ? (
          <Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>
        ) : error ? (
          <Card><CardContent className="pt-8"><p className="text-sm text-muted-foreground">Failed to load. Is the backend running?</p></CardContent></Card>
        ) : briefs.length === 0 && !generating ? (
          <Card>
            <CardContent className="pt-8">
              <EmptyState
                title="No briefs yet"
                description="Generate your first morning brief."
                action={<Button onClick={startGenerate}><RefreshCw className="mr-2 h-4 w-4" />Generate</Button>}
              />
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {briefs.map((brief) => (
              <Card key={brief.id} className="cursor-pointer hover:bg-muted/30 transition-colors" onClick={() => setSelected(brief)}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="default">Morning</Badge>
                      <CardTitle className="text-base">{brief.title}</CardTitle>
                    </div>
                    <span className="text-xs text-muted-foreground">{formatDateTime(brief.generated_at)}</span>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground line-clamp-2">{brief.summary}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </Shell>
  );
}
