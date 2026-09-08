"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import {
  Accordion, AccordionItem, AccordionTrigger, AccordionContent,
} from "@/components/ui/accordion";
import { EmptyState } from "@/components/shared/empty-state";
import { api } from "@/lib/api/client";
import { insightsApi } from "@/lib/api/insights";
import { createInsightGenerationId } from "@/lib/insight-generation-state";
import { formatDateTime } from "@/lib/utils";
import type { DailyBrief, Watchlist } from "@/lib/types/models";
import { usePersistedInsightGenerationId } from "@/lib/use-persisted-insight-generation-id";
import { Markdown } from "@/components/markdown";
import {
  Loader2, RefreshCw, CheckCircle2, Globe, ExternalLink,
  X, Newspaper, List, Circle, AlertCircle,
} from "lucide-react";

type Tab = "briefs" | "watchlist";
type TimeRange = 24 | 72 | 168 | 720;
const TIME_OPTIONS: { label: string; value: TimeRange }[] = [
  { label: "24h", value: 24 },
  { label: "3d", value: 72 },
  { label: "7d", value: 168 },
  { label: "30d", value: 720 },
];

function renderCitations(content: string, sources: any[]): string {
  if (!sources || sources.length === 0) return content;
  return content.replace(/\[(\d+)\]/g, (match, num) => {
    const idx = parseInt(num, 10);
    const src = sources.find((s: any) => s.idx === idx);
    if (src?.url) return `[${match}](${src.url})`;
    return match;
  });
}

const STAGE_ORDER = ["market", "news", "llm", "store"] as const;
const STAGE_LABELS: Record<string, string> = {
  market: "Market Data", news: "News Collection", llm: "AI Generation", store: "Saving",
};

