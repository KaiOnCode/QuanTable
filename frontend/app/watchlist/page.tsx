"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/shared/empty-state";
import { watchlistApi } from "@/lib/api/watchlist";
import type { AlertType } from "@/lib/types/models";
import { formatCurrency, formatPercent } from "@/lib/utils";
import { Star, Plus, MoreHorizontal, Trash2, Bell, TrendingUp, TrendingDown } from "lucide-react";

const MOCK_WATCHLISTS: Record<string, {
  name: string;
  tickers: {
    ticker: string;
    price: number;
    change_pct: number;
    rsi14: number;
    macd_signal: "bullish" | "bearish";
    sentiment: "positive" | "negative" | "neutral";
  }[];
}> = {
  "my-positions": {
    name: "My Positions",
    tickers: [
      { ticker: "AAPL", price: 192.45, change_pct: 1.25, rsi14: 52.3, macd_signal: "bullish", sentiment: "positive" },
      { ticker: "MSFT", price: 445.30, change_pct: 0.85, rsi14: 48.7, macd_signal: "bullish", sentiment: "positive" },
      { ticker: "NVDA", price: 950.20, change_pct: -2.10, rsi14: 62.1, macd_signal: "bearish", sentiment: "neutral" },
    ],
  },
  "ai-stocks": {
    name: "AI Stocks",
    tickers: [
      { ticker: "NVDA", price: 950.20, change_pct: -2.10, rsi14: 62.1, macd_signal: "bearish", sentiment: "neutral" },
      { ticker: "AMD", price: 145.80, change_pct: 3.45, rsi14: 55.2, macd_signal: "bullish", sentiment: "positive" },
      { ticker: "SMCI", price: 680.50, change_pct: 5.20, rsi14: 70.5, macd_signal: "bullish", sentiment: "positive" },
      { ticker: "GOOGL", price: 175.30, change_pct: -0.50, rsi14: 42.8, macd_signal: "bearish", sentiment: "neutral" },
    ],
  },
  "dividend": {
    name: "Dividend",
    tickers: [
      { ticker: "JPM", price: 198.50, change_pct: 0.35, rsi14: 45.6, macd_signal: "bullish", sentiment: "positive" },
      { ticker: "XOM", price: 112.30, change_pct: -1.20, rsi14: 38.9, macd_signal: "bearish", sentiment: "negative" },
    ],
  },
};

const CHANNEL_OPTIONS = [
  { value: "telegram", label: "Telegram" },
  { value: "email", label: "Email" },
  { value: "wechat", label: "WeChat" },
  { value: "whatsapp", label: "WhatsApp" },
] as const;

function getDefaultThreshold(
  type: AlertType,
  snapshot?: { price: number; rsi14: number },
): string {
  if (type === "price_above" || type === "price_below") {
    return snapshot ? snapshot.price.toFixed(2) : "";
  }
  if (type === "rsi_above" || type === "rsi_below") {
    return snapshot ? snapshot.rsi14.toFixed(1) : "";
  }
  return "";
}

