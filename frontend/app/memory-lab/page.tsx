"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { formatPercent } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import { memoryApi } from "@/lib/api/memory";
import {
  Brain, Search, Loader2, BookOpen, FlaskConical, History, RefreshCw,
} from "lucide-react";

export default function MemoryLabPage() {
  const [requestedStrategy, setRequestedStrategy] = useState<string>("");
  const [tickerFilter, setTickerFilter] = useState("");

  const strategiesQuery = useQuery({
    queryKey: ["strategies"],
    queryFn: () => strategiesApi.list(),
  });
  const strategies = strategiesQuery.data?.items ?? [];
  const selectedStrategy =
    strategies.find((strategy) => strategy.id === requestedStrategy)?.id ??
    strategies[0]?.id ??
    "";
  const selectedStrategyName =
    strategies.find((strategy) => strategy.id === selectedStrategy)?.name ?? "";

  const memoryQuery = useQuery({
    queryKey: ["memory", selectedStrategy, tickerFilter],
    queryFn: () => memoryApi.list(selectedStrategy, {
      limit: 50,
      ticker: tickerFilter || undefined,
    }),
    enabled: selectedStrategy.length > 0,
    retry: false,
  });
  const memories = memoryQuery.data?.memories ?? [];

  // OWM score distribution (computed client-side)
  const owmScores = memories.map((m) => m.owm_score);
  const avgOWM = owmScores.length > 0 ? owmScores.reduce((a, b) => a + b, 0) / owmScores.length : 0;

  return (
    <Shell>
      <div className="p-4 sm:p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Brain className="h-5 w-5" /> Memory Lab
          </h2>
          <p className="text-sm text-muted-foreground">
            Strategy learning from historical decisions — OWM-weighted memory, reflections, knowledge.
          </p>
        </div>

        {/* Strategy selector */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-sm font-medium">Strategy:</span>
              <Select
                value={selectedStrategy}
                onValueChange={(v) => v && setRequestedStrategy(v)}
                disabled={strategiesQuery.isLoading || strategiesQuery.isError || strategies.length === 0}
              >
                <SelectTrigger className="w-full sm:w-64" aria-label="Strategy">
                  <span className="flex flex-1 truncate text-left">
                    {selectedStrategyName}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {strategies.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative w-full sm:w-auto">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Filter by ticker..."
                  value={tickerFilter}
                  onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
                  className="pl-9 w-full sm:w-40"
                  disabled={!selectedStrategy}
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full sm:w-auto"
                disabled={!selectedStrategy || memoryQuery.isFetching}
                onClick={() => void memoryQuery.refetch()}
              >
                <RefreshCw className={`mr-2 h-4 w-4 ${memoryQuery.isFetching ? "animate-spin" : ""}`} />
                {memoryQuery.isFetching ? "Refreshing" : "Refresh"}
              </Button>
              {strategiesQuery.isLoading ? (
                <span className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" /> Loading strategies
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {strategiesQuery.isError ? (
          <Card className="border-destructive">
            <CardContent className="pt-6 text-sm text-destructive" role="alert">
              Failed to load strategies: {strategiesQuery.error.message}
            </CardContent>
          </Card>
        ) : null}

        {!strategiesQuery.isLoading && !strategiesQuery.isError && strategies.length === 0 ? (
          <Card>
            <CardContent className="pt-8">
              <EmptyState
                icon={<Brain className="h-12 w-12" />}
                title="No strategies available"
                description="Create a strategy before browsing strategy-scoped memory."
              />
            </CardContent>
          </Card>
        ) : null}

        {!strategiesQuery.isLoading && !strategiesQuery.isError && strategies.length > 0 ? (
        <Tabs defaultValue="memories">
          <div className="overflow-x-auto pb-1">
          <TabsList className="w-max">
            <TabsTrigger value="memories"><Brain className="mr-2 h-4 w-4" />Memories ({memories.length})</TabsTrigger>
            <TabsTrigger value="reflections"><History className="mr-2 h-4 w-4" />Reflections</TabsTrigger>
            <TabsTrigger value="knowledge"><BookOpen className="mr-2 h-4 w-4" />Knowledge Base</TabsTrigger>
            <TabsTrigger value="hypotheses"><FlaskConical className="mr-2 h-4 w-4" />Hypotheses</TabsTrigger>
          </TabsList>
          </div>

          {/* Memories Tab */}
          <TabsContent value="memories" className="space-y-4">
            {/* OWM Score overview */}
            {memoryQuery.isSuccess ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Total Memories</CardDescription>
                  <CardTitle className="text-2xl font-mono">{memories.length}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>Avg OWM Score</CardDescription>
                  <CardTitle className="text-2xl font-mono">{avgOWM.toFixed(2)}</CardTitle>
                </CardHeader>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardDescription>OWM Distribution</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-end gap-1 h-12">
                    {[0, 0.25, 0.5, 0.75, 1.0].map((threshold) => {
                      const count = owmScores.filter((s) => s >= threshold).length;
                      return (
                        <div key={threshold} className="flex-1 flex flex-col items-center">
                          <div
                            className="w-full bg-primary/50 rounded-t"
                            style={{ height: `${owmScores.length > 0 ? (count / owmScores.length) * 48 : 0}px` }}
                          />
                          <span className="text-xs text-muted-foreground mt-1">{"≥"}{threshold}</span>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </div>
            ) : null}

            {/* Memory table */}
            {memoryQuery.isLoading ? (
              <Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>
            ) : memoryQuery.isError ? (
              <Card className="border-destructive">
                <CardContent className="pt-6 space-y-3" role="alert">
                  <p className="text-sm font-medium text-destructive">Failed to load memory records.</p>
                  <p className="text-xs text-muted-foreground">{memoryQuery.error.message}</p>
                  <Button type="button" variant="outline" size="sm" onClick={() => void memoryQuery.refetch()}>
                    <RefreshCw className="mr-2 h-4 w-4" /> Try Again
                  </Button>
                </CardContent>
              </Card>
            ) : memories.length === 0 ? (
              <Card>
                <CardContent className="pt-8">
                  <EmptyState
                    icon={<Brain className="h-12 w-12" />}
                    title="No memories yet"
                    description={selectedStrategy
                      ? "This strategy hasn't generated any memories. Run an analysis to create memory records."
                      : "Select a strategy to view its memory records."
                    }
                  />
                </CardContent>
              </Card>
            ) : (
              <Card>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ticker</TableHead>
                      <TableHead>OWM Score</TableHead>
                      <TableHead>Outcome</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Episode</TableHead>
                      <TableHead>Date</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {memories.map((m) => (
                      <TableRow key={m.id}>
                        <TableCell className="font-mono font-bold">${m.ticker}</TableCell>
                        <TableCell>
                          <Badge variant={m.owm_score >= 0.5 ? "default" : "secondary"}>
                            {m.owm_score.toFixed(2)}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-mono">{formatPercent(m.outcome_quality * 100)}</TableCell>
                        <TableCell>{((m.confidence ?? 0) * 100).toFixed(0)}%</TableCell>
                        <TableCell className="text-sm max-w-[300px] truncate">{m.episodic}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{m.created_at?.slice(0, 10)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            )}
          </TabsContent>

          {/* Reflections Tab */}
          <TabsContent value="reflections">
            <Card><CardContent className="pt-8">
              <EmptyState icon={<History className="h-12 w-12" />} title="No reflections yet"
                description="Weekly reflections will be generated automatically. The scheduler generates them on the configured day/time."
              />
            </CardContent></Card>
          </TabsContent>

          {/* Knowledge Base Tab */}
          <TabsContent value="knowledge">
            <Card><CardContent className="pt-8">
              <EmptyState icon={<BookOpen className="h-12 w-12" />} title="Knowledge Base"
                description="Rules, findings, and failures from strategy execution history. Backend API coming soon."
              />
            </CardContent></Card>
          </TabsContent>

          {/* Hypotheses Tab */}
          <TabsContent value="hypotheses">
            <Card><CardContent className="pt-8">
              <EmptyState icon={<FlaskConical className="h-12 w-12" />} title="Hypotheses"
                description="Active research hypotheses with evidence tracking. Backend API coming soon."
              />
            </CardContent></Card>
          </TabsContent>
        </Tabs>
        ) : null}
      </div>
    </Shell>
  );
}
