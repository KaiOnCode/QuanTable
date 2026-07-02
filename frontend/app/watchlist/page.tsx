"use client";

import { useState, useEffect, useRef } from "react";
import { toast } from "sonner";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shell } from "@/components/layout/shell";
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { watchlistApi } from "@/lib/api/watchlist";
import { api } from "@/lib/api/client";
import { Plus, MoreHorizontal, Trash2, Loader2, TrendingUp, TrendingDown, Minus, Pencil, Check, X, Bell } from "lucide-react";
import type { AlertType, Watchlist } from "@/lib/types/models";

const CHANNEL_OPTIONS = [
  { value: "telegram", label: "Telegram" },
  { value: "email", label: "Email" },
  { value: "wechat", label: "WeChat" },
  { value: "whatsapp", label: "WhatsApp" },
];

function TickerRow({
  ticker,
  meta,
  isNew,
  onRemove,
  onCreateAlert,
}: {
  ticker: string;
  meta?: { name?: string; short_name?: string; currency?: string; country?: string; exchange?: string };
  isNew?: boolean;
  onRemove: () => void;
  onCreateAlert: () => void;
}) {
  const currency = meta?.currency || "USD";
  const companyName = meta?.name || meta?.short_name || "";
  const startDate = new Date(Date.now() - 7 * 86400000).toISOString().split("T")[0];
  const { data: priceData, isLoading, isFetching } = useQuery({
    queryKey: ["market", "prices", ticker],
    queryFn: () => api.get<{ bars: { close: number; date: string }[] }>(`/market/prices/${ticker}?start=${startDate}`),
    staleTime: 10_000,
    refetchInterval: isNew ? 3_000 : 0,  // Fast poll for new tickers, no poll for existing
  });

  const { data: indData } = useQuery({
    queryKey: ["market", "indicators", ticker],
    queryFn: () => api.get<{ rsi14: number | null; macd_signal: string | null }>(`/market/indicators/${ticker}`),
    staleTime: 60_000,
    enabled: !isLoading,  // Only fetch indicators when price data exists
  });

  const bars = priceData?.bars ?? [];
  const latest = bars[bars.length - 1];
  const prev = bars.length > 1 ? bars[bars.length - 2] : null;
  const changePct = prev && latest ? ((latest.close - prev.close) / prev.close) * 100 : 0;
  const hasData = bars.length > 0;
  // Show fetching for: new tickers awaiting data, or active queries
  const showFetching = !hasData && (isNew || isLoading || isFetching);

  // When price data first arrives, retry meta with delays (meta is written right after prices by the bg thread)
  const queryClient = useQueryClient();
  const hadData = useRef(false);
  useEffect(() => {
    if (hasData && !hadData.current) {
      hadData.current = true;
      // Immediate invalidation
      queryClient.invalidateQueries({ queryKey: ["market", "meta"] });
      // Retry after 2s in case bg thread hasn't written meta yet
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["market", "meta"] }), 2000);
      // Final retry after 5s
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["market", "meta"] }), 5000);
    }
  }, [hasData, queryClient]);
  const rsi = indData?.rsi14 ?? null;
  const macd = indData?.macd_signal ?? null;

  return (
    <TableRow>
      <TableCell>
        <div className="font-mono font-bold">${ticker}</div>
        {companyName && (
          <div className="text-xs text-muted-foreground truncate max-w-[180px]">{companyName}</div>
        )}
        {meta?.country && (
          <div className="text-xs text-muted-foreground/60">{meta.country}{meta.exchange ? ` · ${meta.exchange}` : ""}</div>
        )}
      </TableCell>
      <TableCell className="text-right font-mono">
        {showFetching ? (
          <Loader2 className="h-3 w-3 animate-spin inline" />
        ) : hasData ? (
          formatCurrency(latest!.close, currency)
        ) : (
          <span className="text-xs text-muted-foreground">no data</span>
        )}
      </TableCell>
      <TableCell className={`text-right font-mono ${changePct >= 0 ? "text-green-500" : "text-red-500"}`}>
        {hasData ? formatPercent(changePct) : "—"}
      </TableCell>
      <TableCell className="text-right text-xs font-mono">
        {rsi != null ? rsi.toFixed(1) : "—"}
      </TableCell>
      <TableCell className="text-right">
        {macd === "bullish" ? (
          <Badge variant="outline" className="text-green-500 border-green-500/20 text-xs">bullish</Badge>
        ) : macd === "bearish" ? (
          <Badge variant="outline" className="text-red-500 border-red-500/20 text-xs">bearish</Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <DropdownMenu>
          <DropdownMenuTrigger className="hover:bg-muted rounded-md">
            <div className="h-8 w-8 flex items-center justify-center">
              <MoreHorizontal className="h-4 w-4" />
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onCreateAlert}>
              <Bell className="mr-2 h-4 w-4" /> Set Alert
            </DropdownMenuItem>
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
  // Track tickers added in last 30s that are still fetching data
  const [pendingTickers, setPendingTickers] = useState<Record<string, number>>({});
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [alertTicker, setAlertTicker] = useState("");
  const [alertType, setAlertType] = useState<AlertType>("price_above");
  const [alertThreshold, setAlertThreshold] = useState("");
  const [alertChannels, setAlertChannels] = useState<string[]>(["telegram"]);

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
  const activeTickers = active?.tickers ?? [];

  // Fetch company names for active watchlist tickers
  const { data: metaData } = useQuery({
    queryKey: ["market", "meta", activeTickers.join(",")],
    queryFn: () => api.get<{ meta: Record<string, { name?: string; short_name?: string; currency?: string; country?: string; exchange?: string }> }>(
      `/market/meta?tickers=${activeTickers.join(",")}`
    ),
    enabled: activeTickers.length > 0,
    staleTime: 30_000,
  });
  const meta = metaData?.meta ?? {};

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
    onSuccess: (_, { ticker }) => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      queryClient.invalidateQueries({ queryKey: ["market", "meta"] });
      // Mark as pending → shows "fetching..." until data arrives
      setPendingTickers((prev) => ({ ...prev, [ticker.toUpperCase()]: Date.now() }));
      // Auto-clear pending after 30s (if data never arrives)
      setTimeout(() => {
        setPendingTickers((prev) => {
          const next = { ...prev };
          delete next[ticker.toUpperCase()];
          return next;
        });
      }, 30_000);
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

  const renameMutation = useMutation({
    mutationFn: ({ wid, name }: { wid: string; name: string }) =>
      watchlistApi.update(wid, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setRenamingId(null);
    },
  });

  const createAlertMutation = useMutation({
    mutationFn: ({
      wid,
      ticker,
      type,
      threshold,
      channels,
    }: {
      wid: string;
      ticker: string;
      type: AlertType;
      threshold: string;
      channels: string[];
    }) =>
      watchlistApi.createAlert(wid, {
        ticker,
        type,
        threshold_value: Number(threshold),
        notification_channels: channels,
      }),
    onSuccess: (alert) => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      setAlertDialogOpen(false);
      setAlertTicker("");
      setAlertThreshold("");
      toast.success("Watchlist alert created", {
        description: `${alert.ticker} ${alert.type.replace("_", " ")} ${alert.threshold_value}`,
      });
    },
    onError: (error: Error) => {
      toast.error("Failed to create alert", { description: error.message });
    },
  });

  const checkAlertsMutation = useMutation({
    mutationFn: () => watchlistApi.checkAlerts(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["watchlists"] });
      toast.success("Alert check completed", {
        description: `${result.triggered_count} alert(s) triggered.`,
      });
    },
    onError: (error: Error) => {
      toast.error("Failed to check alerts", { description: error.message });
    },
  });

  const openAlertDialog = (ticker: string) => {
    setAlertTicker(ticker);
    setAlertType("price_above");
    setAlertThreshold("");
    setAlertChannels(["telegram"]);
    setAlertDialogOpen(true);
  };

  const toggleAlertChannel = (channel: string, checked: boolean) => {
    setAlertChannels((current) => {
      if (checked) {
        return current.includes(channel) ? current : [...current, channel];
      }
      return current.filter((item) => item !== channel);
    });
  };

  const saveAlert = () => {
    if (!active || !alertTicker || !alertThreshold || alertChannels.length === 0) {
      return;
    }
    createAlertMutation.mutate({
      wid: active.id,
      ticker: alertTicker,
      type: alertType,
      threshold: alertThreshold,
      channels: alertChannels,
    });
  };

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">Watchlist</h2>
            <p className="text-sm text-muted-foreground">Track your favorite tickers with real-time price data.</p>
          </div>
          <Button onClick={() => { setCreateName(""); setCreateDialogOpen(true); }}>
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
                  <Button onClick={() => { setCreateName("My Watchlist"); setCreateDialogOpen(true); }}>
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
                    <CardTitle className="text-base flex items-center gap-2">
                      {renamingId === active.id ? (
                        <>
                          <Input
                            ref={renameInputRef}
                            value={renameValue}
                            onChange={(e) => setRenameValue(e.target.value)}
                            className="h-8 w-48 text-sm"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") renameMutation.mutate({ wid: active.id, name: renameValue });
                              if (e.key === "Escape") setRenamingId(null);
                            }}
                          />
                          <Button size="icon-sm" variant="ghost" onClick={() => renameMutation.mutate({ wid: active.id, name: renameValue })} disabled={renameMutation.isPending}>
                            <Check className="h-3.5 w-3.5" />
                          </Button>
                          <Button size="icon-sm" variant="ghost" onClick={() => setRenamingId(null)}>
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </>
                      ) : (
                        <>
                          {active.name}
                          <Button
                            size="icon-sm"
                            variant="ghost"
                            onClick={() => { setRenamingId(active.id); setRenameValue(active.name); setTimeout(() => renameInputRef.current?.focus(), 0); }}
                          >
                            <Pencil className="h-3 w-3 text-muted-foreground" />
                          </Button>
                        </>
                      )}
                    </CardTitle>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={checkAlertsMutation.isPending}
                      onClick={() => checkAlertsMutation.mutate()}
                    >
                      <Bell className="mr-2 h-3 w-3" />
                      {checkAlertsMutation.isPending ? "Checking" : "Check Alerts"}
                    </Button>
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
                            meta={meta[t]}
                            isNew={!!pendingTickers[t]}
                            onRemove={() => removeTickerMutation.mutate({ wid: active.id, ticker: t })}
                            onCreateAlert={() => openAlertDialog(t)}
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

      {/* Create dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Watchlist</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="Watchlist name"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && createName.trim()) {
                createMutation.mutate(createName.trim());
                setCreateDialogOpen(false);
              }
            }}
            autoFocus
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={() => { createMutation.mutate(createName.trim() || "Watchlist"); setCreateDialogOpen(false); }}
              disabled={createMutation.isPending}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={alertDialogOpen} onOpenChange={setAlertDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Alert for {alertTicker}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4">
            <div className="space-y-2">
              <Label>Condition</Label>
              <Select value={alertType} onValueChange={(value) => setAlertType(value as AlertType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="price_above">Price above</SelectItem>
                  <SelectItem value="price_below">Price below</SelectItem>
                  <SelectItem value="rsi_above">RSI above</SelectItem>
                  <SelectItem value="rsi_below">RSI below</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Threshold</Label>
              <Input
                type="number"
                value={alertThreshold}
                onChange={(event) => setAlertThreshold(event.target.value)}
                placeholder={alertType.startsWith("price") ? "Target price" : "Target RSI"}
              />
            </div>
            <div className="space-y-2">
              <Label>Channels</Label>
              <div className="grid grid-cols-2 gap-3 rounded-md border p-3">
                {CHANNEL_OPTIONS.map((channel) => (
                  <label key={channel.value} className="flex items-center gap-2 text-sm">
                    <Checkbox
                      checked={alertChannels.includes(channel.value)}
                      onCheckedChange={(checked) =>
                        toggleAlertChannel(channel.value, Boolean(checked))
                      }
                    />
                    <span>{channel.label}</span>
                  </label>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
            <Button
              onClick={saveAlert}
              disabled={!alertThreshold || alertChannels.length === 0 || createAlertMutation.isPending}
            >
              {createAlertMutation.isPending ? "Saving" : "Save Alert"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Shell>
  );
}