export default function InsightsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("briefs");
  const [selected, setSelected] = useState<DailyBrief | null>(null);
  const [dismissedGeneratedInsightId, setDismissedGeneratedInsightId] = useState<
    string | null
  >(null);
  const [hours24, setHours24] = useState(true);
  const {
    generationId,
    persistGenerationId,
    syncGenerationStatus,
  } = usePersistedInsightGenerationId();

  // Watchlist news state
  const [wlId, setWlId] = useState<string>("");
  const [wlHours, setWlHours] = useState<TimeRange>(168);
  const [wlNews, setWlNews] = useState<any[] | null>(null); // null = never searched
  const [wlLoading, setWlLoading] = useState(false);
  const [wlSearch, setWlSearch] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["insights"],
    queryFn: () => api.get<{ insights: DailyBrief[] }>("insights?limit=20"),
    enabled: tab === "briefs",
  });
  const briefs = data?.insights ?? [];

  const generationMutation = useMutation({
    mutationFn: ({ id, hours }: { id: string; hours: number }) =>
      insightsApi.generate(id, hours),
    onSuccess: (generation) => {
      persistGenerationId(generation.id, generation.status);
    },
  });
  const generationQuery = useQuery({
    queryKey: ["insight-generation", generationId],
    queryFn: () => insightsApi.getGeneration(generationId ?? ""),
    enabled: generationId !== null,
    retry: (failureCount, queryError) =>
      failureCount < 20 &&
      queryError instanceof Error &&
      queryError.message.startsWith("HTTP 404:"),
    retryDelay: 250,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "pending" || status === "running" ? 1000 : false;
    },
  });
  const generation = generationQuery.data;
  const generating = generationMutation.isPending ||
    generation?.status === "pending" ||
    generation?.status === "running" ||
    (generationId !== null && generationQuery.isLoading);
  const progress = generation?.progress ?? {};
  const completedStageCount = STAGE_ORDER.filter(
    (stage) => progress[stage]?.status === "done",
  ).length;
  const generationError = generationMutation.isError
    ? generationMutation.error instanceof Error
      ? generationMutation.error.message
      : "Insight generation could not start."
    : generation?.error ??
      (generationQuery.isError ? "Unable to restore insight generation status." : null);

  useEffect(() => {
    if (generation === undefined) return;
    syncGenerationStatus(generation.id, generation.status);
    if (generation.status === "completed") {
      void queryClient.invalidateQueries({ queryKey: ["insights"] });
    }
  }, [generation, queryClient, syncGenerationStatus]);

  const completedInsightId = generation?.status === "completed"
    ? generation.result_insight_id
    : null;
  const generatedInsightQuery = useQuery({
    queryKey: ["insights", completedInsightId],
    queryFn: () => insightsApi.get(completedInsightId ?? ""),
    enabled: completedInsightId !== null,
  });

  const selectedBrief = selected ?? (
    completedInsightId !== dismissedGeneratedInsightId
      ? generatedInsightQuery.data ?? null
      : null
  );

  // Fetch watchlists for selector
  const { data: wlData } = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => api.get<{ watchlists: Watchlist[] }>("watchlists"),
    enabled: tab === "watchlist",
  });
  const watchlists = wlData?.watchlists ?? [];

  // Auto-select first non-empty watchlist on entering tab
  useEffect(() => {
    if (tab === "watchlist" && watchlists.length > 0 && !wlId) {
      const first = watchlists.find((w) => (w.tickers?.length ?? 0) > 0);
      if (first) setWlId(first.id);
    }
  }, [tab, watchlists, wlId]);

  const selectedWatchlist = watchlists.find((w) => w.id === wlId);
  const hasTickers = (selectedWatchlist?.tickers?.length ?? 0) > 0;

  // Fetch news — called on watchlist change AND on Search button
  const fetchWatchlistNews = useCallback((hours?: TimeRange) => {
    const h = hours ?? wlHours;
    if (!wlId) return;
    setWlLoading(true);
    setWlNews([]); // show loading state immediately
    api.get<{ articles: any[]; tickers: string[] }>(`insights/watchlist-news?watchlist_id=${wlId}&hours=${h}`)
      .then((d) => setWlNews((d as any).articles || []))
      .catch(() => setWlNews([]))
      .finally(() => setWlLoading(false));
  }, [wlHours, wlId]);

  // Auto-fetch when wlId changes (user picks a different watchlist)
  useEffect(() => {
    if (wlId && tab === "watchlist") fetchWatchlistNews();
  }, [fetchWatchlistNews, tab, wlId]);

  const startGenerate = () => {
    generationMutation.reset();
    const generationId = createInsightGenerationId();
    persistGenerationId(generationId, "pending");
    generationMutation.mutate({ id: generationId, hours: hours24 ? 24 : 0 });
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await api.delete(`insights/${id}`);
    queryClient.invalidateQueries({ queryKey: ["insights"] });
  };

  // ── Selected Brief Detail View ──
  if (selectedBrief) {
    const sources = (selectedBrief as any).sources || (selectedBrief as any).news_sources || [];
    const allArticles = (selectedBrief as any).all_articles || [];
    const byCategory: Record<string, any[]> = {};
    for (const a of allArticles) {
      const cat = a.category || "other";
      if (!byCategory[cat]) byCategory[cat] = [];
      if (byCategory[cat].length < 20) byCategory[cat].push(a);
    }

    return (
      <Shell>
        <div className="p-6 max-w-6xl mx-auto space-y-4">
          <Button variant="ghost" size="sm" onClick={() => {
            setSelected(null);
            setDismissedGeneratedInsightId(completedInsightId);
          }}>← Back</Button>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2"><Badge>Morning Brief</Badge><CardTitle className="text-lg">{selectedBrief.title}</CardTitle></div>
              <div className="text-xs text-muted-foreground">{formatDateTime(selectedBrief.generated_at)}{selectedBrief.news_count != null && <> · {selectedBrief.news_count} articles</>}{selectedBrief.elapsed_s != null && <> · {selectedBrief.elapsed_s}s</>}</div>
            </CardHeader>
            <CardContent>
              <div className="text-sm leading-relaxed prose prose-sm dark:prose-invert max-w-none">
                <Markdown components={{ a: ({ href, children, ...p }: any) => href?.startsWith("http") ? <a href={href} target="_blank" rel="noopener noreferrer" {...p}>{children}</a> : <a href={href} {...p}>{children}</a> }}>
                  {renderCitations(selectedBrief.content, sources)}
                </Markdown>
              </div>
              {sources.length > 0 && (
                <Accordion className="mt-4"><AccordionItem value="cited"><AccordionTrigger className="text-sm font-medium">Cited Sources ({sources.length})</AccordionTrigger><AccordionContent><div className="max-h-64 overflow-y-auto space-y-1 text-xs">{sources.map((s: any) => (<div key={s.idx} className="flex items-start gap-2 py-1 border-b border-muted/20 last:border-0"><span className="text-muted-foreground font-mono w-7 shrink-0 text-right">[{s.idx}]</span><div className="min-w-0">{s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline leading-snug">{s.title}</a> : <span className="leading-snug">{s.title}</span>}<div className="text-muted-foreground mt-0.5">{s.source} · {s.category}</div></div></div>))}</div></AccordionContent></AccordionItem></Accordion>
              )}
            </CardContent>
          </Card>
          {Object.keys(byCategory).length > 0 && (
            <Card><CardHeader><CardTitle className="text-base"><Globe className="inline h-4 w-4 mr-1" />All Articles ({allArticles.length})</CardTitle></CardHeader><CardContent><Accordion className="space-y-1">{Object.entries(byCategory).sort().map(([cat, arts]) => (<AccordionItem key={cat} value={cat}><AccordionTrigger className="text-sm py-2"><span className="font-mono text-xs text-muted-foreground mr-2">{cat}</span><span className="text-xs">({arts.length})</span></AccordionTrigger><AccordionContent><div className="max-h-48 overflow-y-auto space-y-1 text-xs pl-4">{arts.map((a: any) => (<div key={`${a.url ?? ""}-${a.published_at ?? ""}-${a.title ?? ""}`} className="flex items-start gap-2 py-1 border-b border-muted/10 last:border-0"><span className="shrink-0">{a.url ? <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline"><ExternalLink className="h-3 w-3" /></a> : null}</span><div className="min-w-0"><p className="leading-snug">{a.title}</p><span className="text-muted-foreground">{a.source}</span></div></div>))}</div></AccordionContent></AccordionItem>))}</Accordion></CardContent></Card>
          )}
        </div>
      </Shell>
    );
  }

  // ── Main Page ──
  return (
    <Shell>
      <div className="p-6 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Daily Insights</h2>
            <p className="text-sm text-muted-foreground">Market briefs, watchlist news, all in one place.</p>
          </div>
          {tab === "briefs" && (
            <div className="flex items-center gap-3">
              <Button variant={hours24 ? "default" : "outline"} size="sm" onClick={() => setHours24(!hours24)}>24h</Button>
              <Button onClick={startGenerate} disabled={generating}>{generating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}{generating ? "Generating..." : "Generate"}</Button>
            </div>
          )}
        </div>

        {/* Tab selector */}
        <div className="flex gap-2 border-b pb-2">
          <Button variant={tab === "briefs" ? "default" : "ghost"} size="sm" onClick={() => setTab("briefs")}><Newspaper className="mr-1 h-4 w-4" />Briefs</Button>
          <Button variant={tab === "watchlist" ? "default" : "ghost"} size="sm" onClick={() => setTab("watchlist")}><List className="mr-1 h-4 w-4" />Watchlist News</Button>
        </div>

        {/* ── Briefs Tab ── */}
        {tab === "briefs" && (
          <>
            {(generating || generationError !== null) && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">{generationError ? "Brief Generation Failed" : "Generating Brief"}</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  <Progress
                    value={completedStageCount / STAGE_ORDER.length * 100}
                    aria-label="Brief generation progress"
                    aria-valuetext={`${completedStageCount} of ${STAGE_ORDER.length} stages complete`}
                  />
                  {STAGE_ORDER.map((stage) => {
                    const p = progress[stage];
                    const done = p?.status === "done";
                    const active = p && !done;
                    return (
                      <div key={stage} className={`flex items-center gap-3 text-sm transition-opacity duration-300 ${!p ? "opacity-40" : "opacity-100"}`}>
                        {done ? (
                          <CheckCircle2 className="h-4 w-4 text-foreground shrink-0 transition-all duration-300 scale-110" />
                        ) : active ? (
                          <Loader2 className="h-4 w-4 animate-spin text-primary shrink-0" />
                        ) : (
                          <Circle className="h-4 w-4 text-muted-foreground/30 shrink-0" />
                        )}
                        <span className={`w-32 shrink-0 text-xs ${active ? "text-foreground font-medium" : "text-muted-foreground"}`}>
                          {STAGE_LABELS[stage]}
                        </span>
                        <span className={`text-xs truncate ${active ? "text-foreground" : "text-muted-foreground"}`}>
                          {p?.detail || "Waiting"}
                        </span>
                      </div>
                    );
                  })}
                  {generationError && (
                    <div className="flex items-center gap-3 text-sm text-destructive" role="alert">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span>{generationError}</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
            {isLoading ? (<Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>) : error ? (<Card><CardContent className="pt-8"><p className="text-sm text-muted-foreground">Failed to load.</p></CardContent></Card>) : briefs.length === 0 && !generating ? (<Card><CardContent className="pt-8"><EmptyState title="No briefs yet" description="Generate your first morning brief." action={<Button onClick={startGenerate}><RefreshCw className="mr-2 h-4 w-4" />Generate</Button>} /></CardContent></Card>) : (
              <div className="space-y-3">
                {briefs.map((brief) => (
                  <Card key={brief.id} className="cursor-pointer hover:bg-muted/30 transition-colors group" onClick={() => setSelected(brief)}>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2"><Badge variant="default">Morning</Badge><CardTitle className="text-base">{brief.title}</CardTitle></div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-muted-foreground">{formatDateTime(brief.generated_at)}</span>
                          <button type="button" onClick={(e) => handleDelete(e, brief.id)} className="p-1 rounded hover:bg-destructive/10 transition-colors opacity-0 group-hover:opacity-100" title="Delete"><X className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" /></button>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent><p className="text-sm text-muted-foreground line-clamp-2 [word-break:auto-phrase] [text-wrap:pretty]">{brief.summary}</p></CardContent>
                  </Card>
                ))}
              </div>
            )}
          </>
        )}

        {/* ── Watchlist News Tab ── */}
        {tab === "watchlist" && (
          <div className="space-y-4">
            {/* Watchlist selector — button group for reliable display */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground font-medium">Watchlist</p>
              <div className="flex gap-1 flex-wrap">
                {watchlists.map((w) => (
                  <Button
                    key={w.id}
                    variant={wlId === w.id ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => setWlId(w.id)}
                  >
                    {w.name} ({w.tickers?.length ?? 0})
                  </Button>
                ))}
              </div>
            </div>
            {/* Time + Search */}
            <div className="flex items-end gap-4 flex-wrap">
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground font-medium">Time Range</p>
                <div className="flex gap-0.5">
                  {TIME_OPTIONS.map((t) => (<Button key={t.value} variant={wlHours === t.value ? "default" : "outline"} size="sm" className="h-8 text-xs" onClick={() => setWlHours(t.value)}>{t.label}</Button>))}
                </div>
              </div>
              <div className="space-y-1">
                <label htmlFor="watchlist-news-filter" className="text-xs text-muted-foreground font-medium">Filter</label>
                <Input id="watchlist-news-filter" placeholder="Ticker or keyword..." value={wlSearch} onChange={(e) => setWlSearch(e.target.value)} className="h-8 w-40 text-xs" />
              </div>
              <Button size="sm" onClick={() => fetchWatchlistNews()} disabled={wlLoading || !wlId}>
                {wlLoading ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1 h-3.5 w-3.5" />}
                Search
              </Button>
              <span className="text-xs text-muted-foreground pb-1">{wlNews?.length ?? 0} articles</span>
            </div>

            {!hasTickers ? (
              <Card><CardContent className="pt-8"><p className="text-sm text-muted-foreground text-center">This watchlist has no tickers. Add tickers to it first.</p></CardContent></Card>
            ) : wlLoading ? (
              <Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>
            ) : wlNews === null ? (
              <Card><CardContent className="pt-8"><p className="text-sm text-muted-foreground text-center">Select a watchlist and click Search to find news.</p></CardContent></Card>
            ) : wlNews.length === 0 ? (
              <Card><CardContent className="pt-8"><p className="text-sm text-muted-foreground text-center">No news found. Try a longer time range or a different watchlist.</p></CardContent></Card>
            ) : (
              <WatchlistNewsList articles={wlNews} search={wlSearch} />
            )}
          </div>
        )}
      </div>
    </Shell>
  );
}

function WatchlistNewsList({ articles, search }: { articles: any[]; search: string }) {
  const [summaries, setSummaries] = useState<Record<string, string>>({});
  const [allSummary, setAllSummary] = useState<string>("");
  const [summLoading, setSummLoading] = useState<string | null>(null); // ticker or "all"

  const filtered = search
    ? articles.filter((a: any) =>
        a.ticker?.toLowerCase().includes(search.toLowerCase()) ||
        a.title?.toLowerCase().includes(search.toLowerCase()))
    : articles;

  const grouped = useMemo(() => {
    const map: Record<string, any[]> = {};
    for (const a of filtered) {
      const t = a.ticker || "?";
      if (!map[t]) map[t] = [];
      map[t].push(a);
    }
    for (const t of Object.keys(map)) {
      map[t].sort((a: any, b: any) => (b.published_at || "").localeCompare(a.published_at || ""));
    }
    return Object.entries(map).sort((a, b) => b[1].length - a[1].length);
  }, [filtered]);

  const doSummary = async (ticker: string, arts: any[]) => {
    setSummLoading(ticker);
    try {
      const d = await api.post<{ summary: string }>("insights/watchlist-summary", { ticker, articles: arts });
      setSummaries((prev) => ({ ...prev, [ticker]: d.summary }));
    } catch { /* ignore */ }
    setSummLoading(null);
  };

  const doSummaryAll = async () => {
    setSummLoading("all");
    try {
      const d = await api.post<{ summary: string }>("insights/watchlist-summary", { articles: filtered });
      setAllSummary(d.summary);
    } catch { /* ignore */ }
    setSummLoading(null);
  };

  if (grouped.length === 0) return null;

  return (
    <div className="space-y-3">
      {/* Summarize All */}
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={doSummaryAll} disabled={summLoading === "all"}>
          {summLoading === "all" ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
          Summarize All
        </Button>
      </div>
      {allSummary && (
        <Card><CardContent className="py-3 text-sm text-muted-foreground">{allSummary}</CardContent></Card>
      )}

      <Card>
        <CardContent className="pt-4 max-h-[calc(100vh-380px)] overflow-y-auto">
          <Accordion className="space-y-0">
          {grouped.map(([ticker, arts]) => (
            <AccordionItem key={ticker} value={ticker}>
              <AccordionTrigger className="py-2 pr-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="font-mono text-xs">{ticker}</Badge>
                  <span className="text-xs text-muted-foreground">{arts.length} articles</span>
                  <span className="text-[10px] text-muted-foreground">
                    {arts[0]?.published_at?.slice(0, 10) || ""}
                    {arts[arts.length - 1]?.published_at?.slice(0, 10) !== arts[0]?.published_at?.slice(0, 10)
                      ? ` — ${arts[arts.length - 1]?.published_at?.slice(0, 10) || ""}` : ""}
                  </span>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="space-y-0.5 pl-2">
                  {/* Per-ticker summary */}
                  {summaries[ticker] && (
                    <div className="py-2 px-3 mb-2 rounded bg-primary/5 border border-primary/10 text-xs text-muted-foreground">
                      {summaries[ticker]}
                    </div>
                  )}
                  <div className="flex justify-end mb-1">
                    <Button variant="ghost" size="sm" className="h-6 text-[10px]"
                      onClick={(e) => { e.stopPropagation(); doSummary(ticker, arts); }}
                      disabled={summLoading === ticker}>
                      {summLoading === ticker ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : null}
                      Summarize
                    </Button>
                  </div>
                  {arts.map((a: any) => (
                    <div key={`${a.url ?? ""}-${a.published_at ?? ""}-${a.title ?? ""}`} className="flex items-start gap-2 py-1.5 border-b border-muted/10 last:border-0">
                      <div className="shrink-0 mt-0.5">
                        <Badge variant="secondary" className="text-[9px] px-1 py-0 h-4 font-normal">{a.source}</Badge>
                      </div>
                      <div className="min-w-0 flex-1">
                        {a.url ? (
                          <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline leading-snug">{a.title}</a>
                        ) : (
                          <p className="text-xs leading-snug">{a.title}</p>
                        )}
                        {a.published_at && (
                          <span className="text-[10px] text-muted-foreground ml-2 shrink-0">{a.published_at.slice(0, 16)}</span>
                        )}
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
    </div>
  );
}
