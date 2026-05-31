"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { EmptyState } from "@/components/shared/empty-state";
import { formatPercent } from "@/lib/utils";
import { strategiesApi } from "@/lib/api/strategies";
import { api } from "@/lib/api/client";
import type { StrategyConfig, MemoryRecord } from "@/lib/types/models";
import {
  Brain, Search, Loader2, BookOpen, FlaskConical, History, BarChart3,
} from "lucide-react";

export default function MemoryLabPage() {
  const [selectedStrategy, setSelectedStrategy] = useState<string>("");
  const [tickerFilter, setTickerFilter] = useState("");

  const { data: strategiesData } = useQuery({
    queryKey: ["strategies", undefined, undefined],
    queryFn: () => strategiesApi.list(),
  });
  const strategies = strategiesData?.items ?? [];

  // Set initial strategy
  if (!selectedStrategy && strategies.length > 0) {
    setSelectedStrategy(strategies[0].id);
  }

  const { data: memoryData, isLoading } = useQuery({
    queryKey: ["memory", selectedStrategy, tickerFilter],
    queryFn: () =>
      api.get<{ memories: MemoryRecord[]; total: number }>(
        `/strategies/${selectedStrategy}/memory?limit=50${tickerFilter ? `&ticker=${tickerFilter}` : ""}`
      ),
    enabled: !!selectedStrategy,
  });
  const memories = memoryData?.memories ?? [];

  // OWM score distribution (computed client-side)
  const owmScores = memories.map((m) => m.owm_score);
  const avgOWM = owmScores.length > 0 ? owmScores.reduce((a, b) => a + b, 0) / owmScores.length : 0;

  return (
    <Shell>
      <div className="p-6 space-y-6">
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
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium">Strategy:</span>
              <Select value={selectedStrategy} onValueChange={(v) => v && setSelectedStrategy(v)}>
                <SelectTrigger className="w-64">
                  <SelectValue placeholder="Select strategy" />
                </SelectTrigger>
                <SelectContent>
                  {strategies.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Filter by ticker..."
                  value={tickerFilter}
                  onChange={(e) => setTickerFilter(e.target.value.toUpperCase())}
                  className="pl-9 w-40"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Tabs defaultValue="memories">
          <TabsList>
            <TabsTrigger value="memories"><Brain className="mr-2 h-4 w-4" />Memories ({memories.length})</TabsTrigger>
            <TabsTrigger value="reflections"><History className="mr-2 h-4 w-4" />Reflections</TabsTrigger>
            <TabsTrigger value="knowledge"><BookOpen className="mr-2 h-4 w-4" />Knowledge Base</TabsTrigger>
            <TabsTrigger value="hypotheses"><FlaskConical className="mr-2 h-4 w-4" />Hypotheses</TabsTrigger>
          </TabsList>

          {/* Memories Tab */}
          <TabsContent value="memories" className="space-y-4">
            {/* OWM Score overview */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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

            {/* Memory table */}
            {isLoading ? (
              <Card><CardContent className="pt-8 flex justify-center"><Loader2 className="h-6 w-6 animate-spin" /></CardContent></Card>
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
      </div>
    </Shell>
  );
}
