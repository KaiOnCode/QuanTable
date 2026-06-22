"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api/client";
import { formatCurrency } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  ComposedChart,
  Area,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  DollarSign,
} from "lucide-react";

type Timeframe = "1M" | "3M" | "6M" | "1Y";

const TIMEFRAME_DAYS: Record<Timeframe, number> = {
  "1M": 30,
  "3M": 90,
  "6M": 180,
  "1Y": 365,
};

function getDateRange(tf: Timeframe) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - TIMEFRAME_DAYS[tf]);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

type Props = {
  ticker: string;
};

export function TickerPreview({ ticker }: Props) {
  const [timeframe, setTimeframe] = useState<Timeframe>("3M");
  const [tab, setTab] = useState("price");

  const { start, end } = getDateRange(timeframe);

  const pricesQuery = useQuery({
    queryKey: ["market", "prices", ticker, start, end],
    queryFn: () =>
      api.get<{
        ticker: string;
        bars: { date: string; close: number; volume: number }[];
      }>(`market/prices/${ticker}?start=${start}&end=${end}`),
    enabled: !!ticker,
    staleTime: 60_000,
  });

  const fundamentalsQuery = useQuery({
    queryKey: ["market", "fundamentals", ticker],
    queryFn: () =>
      api.get<{
        ticker: string;
        fundamentals: Record<string, number | string> | null;
      }>(`market/fundamentals/${ticker}`),
    enabled: !!ticker,
    staleTime: 120_000,
  });

  const indicatorsQuery = useQuery({
    queryKey: ["market", "indicators", ticker],
    queryFn: () =>
      api.get<{
        ticker: string;
        rsi14: number | null;
        macd_signal: string;
        sma20: number | null;
        sma50: number | null;
        atr14: number | null;
      }>(`market/indicators/${ticker}`),
    enabled: !!ticker,
    staleTime: 60_000,
  });

  const metaQuery = useQuery({
    queryKey: ["market", "meta", ticker],
    queryFn: () =>
      api.get<{
        meta: Record<string, { name: string; short_name: string; sector: string; industry: string; currency: string; market: string; country: string } | null>;
      }>(`market/meta?tickers=${ticker}`),
    enabled: !!ticker,
    staleTime: Infinity,
  });

  const chartData = useMemo(() => {
    const bars = pricesQuery.data?.bars || [];
    const thisYear = new Date().getFullYear();
    return bars.map((b) => {
      const d = b.date;
      if (!d) return { ...b, date: "" };
      const year = parseInt(d.slice(0, 4), 10);
      // Show year prefix for dates not in the current year
      return { ...b, date: year !== thisYear ? d.slice(0, 10) : d.slice(5) };
    });
  }, [pricesQuery.data]);

  const priceChange = useMemo(() => {
    if (chartData.length < 2) return null;
    const first = chartData[0]?.close ?? 0;
    const last = chartData[chartData.length - 1]?.close ?? 0;
    if (!first) return null;
    const pct = ((last - first) / first) * 100;
    return { value: pct, last };
  }, [chartData]);

  const meta = metaQuery.data?.meta?.[ticker?.toUpperCase()];
  const currency = meta?.currency || "USD";
  const fundamentals = fundamentalsQuery.data?.fundamentals;
  const indicators = indicatorsQuery.data;

  // Compute volume bar colors: green for up days, red for down
  const chartDataWithMA = useMemo(() => {
    return chartData.map((d, i, arr) => {
      const slice = (n: number) =>
        arr.slice(Math.max(0, i - n + 1), i + 1);
      const avg = (vals: number[]) =>
        vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
      return {
        ...d,
        ma20: avg(slice(20).map((p) => p.close)),
        ma50: avg(slice(50).map((p) => p.close)),
        volumeColor: d.close >= (arr[i - 1]?.close ?? d.close) ? "#22c55e40" : "#ef444440",
      };
    });
  }, [chartData]);

  // RSI gauge color
  const rsiColor =
    indicators?.rsi14 == null
      ? "bg-muted"
      : indicators.rsi14 >= 70
        ? "bg-red-500"
        : indicators.rsi14 <= 30
          ? "bg-green-500"
          : "bg-blue-500";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            {meta?.name || meta?.short_name || ticker}
            <Badge variant="outline" className="text-[10px] font-mono">
              {ticker}
            </Badge>
            {meta?.sector && (
              <span className="text-xs text-muted-foreground">
                {meta.sector}
              </span>
            )}
          </CardTitle>
          {priceChange && (
            <div className="flex items-center gap-1 text-sm">
              <span className="font-mono">
                {formatCurrency(priceChange.last, currency)}
              </span>
              <span
                className={
                  priceChange.value >= 0 ? "text-green-500" : "text-red-500"
                }
              >
                {priceChange.value >= 0 ? (
                  <TrendingUp className="h-4 w-4 inline" />
                ) : (
                  <TrendingDown className="h-4 w-4 inline" />
                )}{" "}
                {priceChange.value >= 0 ? "+" : ""}
                {priceChange.value.toFixed(2)}%
              </span>
            </div>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <Tabs value={tab} onValueChange={setTab}>
          <div className="flex items-center justify-between mb-3">
            <TabsList className="h-8">
              <TabsTrigger value="price" className="text-xs">
                <Activity className="h-3 w-3 mr-1" />
                Price
              </TabsTrigger>
              <TabsTrigger value="fundamentals" className="text-xs">
                <DollarSign className="h-3 w-3 mr-1" />
                Fundamentals
              </TabsTrigger>
              <TabsTrigger value="indicators" className="text-xs">
                <TrendingUp className="h-3 w-3 mr-1" />
                Indicators
              </TabsTrigger>
            </TabsList>

            {tab === "price" && (
              <div className="flex gap-0.5">
                {(["1M", "3M", "6M", "1Y"] as Timeframe[]).map((tf) => (
                  <Button
                    key={tf}
                    variant={timeframe === tf ? "default" : "ghost"}
                    size="sm"
                    className="h-7 text-xs px-2"
                    onClick={() => setTimeframe(tf)}
                  >
                    {tf}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Price Chart Tab */}
          <TabsContent value="price" className="mt-0">
            {pricesQuery.isLoading ? (
              <Skeleton className="h-64 w-full" />
            ) : chartData.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground py-16">
                No price data available
              </p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={220}>
                  <ComposedChart data={chartDataWithMA}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 10 }}
                      interval="preserveStartEnd"
                      hide
                    />
                    <YAxis
                      tick={{ fontSize: 10 }}
                      domain={["auto", "auto"]}
                      width={55}
                      stroke="rgba(148,163,184,0.5)"
                    />
                    <Tooltip
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: "1px solid rgba(148,163,184,0.3)",
                        background: "var(--background)",
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="close"
                      stroke="#22c55e"
                      fill="url(#priceGradient)"
                      strokeWidth={2}
                      dot={false}
                    />
                    <defs>
                      <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#22c55e" stopOpacity={0.2} />
                        <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Line
                      type="monotone"
                      dataKey="ma20"
                      stroke="#f59e0b"
                      strokeWidth={1}
                      dot={false}
                      strokeDasharray="4 2"
                    />
                    <Line
                      type="monotone"
                      dataKey="ma50"
                      stroke="#ec4899"
                      strokeWidth={1}
                      dot={false}
                      strokeDasharray="4 2"
                    />
                  </ComposedChart>
                </ResponsiveContainer>

                {/* Volume bars */}
                <ResponsiveContainer width="100%" height={50}>
                  <BarChart data={chartDataWithMA}>
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} hide />
                    <Tooltip
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: "1px solid rgba(148,163,184,0.3)",
                        background: "var(--background)",
                      }}
                    />
                    <Bar
                      dataKey="volume"
                      fill="#22c55e"
                      radius={[1, 1, 0, 0]}
                      opacity={0.3}
                    />
                  </BarChart>
                </ResponsiveContainer>

                {/* Legend */}
                <div className="flex items-center gap-4 text-[10px] text-muted-foreground mt-2">
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-0.5 rounded bg-[#22c55e]" />
                    Close
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-0.5 rounded bg-[#f59e0b]" style={{ borderTop: "1px dashed #f59e0b" }} />
                    MA20
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-0.5 rounded bg-[#ec4899]" style={{ borderTop: "1px dashed #ec4899" }} />
                    MA50
                  </div>
                </div>
              </>
            )}
          </TabsContent>

          {/* Fundamentals Tab */}
          <TabsContent value="fundamentals" className="mt-0">
            {fundamentalsQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : !fundamentals ? (
              <p className="text-center text-sm text-muted-foreground py-16">
                No fundamentals data available
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
                  <MetricCard
                    label="Market Cap"
                    value={
                      typeof fundamentals.market_cap === "number"
                        ? formatMarketCap(fundamentals.market_cap as number)
                        : "—"
                    }
                  />
                  <MetricCard
                    label="PE Ratio"
                    value={
                      fundamentals.pe != null
                        ? (fundamentals.pe as number).toFixed(1)
                        : "—"
                    }
                  />
                  <MetricCard
                    label="PB Ratio"
                    value={
                      fundamentals.pb != null
                        ? (fundamentals.pb as number).toFixed(1)
                        : "—"
                    }
                  />
                  <MetricCard
                    label="EPS"
                    value={
                      fundamentals.eps != null
                        ? formatCurrency(fundamentals.eps as number, currency)
                        : "—"
                    }
                  />
                  <MetricCard
                    label="ROE"
                    value={
                      fundamentals.roe != null
                        ? `${(fundamentals.roe as number).toFixed(1)}%`
                        : "—"
                    }
                  />
                  <MetricCard
                    label="Dividend Yield"
                    value={
                      fundamentals.dividend_yield != null
                        ? `${(fundamentals.dividend_yield as number).toFixed(2)}%`
                        : "—"
                    }
                  />
                  <MetricCard
                    label="Profit Margin"
                    value={
                      fundamentals.profit_margin != null
                        ? `${(fundamentals.profit_margin as number).toFixed(1)}%`
                        : "—"
                    }
                  />
                  <MetricCard label="Sector" value={meta?.sector || "—"} />
                </div>
                {meta && (
                  <div className="text-xs text-muted-foreground space-y-1">
                    <div className="flex gap-2">
                      <span className="font-medium">Industry:</span> {meta.industry || "—"}
                    </div>
                    <div className="flex gap-2">
                      <span className="font-medium">Country:</span> {meta.country || "—"}
                    </div>
                    <div className="flex gap-2">
                      <span className="font-medium">Exchange:</span> {meta.market || "—"}
                    </div>
                  </div>
                )}
              </>
            )}
          </TabsContent>

          {/* Indicators Tab */}
          <TabsContent value="indicators" className="mt-0">
            {indicatorsQuery.isLoading ? (
              <div className="space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-6 w-full" />
                <Skeleton className="h-6 w-full" />
              </div>
            ) : !indicators ? (
              <p className="text-center text-sm text-muted-foreground py-16">
                No indicators data available
              </p>
            ) : (
              <div className="space-y-4">
                {/* RSI */}
                <div>
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="font-medium">RSI (14)</span>
                    <span className="font-mono">
                      {indicators.rsi14 != null ? indicators.rsi14.toFixed(1) : "—"}
                    </span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${rsiColor}`}
                      style={{ width: `${Math.min(100, Math.max(0, indicators.rsi14 || 0))}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
                    <span>Oversold</span>
                    <span>30</span>
                    <span>50</span>
                    <span>70</span>
                    <span>Overbought</span>
                  </div>
                </div>

                {/* MACD */}
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">MACD Signal</span>
                  <Badge
                    variant="outline"
                    className={
                      indicators.macd_signal === "bullish"
                        ? "text-green-500 border-green-500/20"
                        : "text-red-500 border-red-500/20"
                    }
                  >
                    {indicators.macd_signal === "bullish" ? (
                      <TrendingUp className="h-3 w-3 mr-1" />
                    ) : (
                      <TrendingDown className="h-3 w-3 mr-1" />
                    )}
                    {indicators.macd_signal}
                  </Badge>
                </div>

                {/* SMAs */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-lg bg-muted/30">
                    <div className="text-[10px] text-muted-foreground">SMA 20</div>
                    <div className="text-sm font-mono font-bold">
                      {indicators.sma20 != null
                        ? formatCurrency(indicators.sma20, currency)
                        : "—"}
                    </div>
                  </div>
                  <div className="p-3 rounded-lg bg-muted/30">
                    <div className="text-[10px] text-muted-foreground">SMA 50</div>
                    <div className="text-sm font-mono font-bold">
                      {indicators.sma50 != null
                        ? formatCurrency(indicators.sma50, currency)
                        : "—"}
                    </div>
                  </div>
                </div>

                {/* ATR */}
                <div className="p-3 rounded-lg bg-muted/30">
                  <div className="text-[10px] text-muted-foreground">ATR (14)</div>
                  <div className="text-sm font-mono font-bold">
                    {indicators.atr14 != null
                      ? formatCurrency(indicators.atr14, currency)
                      : "—"}
                  </div>
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function formatMarketCap(value: number): string {
  if (value >= 1e12) return (value / 1e12).toFixed(2) + "T";
  if (value >= 1e9) return (value / 1e9).toFixed(2) + "B";
  if (value >= 1e6) return (value / 1e6).toFixed(2) + "M";
  return (value / 1e3).toFixed(2) + "K";
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="p-2.5 rounded-lg bg-muted/30">
      <div className="text-[10px] text-muted-foreground mb-0.5">{label}</div>
      <div className="text-sm font-mono font-medium truncate">{value}</div>
    </div>
  );
}
