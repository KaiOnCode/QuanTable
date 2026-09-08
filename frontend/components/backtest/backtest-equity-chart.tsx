import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState } from "@/components/shared/empty-state";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { BacktestSeriesPointView } from "@/lib/types/models";
import { formatCurrency, formatDate, formatPercent } from "@/lib/utils";

type BacktestEquityChartProps = {
  readonly equity: readonly BacktestSeriesPointView[];
};

function tooltipValue(value: unknown, name: unknown): [string, string] {
  const label = typeof name === "string" ? name : "Value";
  if (typeof value !== "number") return ["Unavailable", label];
  return [label.toLowerCase().includes("drawdown") ? formatPercent(value) : formatCurrency(value), label];
}

export function BacktestEquityChart({ equity }: BacktestEquityChartProps) {
  const chartData = equity.map((point) => ({ ...point, dateLabel: formatDate(point.date) }));
  const description = chartData.length === 0
    ? "No daily equity observations were returned by this completed job."
    : `${chartData.length} daily observations compare strategy equity, benchmark equity when available, and strategy drawdown.`;

  return (
    <Card>
      <CardHeader>
        <CardTitle id="backtest-equity-title" className="text-base">Equity and Drawdown</CardTitle>
        <CardDescription id="backtest-equity-description">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? <EmptyState title="No daily equity series" description="This result has no equity observations to chart." className="py-8" /> : (
          <div className="h-80 min-w-0" role="img" aria-labelledby="backtest-equity-title" aria-describedby="backtest-equity-description">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} accessibilityLayer margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="dateLabel" minTickGap={32} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <YAxis yAxisId="equity" tickFormatter={(value: number) => formatCurrency(value)} width={78} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <YAxis yAxisId="drawdown" orientation="right" tickFormatter={formatPercent} width={58} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <Tooltip
                  formatter={tooltipValue}
                  contentStyle={{
                    backgroundColor: "var(--popover)",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--radius)",
                    color: "var(--popover-foreground)",
                  }}
                  labelStyle={{ color: "var(--muted-foreground)" }}
                  itemStyle={{ color: "var(--popover-foreground)" }}
                />
                <Legend />
                <Line yAxisId="equity" type="monotone" dataKey="strategy_equity" name="Strategy equity" stroke="var(--primary)" strokeWidth={2} dot={false} />
                <Line yAxisId="equity" type="monotone" dataKey="benchmark_equity" name="Benchmark equity" stroke="var(--muted-foreground)" strokeWidth={2} dot={false} connectNulls={false} />
                <Line yAxisId="drawdown" type="monotone" dataKey="strategy_drawdown_pct" name="Strategy drawdown" stroke="var(--destructive)" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