export default function WatchlistPage() {
  const [activeTab, setActiveTab] = useState("my-positions");
  const [alertTicker, setAlertTicker] = useState("");
  const [alertType, setAlertType] = useState<AlertType>("price_above");
  const [alertThreshold, setAlertThreshold] = useState("");
  const [alertChannels, setAlertChannels] = useState<string[]>(["telegram"]);
  const [savingAlert, setSavingAlert] = useState(false);
  const [checkingAlerts, setCheckingAlerts] = useState(false);
  const lists = MOCK_WATCHLISTS;
  const active = lists[activeTab];
  const alertTickerSnapshot = active.tickers.find((ticker) => ticker.ticker === alertTicker);
  const thresholdMeta =
    alertType === "price_above" || alertType === "price_below"
      ? {
          label: "Price Threshold",
          placeholder: alertTickerSnapshot
            ? `Current price ${alertTickerSnapshot.price.toFixed(2)}`
            : "Enter target price",
          hint: "Use the target price that should trigger the alert.",
        }
      : {
          label: "RSI Threshold",
          placeholder:
            alertType === "rsi_above"
              ? `Current RSI ${alertTickerSnapshot?.rsi14 ?? "--"}`
              : `Current RSI ${alertTickerSnapshot?.rsi14 ?? "--"}`,
          hint:
            alertType === "rsi_above"
              ? "Defaults to the ticker's current RSI raw value."
              : "Defaults to the ticker's current RSI raw value.",
        };

  const openAlertForm = (ticker: string, defaultPrice: number) => {
    const snapshot = active.tickers.find((item) => item.ticker === ticker) ?? {
      price: defaultPrice,
      rsi14: 50,
    };
    setAlertTicker(ticker);
    setAlertType("price_above");
    setAlertThreshold(getDefaultThreshold("price_above", snapshot));
    setAlertChannels(["telegram"]);
  };

  const createAlert = async () => {
    if (!alertTicker || !alertThreshold || alertChannels.length === 0) return;
    setSavingAlert(true);
    try {
      await watchlistApi.createAlert(activeTab, {
        ticker: alertTicker,
        type: alertType,
        threshold_value: Number(alertThreshold),
        notification_channels: alertChannels,
      });
      toast.success("Watchlist alert created", {
        description: `${alertTicker} ${alertType.replace("_", " ")} ${alertThreshold}`,
      });
      setAlertTicker("");
    } catch (error: unknown) {
      toast.error("Failed to create alert", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setSavingAlert(false);
    }
  };

  const handleAlertTypeChange = (value: AlertType | null) => {
    if (!value) return;
    setAlertType(value);
    setAlertThreshold(getDefaultThreshold(value, alertTickerSnapshot));
  };

  const toggleAlertChannel = (channel: string, checked: boolean) => {
    setAlertChannels((current) => {
      if (checked) {
        return current.includes(channel) ? current : [...current, channel];
      }
      return current.filter((item) => item !== channel);
    });
  };

  const checkAlerts = async () => {
    setCheckingAlerts(true);
    try {
      const snapshots = Object.fromEntries(
        active.tickers.map((ticker) => [
          ticker.ticker,
          { price: ticker.price, rsi14: ticker.rsi14 },
        ])
      );
      const result = await watchlistApi.checkAlerts({ snapshots });
      toast.success("Alert check completed", {
        description: `${result.triggered_count} alert(s) triggered.`,
      });
    } catch (error: unknown) {
      toast.error("Failed to check alerts", {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setCheckingAlerts(false);
    }
  };

  return (
    <Shell>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Star className="h-5 w-5" />
              Watchlist
            </h2>
            <p className="text-sm text-muted-foreground">
              Track your favorite tickers with real-time indicators and alerts.
            </p>
          </div>
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Watchlist
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 flex-wrap">
          {Object.entries(lists).map(([key, list]) => (
            <Button
              key={key}
              variant={activeTab === key ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTab(key)}
            >
              {list.name}
              <Badge variant="secondary" className="ml-2 text-xs">
                {list.tickers.length}
              </Badge>
            </Button>
          ))}
        </div>

        {/* Table */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="text-base">{active.name}</CardTitle>
              <CardDescription>
                Triggered alerts automatically notify configured channels once.
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={checkingAlerts}
              onClick={checkAlerts}
            >
              <Bell className="mr-2 h-4 w-4" />
              {checkingAlerts ? "Checking..." : "Check Alerts"}
            </Button>
          </CardHeader>
          {active.tickers.length === 0 ? (
            <CardContent className="pt-8">
              <EmptyState
                title="No tickers in this watchlist"
                description="Add tickers to start tracking their performance."
                action={
                  <Button size="sm">
                    <Plus className="mr-2 h-4 w-4" />
                    Add Ticker
                  </Button>
                }
              />
            </CardContent>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Ticker</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="text-right">Change</TableHead>
                  <TableHead className="text-right">RSI(14)</TableHead>
                  <TableHead>MACD</TableHead>
                  <TableHead>Sentiment</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {active.tickers.map((t) => (
                  <TableRow key={t.ticker}>
                    <TableCell>
                      <span className="font-mono font-bold">${t.ticker}</span>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatCurrency(t.price)}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono ${
                        t.change_pct >= 0 ? "text-green-500" : "text-red-500"
                      }`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {t.change_pct >= 0 ? (
                          <TrendingUp className="h-3 w-3" />
                        ) : (
                          <TrendingDown className="h-3 w-3" />
                        )}
                        {formatPercent(t.change_pct)}
                      </span>
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      <span
                        className={
                          t.rsi14 > 70
                            ? "text-red-500"
                            : t.rsi14 < 30
                            ? "text-green-500"
                            : ""
                        }
                      >
                        {t.rsi14}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          t.macd_signal === "bullish"
                            ? "text-green-500 border-green-500/20"
                            : "text-red-500 border-red-500/20"
                        }
                      >
                        {t.macd_signal}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          t.sentiment === "positive"
                            ? "text-green-500 border-green-500/20"
                            : t.sentiment === "negative"
                            ? "text-red-500 border-red-500/20"
                            : ""
                        }
                      >
                        {t.sentiment}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger className="hover:bg-muted rounded-md">
                          <div className="h-8 w-8 flex items-center justify-center">
                            <MoreHorizontal className="h-4 w-4" />
                          </div>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openAlertForm(t.ticker, t.price)}>
                            <Bell className="mr-2 h-4 w-4" />
                            Set Alert
                          </DropdownMenuItem>
                          <DropdownMenuItem className="text-destructive">
                            <Trash2 className="mr-2 h-4 w-4" />
                            Remove
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {alertTicker ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Create Alert for ${alertTicker}</CardTitle>
              <CardDescription>
                When the condition is met, the backend sends a high-priority notification.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div className="space-y-2">
                <Label>Condition</Label>
                <Select
                  value={alertType}
                  onValueChange={handleAlertTypeChange}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="price_above">Price above</SelectItem>
                    <SelectItem value="price_below">Price below</SelectItem>
                    <SelectItem value="rsi_above">RSI above</SelectItem>
                    <SelectItem value="rsi_below">RSI below</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{thresholdMeta.label}</Label>
                <Input
                  type="number"
                  value={alertThreshold}
                  onChange={(event) => setAlertThreshold(event.target.value)}
                  placeholder={thresholdMeta.placeholder}
                />
                <p className="text-xs text-muted-foreground">{thresholdMeta.hint}</p>
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label>Channels</Label>
                <div className="grid grid-cols-2 gap-3 rounded-md border p-3">
                  {CHANNEL_OPTIONS.map((channel) => (
                    <label
                      key={channel.value}
                      className="flex items-center gap-2 text-sm"
                    >
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
                <p className="text-xs text-muted-foreground">
                  Choose one or more channels for this alert.
                </p>
              </div>
              <div className="flex items-end gap-2 md:col-span-4">
                <Button disabled={savingAlert} onClick={createAlert}>
                  {savingAlert ? "Saving..." : "Save Alert"}
                </Button>
                <Button variant="outline" onClick={() => setAlertTicker("")}>
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        {/* Quick add */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add Ticker</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <Input placeholder="Ticker symbol (e.g. AAPL)" className="max-w-xs font-mono" />
              <Button variant="outline">
                <Plus className="mr-2 h-4 w-4" />
                Add
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}
