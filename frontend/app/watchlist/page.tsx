"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/shared/empty-state";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { watchlistApi } from "@/lib/api/watchlist";
import { api } from "@/lib/api/client";
import { Plus, MoreHorizontal, Trash2, Loader2, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { Watchlist } from "@/lib/types/models";

function TickerRow({
  ticker,
  onRemove,
}: {
  ticker: string;
  onRemove: () => void;
}) {
  const { data: priceData } = useQuery({
    queryKey: ["market", "prices", ticker],
    queryFn: () => api.get<{ bars: { close: number }[] }>(`/market/prices/${ticker}?start=${new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0]}`),
    staleTime: 60_000,
  });

  const bars = priceData?.bars ?? [];
  const latest = bars[bars.length - 1];
  const prev = bars.length > 1 ? bars[bars.length - 2] : null;
  const changePct = prev && latest ? ((latest.close - prev.close) / prev.close) * 100 : 0;

  return (
    <TableRow>
      <TableCell className="font-mono font-bold">${ticker}</TableCell>
      <TableCell className="text-right font-mono">
        {latest ? formatCurrency(latest.close) : <Loader2 className="h-3 w-3 animate-spin inline" />}
      </TableCell>
      <TableCell className={`text-right font-mono ${changePct >= 0 ? "text-green-500" : "text-red-500"}`}>
        {latest ? formatPercent(changePct) : "—"}
      </TableCell>
      <TableCell className="text-right text-sm text-muted-foreground">—</TableCell>
      <TableCell className="text-right">
        {latest ? (
          changePct > 0 ? <Badge variant="outline" className="text-green-500 border-green-500/20">bullish</Badge> :
          changePct < 0 ? <Badge variant="outline" className="text-red-500 border-red-500/20">bearish</Badge> :
          <Badge variant="outline">neutral</Badge>
        ) : null}
      </TableCell>
      <TableCell className="text-right">
        <DropdownMenu>
          <DropdownMenuTrigger className="hover:bg-muted rounded-md">
            <div className="h-8 w-8 flex items-center justify-center">
              <MoreHorizontal className="h-4 w-4" />
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem className="text-destructive" onClick={onRemove}>
              <Trash2 className="mr-2 h-4 w-4" /> Remove
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  );
}

export default function WatchlistPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>("");
  const [newTicker, setNewTicker] = useState("");
  const [newWatchlistName, setNewWatchlistName] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["watchlists"],
    queryFn: () => watchlistApi.list(),
  });
  const watchlists = data?.watchlists ?? [];

  // Set initial active tab
  if (!activeTab && watchlists.length > 0 && !isLoading) {
    setActiveTab(watchlists[0].id);
  }

  const active = watchlists.find((w) => w.id === activeTab);

  const createMutation = useMutation({
    mutationFn: (name: string) => watchlistApi.create({ name, tickers: [] }),
    onSuccess: (w) => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setActiveTab(w.id);
      setNewWatchlistName("");
    },
  });

  const addTickerMutation = useMutation({
    mutationFn: ({ wid, ticker }: { wid: string; ticker: string }) =>
      watchlistApi.addTicker(wid, { ticker }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setNewTicker("");
    },
  });

  const removeTickerMutation = useMutation({
    mutationFn: ({ wid, ticker }: { wid: string; ticker: string }) =>
      watchlistApi.removeTicker(wid, ticker),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (wid: string) => watchlistApi.delete(wid),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setActiveTab("");
    },
  });

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Watchlist</h2>
            <p className="text-sm text-muted-foreground">Track your favorite tickers with real-time price data.</p>
          </div>
          <Button onClick={() => createMutation.mutate("New Watchlist")} disabled={createMutation.isPending}>
            <Plus className="mr-2 h-4 w-4" /> New Watchlist
          </Button>
        </div>

        {isLoading ? (
          <Card>
            <CardContent className="pt-8 flex justify-center">
              <Loader2 className="h-6 w-6 animate-spin" />
            </CardContent>
          </Card>
        ) : watchlists.length === 0 ? (
          <Card>
            <CardContent className="pt-8">
              <EmptyState
                title="No watchlists"
                description="Create a watchlist to start tracking tickers."
                action={
                  <Button onClick={() => createMutation.mutate("My Watchlist")}>
                    <Plus className="mr-2 h-4 w-4" /> Create Watchlist
                  </Button>
                }
              />
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Watchlist tab bar */}
            <div className="flex items-center gap-2 flex-wrap">
              {watchlists.map((w) => (
                <Button
                  key={w.id}
                  variant={activeTab === w.id ? "default" : "outline"}
                  size="sm"
                  onClick={() => setActiveTab(w.id)}
                >
                  {w.name} ({w.tickers?.length ?? 0})
                </Button>
              ))}
            </div>

            {/* Active watchlist content */}
            {active && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base">{active.name}</CardTitle>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        if (confirm(`Delete "${active.name}"?`)) {
                          deleteMutation.mutate(active.id);
                        }
                      }}
                    >
                      <Trash2 className="mr-2 h-3 w-3" /> Delete
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {/* Ticker table */}
                  {(active.tickers ?? []).length === 0 ? (
                    <div className="text-center py-4 text-sm text-muted-foreground">
                      No tickers yet. Add one below.
                    </div>
                  ) : (
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Ticker</TableHead>
                          <TableHead className="text-right">Price</TableHead>
                          <TableHead className="text-right">Change</TableHead>
                          <TableHead className="text-right">RSI(14)</TableHead>
                          <TableHead className="text-right">Signal</TableHead>
                          <TableHead className="w-12" />
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {(active.tickers ?? []).map((t) => (
                          <TickerRow
                            key={t}
                            ticker={t}
                            onRemove={() => removeTickerMutation.mutate({ wid: active.id, ticker: t })}
                          />
                        ))}
                      </TableBody>
                    </Table>
                  )}

                  {/* Add ticker */}
                  <div className="mt-4 flex items-center gap-2">
                    <Input
                      placeholder="Add ticker (e.g. AAPL)"
                      value={newTicker}
                      onChange={(e) => setNewTicker(e.target.value.toUpperCase())}
                      className="max-w-[200px]"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && newTicker.trim()) {
                          addTickerMutation.mutate({ wid: active.id, ticker: newTicker.trim() });
                        }
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!newTicker.trim() || addTickerMutation.isPending}
                      onClick={() => addTickerMutation.mutate({ wid: active.id, ticker: newTicker.trim() })}
                    >
                      {addTickerMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        )}
      </div>
    </Shell>
  );
}
