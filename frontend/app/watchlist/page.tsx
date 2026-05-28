"use client";

import { useState } from "react";
import { Shell } from "@/components/layout/shell";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { EmptyState } from "@/components/shared/empty-state";
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

export default function WatchlistPage() {
  const [activeTab, setActiveTab] = useState("my-positions");
  const lists = MOCK_WATCHLISTS;
  const active = lists[activeTab];

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
                          <DropdownMenuItem>
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
